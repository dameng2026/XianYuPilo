#!/bin/sh
# 首次启动初始化向导：自动生成所有 secrets 文件、bcrypt admin 密码 hash 和 .env。
# 安全设计：所有随机值都从 /dev/urandom 读取；密码 hash 用 bcrypt cost 12；
# secrets 目录权限 0700，文件权限 0644（容器内非 root 用户需读取）。
# 已存在的文件不会被覆盖。
#
# 注意：不使用 `set -e`，因为 bcrypt 生成有多层兜底，单层失败不应终止脚本。
# 使用 `set -u` 捕获未定义变量引用。

set -u

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_DIR"

SECRETS_DIR="./secrets"
DEFAULT_ADMIN_PASSWORD="admin123"

color() { printf '\033[%sm%s\033[0m' "$1" "$2"; }
info()  { printf '%s %s\n' "$(color '1;36' '•')" "$*"; }
ok()    { printf '%s %s\n' "$(color '1;32' '✓')" "$*"; }
warn()  { printf '%s %s\n' "$(color '1;33' '!')" "$*" >&2; }
die()   { printf '%s %s\n' "$(color '1;31' '✗')" "$*" >&2; exit 1; }

# ---------- 1. 前置依赖检查 ----------
# 生成 secrets 不需要 Docker；只有 bcrypt 生成在主机无 Python 时才退到 Docker 容器
command -v openssl >/dev/null 2>&1 || command -v head >/dev/null 2>&1 || die "未检测到 openssl/head，无法生成随机密钥"

# ---------- 2. 创建 secrets 目录 ----------
mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR" 2>/dev/null || true

# 生成 base64url 随机字符串（A-Za-z0-9_-，符合 Redis 密码正则要求）
gen_random() {
  bytes=${1:-32}
  # 优先用 openssl（更可靠），退到 /dev/urandom + base64
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 "$bytes" 2>/dev/null | tr -d '\n=' | tr '+/' '-_'
  else
    head -c "$bytes" /dev/urandom | base64 | tr -d '\n=' | tr '+/' '-_'
  fi
}

# 写入 secret 文件（已存在且非空则跳过）
# 权限 0644：docker-compose secrets file 模式下，容器内进程（如 mysql 用户）需要读取权限
write_secret() {
  file=$1
  content=$2
  if [ -s "$file" ]; then
    return 0
  fi
  printf '%s' "$content" > "$file"
  chmod 644 "$file" 2>/dev/null || true
}

# 生成空的可选 secret 文件（已存在则跳过）
touch_optional() {
  file=$1
  if [ ! -f "$file" ]; then
    : > "$file"
    chmod 644 "$file" 2>/dev/null || true
  fi
}

# ---------- 3. 生成必需的随机 secrets ----------
info "生成随机 secrets（如已存在则跳过）..."

# 3 组 MySQL 密码必须互不相同且 >=16 字符；gen_random 32 bytes 输出 ~43 字符，远超要求
write_secret "$SECRETS_DIR/mysql-root-password"       "$(gen_random 32)"
write_secret "$SECRETS_DIR/mysql-app-password"        "$(gen_random 32)"
write_secret "$SECRETS_DIR/mysql-migration-password"  "$(gen_random 32)"
# Redis 密码必须 Base64URL 字符
write_secret "$SECRETS_DIR/redis-password"            "$(gen_random 32)"
# JWT/Cookie/Token 必须 >=32 字符
write_secret "$SECRETS_DIR/jwt-secret"                "$(gen_random 64)"
write_secret "$SECRETS_DIR/cookie-crypto-secret"      "$(gen_random 64)"
write_secret "$SECRETS_DIR/internal-api-token"        "$(gen_random 64)"

# ---------- 4. 生成空的可选 secrets（功能未启用时也需要文件存在） ----------
touch_optional "$SECRETS_DIR/commercial-backend-access-token"
touch_optional "$SECRETS_DIR/embedding-api-key"
touch_optional "$SECRETS_DIR/ai-provider-api-key"
touch_optional "$SECRETS_DIR/amap-api-key"

# ---------- 5. 生成 admin bcrypt 密码 hash ----------
# 多层兜底策略（任一成功即完成）：
#   1. 主机 Python + bcrypt（已装）
#   2. 主机 pip install --user bcrypt
#   3. Docker 容器 python:3.11-slim + pip install bcrypt（默认 PyPI 源）
#   4. Docker 容器 python:3.11-slim + pip install bcrypt（国内清华源，解决网络问题）
#   5. Docker 容器 python:3.11-alpine（更小，拉取快）+ 国内源
#   6. 最终兜底：跳过生成，由 start.sh 在镜像构建后用 api 镜像生成
ADMIN_PASSWORD="${ADMIN_PASSWORD:-$DEFAULT_ADMIN_PASSWORD}"

if [ -s "$SECRETS_DIR/admin-password-hash" ]; then
  ok "admin-password-hash 已存在（跳过生成）"
  DISPLAY_PASSWORD="$ADMIN_PASSWORD"
else
  info "生成 admin bcrypt 密码 hash（cost 12）..."
  export ADMIN_PASSWORD

  hash_value=""
  bcrypt_failed_reasons=""

  # --- 方案 1：主机 Python + bcrypt（已装） ---
  if [ -z "$hash_value" ]; then
    python_cmd=""
    if command -v python3 >/dev/null 2>&1 && python3 -c "import bcrypt" 2>/dev/null; then
      python_cmd="python3"
    elif command -v python >/dev/null 2>&1 && python -c "import bcrypt" 2>/dev/null; then
      python_cmd="python"
    fi

    if [ -n "$python_cmd" ]; then
      info "  [1/5] 使用主机 $python_cmd + bcrypt 生成..."
      hash_value=$($python_cmd -c '
import os, bcrypt
pw = os.environ["ADMIN_PASSWORD"].encode("utf-8")
print(bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode())
' 2>/dev/null) || hash_value=""
      if [ -n "$hash_value" ]; then
        ok "  [1/5] 主机 Python bcrypt 生成成功"
      else
        bcrypt_failed_reasons="$bcrypt_failed_reasons\n  - 主机 Python bcrypt 调用失败"
      fi
    else
      bcrypt_failed_reasons="$bcrypt_failed_reasons\n  - 主机无 Python bcrypt 包"
    fi
  fi

  # --- 方案 2：主机 pip install --user bcrypt ---
  if [ -z "$hash_value" ]; then
    pip_cmd=""
    if command -v python3 >/dev/null 2>&1; then
      pip_cmd="python3"
    elif command -v python >/dev/null 2>&1; then
      pip_cmd="python"
    fi

    if [ -n "$pip_cmd" ] && $pip_cmd -m pip --version >/dev/null 2>&1; then
      info "  [2/5] 主机未装 bcrypt，尝试 pip install --user bcrypt..."
      pip_output=$($pip_cmd -m pip install --user --quiet --timeout 60 bcrypt 2>&1) || true
      if $pip_cmd -c "import bcrypt" 2>/dev/null; then
        hash_value=$($pip_cmd -c '
import os, bcrypt
pw = os.environ["ADMIN_PASSWORD"].encode("utf-8")
print(bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode())
' 2>/dev/null) || hash_value=""
        if [ -n "$hash_value" ]; then
          ok "  [2/5] pip install bcrypt 成功并生成 hash"
        else
          bcrypt_failed_reasons="$bcrypt_failed_reasons\n  - pip install 后 bcrypt 调用失败"
        fi
      else
        bcrypt_failed_reasons="$bcrypt_failed_reasons\n  - pip install bcrypt 失败：$(echo "$pip_output" | tail -1)"
      fi
    else
      bcrypt_failed_reasons="$bcrypt_failed_reasons\n  - 主机无 pip"
    fi
  fi

  # --- 方案 3：Docker 容器 python:3.11-slim（默认 PyPI 源） ---
  if [ -z "$hash_value" ] && command -v docker >/dev/null 2>&1; then
    info "  [3/5] 使用 Docker 临时容器生成（python:3.11-slim，默认源，首次约 30-60s）..."
    # 注意：不吞掉 stderr，但用 2>&1 合并到 stdout 以便捕获错误信息
    docker_output=$(docker run --rm -e ADMIN_PASSWORD python:3.11-slim sh -c '
      pip install --quiet --no-cache-dir --timeout 60 bcrypt 2>&1 && \
      python -c "
import os, bcrypt
pw = os.environ[\"ADMIN_PASSWORD\"].encode(\"utf-8\")
print(bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode())
"
    ' 2>&1) || true
    # 从输出中提取 bcrypt hash（以 $2 开头的行）
    hash_value=$(echo "$docker_output" | grep -E '^\$2[aby]\$' | head -1) || hash_value=""
    if [ -n "$hash_value" ]; then
      ok "  [3/5] Docker python:3.11-slim 生成成功"
    else
      bcrypt_failed_reasons="$bcrypt_failed_reasons\n  - Docker python:3.11-slim 失败：$(echo "$docker_output" | tail -2 | head -1)"
    fi
  fi

  # --- 方案 4：Docker 容器 python:3.11-slim + 国内清华源 ---
  if [ -z "$hash_value" ] && command -v docker >/dev/null 2>&1; then
    info "  [4/5] 使用国内 PyPI 镜像源重试（清华源）..."
    docker_output=$(docker run --rm -e ADMIN_PASSWORD python:3.11-slim sh -c '
      pip install --quiet --no-cache-dir --timeout 60 \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        --trusted-host pypi.tuna.tsinghua.edu.cn \
        bcrypt 2>&1 && \
      python -c "
import os, bcrypt
pw = os.environ[\"ADMIN_PASSWORD\"].encode(\"utf-8\")
print(bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode())
"
    ' 2>&1) || true
    hash_value=$(echo "$docker_output" | grep -E '^\$2[aby]\$' | head -1) || hash_value=""
    if [ -n "$hash_value" ]; then
      ok "  [4/5] 国内源 Docker 生成成功"
    else
      bcrypt_failed_reasons="$bcrypt_failed_reasons\n  - Docker 国内源失败：$(echo "$docker_output" | tail -2 | head -1)"
    fi
  fi

  # --- 方案 5：Docker 容器 python:3.11-alpine（更小，拉取快） + 国内源 ---
  if [ -z "$hash_value" ] && command -v docker >/dev/null 2>&1; then
    info "  [5/5] 使用更小的 alpine 镜像重试..."
    docker_output=$(docker run --rm -e ADMIN_PASSWORD python:3.11-alpine sh -c '
      apk add --no-cache --quiet build-base libffi-dev 2>/dev/null
      pip install --quiet --no-cache-dir --timeout 60 \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        --trusted-host pypi.tuna.tsinghua.edu.cn \
        bcrypt 2>&1 && \
      python -c "
import os, bcrypt
pw = os.environ[\"ADMIN_PASSWORD\"].encode(\"utf-8\")
print(bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode())
"
    ' 2>&1) || true
    hash_value=$(echo "$docker_output" | grep -E '^\$2[aby]\$' | head -1) || hash_value=""
    if [ -n "$hash_value" ]; then
      ok "  [5/5] alpine 镜像生成成功"
    else
      bcrypt_failed_reasons="$bcrypt_failed_reasons\n  - alpine 镜像失败：$(echo "$docker_output" | tail -2 | head -1)"
    fi
  fi

  # --- 最终处理 ---
  if [ -n "$hash_value" ]; then
    printf '%s' "$hash_value" > "$SECRETS_DIR/admin-password-hash"
    chmod 644 "$SECRETS_DIR/admin-password-hash" 2>/dev/null || true
    ok "admin bcrypt hash 生成完成"
  else
    # 所有方案失败：不终止脚本，由 start.sh 用 api 镜像兜底生成
    warn "所有 bcrypt 生成方案均失败，将延迟到镜像构建后用 api 容器生成"
    warn "失败原因：$bcrypt_failed_reasons"
    # 创建空文件作为标记，start.sh 会检测并用 api 镜像生成
    : > "$SECRETS_DIR/admin-password-hash"
    chmod 644 "$SECRETS_DIR/admin-password-hash" 2>/dev/null || true
  fi

  DISPLAY_PASSWORD="$ADMIN_PASSWORD"
  unset ADMIN_PASSWORD
fi

# ---------- 6. 创建 .env ----------
if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    ok "已从 .env.example 创建 .env"
  else
    die ".env.example 不存在，无法创建 .env"
  fi
else
  ok ".env 已存在（跳过创建）"
fi

# ---------- 7. 完成 ----------
DISPLAY_PASSWORD="${DISPLAY_PASSWORD:-$DEFAULT_ADMIN_PASSWORD}"

cat <<EOF

$(ok "初始化完成")

默认管理员账号：
  用户名：admin
  密码：${DISPLAY_PASSWORD}

$(warn "请尽快登录后修改默认密码！")

下一步：
  启动服务：sh ./start.sh
  或手动：docker compose pull && docker compose up -d

EOF
