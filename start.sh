#!/bin/sh
# 一键启动脚本：自动初始化 secrets、拉取镜像、启动服务、等待健康。
# 用法：
#   sh ./start.sh              # 拉取预构建镜像并启动（推荐）
#   sh ./start.sh --build      # 本地源码构建并启动
#   sh ./start.sh --no-pull    # 跳过镜像拉取（用本地已有的镜像）
#
# 错误兜底策略：
#   - Docker 未安装 → 自动安装（get.docker.com）
#   - secrets 生成失败 → setup-wizard.sh 内部多层兜底
#   - bcrypt hash 生成失败 → 镜像构建后用 api 容器兜底生成
#   - 镜像拉取失败 → 自动回退到本地源码构建
#   - 容器启动失败 → 显示异常服务名和日志查看命令
#   - 健康检查超时 → 显示日志查看命令
#   - 端口被占用 → 提示修改 WEB_PORT
#
# 注意：不使用 `set -e`，因为部署流程中某些步骤失败时有兜底方案，不应立即终止。

set -u

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PROJECT_DIR"

DO_BUILD=0
DO_PULL=1
for arg in "$@"; do
  case "$arg" in
    --build)   DO_BUILD=1; DO_PULL=0 ;;
    --no-pull) DO_PULL=0 ;;
    *) echo "未知参数：$arg（支持：--build 本地构建 / --no-pull 跳过拉取）" >&2; exit 1 ;;
  esac
done

color() { printf '\033[%sm%s\033[0m' "$1" "$2"; }
info()  { printf '%s %s\n' "$(color '1;36' '•')" "$*"; }
ok()    { printf '%s %s\n' "$(color '1;32' '✓')" "$*"; }
warn()  { printf '%s %s\n' "$(color '1;33' '!')" "$*" >&2; }
die()   { printf '%s %s\n' "$(color '1;31' '✗')" "$*" >&2; exit 1; }

# 自动安装 Docker（Ubuntu/Debian/CentOS/RHEL/Fedora 等，用官方 get.docker.com 脚本）
ensure_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    return 0
  fi

  # 检测发行版
  os_id="unknown"
  if [ -f /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    os_id="${ID:-unknown}"
  fi

  # 非 root 用户检查
  if [ "$(id -u)" != "0" ]; then
    if command -v sudo >/dev/null 2>&1; then
      SUDO=sudo
    else
      die "Docker 未安装且当前用户非 root，也未安装 sudo。请让管理员安装 Docker：https://docs.docker.com/get-docker/"
    fi
  else
    SUDO=""
  fi

  warn "未检测到 Docker，尝试自动安装（发行版：$os_id）..."
  info "使用 Docker 官方安装脚本 get.docker.com（约 1-2 分钟）..."

  # 下载官方安装脚本
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh || die "下载 get.docker.sh 失败，请检查网络或手动安装：https://docs.docker.com/get-docker/"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO /tmp/get-docker.sh https://get.docker.com || die "下载 get.docker.sh 失败，请检查网络或手动安装：https://docs.docker.com/get-docker/"
  else
    die "未检测到 curl/wget，请手动安装 Docker：https://docs.docker.com/get-docker/"
  fi

  # 执行安装
  sh /tmp/get-docker.sh || die "Docker 安装失败，请查看上方输出或手动安装"
  rm -f /tmp/get-docker.sh

  # 启动 Docker 服务（systemd 系统）
  if command -v systemctl >/dev/null 2>&1; then
    $SUDO systemctl enable docker 2>/dev/null || true
    $SUDO systemctl start docker 2>/dev/null || true
  fi

  # 非 root 用户加入 docker 组（需重新登录生效，本次先用 sudo）
  if [ "$(id -u)" != "0" ]; then
    $SUDO usermod -aG docker "$(whoami)" 2>/dev/null || true
    info "已将当前用户加入 docker 组，重新登录后可直接使用 docker 命令"
    # 本次会话用 sudo 调用 docker
    if [ -z "$SUDO" ]; then
      die "无法配置 docker 命令访问权限"
    fi
  fi

  # 等待 Docker daemon 就绪
  info "等待 Docker daemon 就绪..."
  docker_ok=0
  i=0
  while [ "$i" -lt 30 ]; do
    if $SUDO docker info >/dev/null 2>&1; then
      docker_ok=1
      break
    fi
    sleep 1
    i=$((i + 1))
  done

  if [ "$docker_ok" = "0" ]; then
    die "Docker 已安装但 daemon 未就绪，请检查：systemctl status docker"
  fi

  ok "Docker 安装完成"
}

# 用 api 镜像兜底生成 admin bcrypt hash
# 当 setup-wizard.sh 中所有 bcrypt 生成方案都失败时，此函数在 api 镜像构建后调用
# api 镜像内一定有 bcrypt（FastAPI 依赖），是最可靠的兜底方案
generate_admin_hash_with_api_image() {
  if [ -s "./secrets/admin-password-hash" ]; then
    # 文件非空，检查是否是有效的 bcrypt hash
    if grep -qE '^\$2[aby]\$' "./secrets/admin-password-hash" 2>/dev/null; then
      return 0
    fi
  fi

  info "用 api 镜像兜底生成 admin bcrypt hash..."
  ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin123}"
  export ADMIN_PASSWORD

  # 获取 api 镜像名（从 docker-compose.yml 或默认值）
  api_image=$($DOCKER_COMPOSE config --images 2>/dev/null | grep -i 'api' | head -1) || api_image=""
  if [ -z "$api_image" ]; then
    api_image="xianyu-assistant-api"
  fi

  # 用 api 镜像生成 hash
  hash_value=$(docker run --rm -e ADMIN_PASSWORD "$api_image" python -c '
import os, bcrypt
pw = os.environ["ADMIN_PASSWORD"].encode("utf-8")
print(bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode())
' 2>/dev/null) || hash_value=""

  if [ -n "$hash_value" ] && echo "$hash_value" | grep -qE '^\$2[aby]\$'; then
    printf '%s' "$hash_value" > "./secrets/admin-password-hash"
    chmod 644 "./secrets/admin-password-hash" 2>/dev/null || true
    ok "admin bcrypt hash 兜底生成成功（用 api 镜像）"
    unset ADMIN_PASSWORD
    return 0
  else
    warn "api 镜像兜底生成也失败"
    unset ADMIN_PASSWORD
    return 1
  fi
}

# 检查端口是否被占用
check_port_available() {
  port=$1
  if command -v ss >/dev/null 2>&1; then
    if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
      return 1
    fi
  elif command -v netstat >/dev/null 2>&1; then
    if netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
      return 1
    fi
  fi
  return 0
}

print_access_info() {
  # 推断可访问地址
  if [ "$WEB_BIND" = "0.0.0.0" ]; then
    # 尝试获取本机 IP
    lan_ip=""
    if command -v hostname >/dev/null 2>&1; then
      lan_ip=$(hostname -I 2>/dev/null | awk '{print $1}' || true)
    fi
    if command -v ip >/dev/null 2>&1; then
      lan_ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}' || true)
    fi

    echo "访问地址："
    echo "  本机：    http://localhost:${WEB_PORT}"
    [ -n "$lan_ip" ] && echo "  局域网：  http://${lan_ip}:${WEB_PORT}"
  else
    echo "访问地址：http://localhost:${WEB_PORT}"
  fi
  echo ""
  echo "默认账号：admin"
  echo "默认密码：admin123（首次启动时由脚本生成，请尽快修改）"
  echo ""
  echo "常用命令："
  echo "  查看状态：python scripts/production_ops.py --env-file .env status"
  echo "  查看日志：python scripts/production_ops.py --env-file .env logs --tail 200"
  echo "  停止服务：python scripts/production_ops.py --env-file .env stop"
  echo ""
  warn "默认绑定 0.0.0.0:${WEB_PORT}，暴露到公网前请在 .env 中配置 TRUSTED_HOSTS 和反向代理 TLS"
}

# ---------- 1. 前置依赖检查 + 自动安装 Docker ----------
SUDO=""
ensure_docker

# 如果是非 root 用户，后续 docker 命令需要 sudo
if [ "$(id -u)" != "0" ] && ! docker info >/dev/null 2>&1; then
  SUDO="sudo"
fi

DOCKER_COMPOSE="${SUDO} docker compose"

# ---------- 2. 首次启动初始化 ----------
need_init=0
[ ! -f .env ] && need_init=1
[ ! -d ./secrets ] && need_init=1
[ -d ./secrets ] && [ -z "$(ls -A ./secrets 2>/dev/null)" ] && need_init=1
# 检查关键 secrets 文件是否齐全
for f in admin-password-hash mysql-root-password mysql-app-password mysql-migration-password \
         redis-password jwt-secret cookie-crypto-secret internal-api-token; do
  [ ! -s "./secrets/$f" ] && need_init=1
done

if [ "$need_init" = "1" ]; then
  info "首次启动，运行初始化向导..."
  sh ./scripts/setup-wizard.sh
fi

# ---------- 3. 加载 .env（用于读取 WEB_PORT 等变量） ----------
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

WEB_PORT="${WEB_PORT:-8080}"
WEB_BIND="${WEB_BIND_ADDRESS:-0.0.0.0}"

# ---------- 3.5 端口占用检查 ----------
if ! check_port_available "$WEB_PORT"; then
  warn "端口 $WEB_PORT 已被占用！"
  info "解决方法：修改 .env 中的 WEB_PORT=其他端口（如 8081），然后重新运行 sh ./start.sh"
  info "或检查占用进程：ss -tlnp | grep :${WEB_PORT}"
  die "端口 $WEB_PORT 被占用，无法启动"
fi

# ---------- 4. 拉取镜像或本地构建 ----------
# 先构建/拉取镜像（不启动服务），以便用 api 镜像兜底生成 bcrypt hash
build_ok=0
if [ "$DO_BUILD" = "1" ]; then
  info "本地源码构建镜像（首次约 5-10 分钟）..."
  if $DOCKER_COMPOSE build 2>&1; then
    build_ok=1
  else
    die "镜像构建失败。查看错误信息上方输出，或检查网络和磁盘空间"
  fi
else
  pull_ok=0
  if [ "$DO_PULL" = "1" ]; then
    info "拉取最新镜像（首次约 3-5 分钟）..."
    if $DOCKER_COMPOSE pull 2>&1; then
      pull_ok=1
    else
      warn "镜像拉取失败（可能是 GHCR 镜像未发布或命名空间不匹配）"
      info "自动回退到本地源码构建（首次约 5-10 分钟）..."
      DO_BUILD=1
    fi
  fi
  if [ "$pull_ok" = "1" ]; then
    build_ok=1
  else
    if $DOCKER_COMPOSE build 2>&1; then
      build_ok=1
    else
      die "镜像构建失败。查看错误信息上方输出，或检查网络和磁盘空间"
    fi
  fi
fi

# ---------- 4.5 兜底生成 admin bcrypt hash（用 api 镜像） ----------
# setup-wizard.sh 中所有 bcrypt 生成方案都失败时，admin-password-hash 为空
# 此时 api 镜像已经构建好，用它来生成 hash（api 镜像内一定有 bcrypt）
if [ -f "./secrets/admin-password-hash" ] && [ ! -s "./secrets/admin-password-hash" ]; then
  generate_admin_hash_with_api_image || {
    warn "无法生成 admin bcrypt hash，服务可能无法启动"
    warn "手动生成方法："
    warn "  1) 安装 bcrypt: pip3 install --user bcrypt"
    warn "  2) 生成 hash: python3 -c \"import bcrypt; print(bcrypt.hashpw(b'admin123', bcrypt.gensalt(rounds=12)).decode())\" > ./secrets/admin-password-hash"
    warn "  3) 重新运行: sh ./start.sh --no-pull"
    die "admin bcrypt hash 生成失败"
  }
fi

# ---------- 5. 启动服务 ----------
info "启动服务..."
$DOCKER_COMPOSE up -d || die "服务启动失败。查看日志：$DOCKER_COMPOSE logs"

# ---------- 6. 等待 Web 健康检查 ----------
info "等待服务就绪（最长 3 分钟）..."

# curl 或 wget 二选一
HEALTH_URL="http://127.0.0.1:${WEB_PORT}/readyz"
HEALTH_CHECK=""
if command -v curl >/dev/null 2>&1; then
  HEALTH_CHECK="curl -fsS --max-time 3 '$HEALTH_URL' >/dev/null 2>&1"
elif command -v wget >/dev/null 2>&1; then
  HEALTH_CHECK="wget -qO- --timeout=3 '$HEALTH_URL' >/dev/null 2>&1"
else
  HEALTH_CHECK=""
fi

max_attempts=90
attempt=0
while [ "$attempt" -lt "$max_attempts" ]; do
  attempt=$((attempt + 1))

  # 先看容器状态
  failed_services=$($DOCKER_COMPOSE ps --format '{{.Service}}:{{.Status}}' 2>/dev/null | grep -iE 'exited|failed|unhealthy' || true)
  if [ -n "$failed_services" ]; then
    # 检查是否是 migrate 一次性容器退出（这是正常的）
    real_failed=$(echo "$failed_services" | grep -v '^migrate:' || true)
    if [ -n "$real_failed" ]; then
      echo ""
      warn "以下服务异常："
      echo "$real_failed" | sed 's/^/    /'
      echo ""
      info "排查步骤："
      info "  1) 查看异常服务日志：$DOCKER_COMPOSE logs --tail 100 <服务名>"
      info "  2) 常见原因：端口冲突、内存不足、secrets 文件权限、数据库初始化失败"
      info "  3) 完全重置：$DOCKER_COMPOSE down -v && rm -rf secrets .env && sh ./start.sh"
      exit 1
    fi
  fi

  if [ -n "$HEALTH_CHECK" ]; then
    if eval "$HEALTH_CHECK"; then
      echo ""
      ok "服务已就绪"
      echo ""
      print_access_info
      exit 0
    fi
  else
    # 没有 curl/wget，只检查容器健康状态
    healthy=$($DOCKER_COMPOSE ps --format '{{.Health}}' 2>/dev/null | grep -c 'healthy' || echo 0)
    total=$($DOCKER_COMPOSE ps --format '{{.Service}}' 2>/dev/null | grep -vc '^migrate$' || echo 0)
    if [ "$healthy" -ge "$total" ] && [ "$total" -gt 0 ]; then
      echo ""
      ok "服务已就绪"
      echo ""
      print_access_info
      exit 0
    fi
  fi

  printf '.'
  sleep 2
done

echo ""
warn "服务启动超时（3 分钟内未通过健康检查）"
info "排查步骤："
info "  1) 查看所有服务状态：$DOCKER_COMPOSE ps"
info "  2) 查看日志：$DOCKER_COMPOSE logs --tail 200"
info "  3) 如 MySQL 初始化慢，可等待后重试：$DOCKER_COMPOSE up -d"
info "  4) 完全重置：$DOCKER_COMPOSE down -v && rm -rf secrets .env && sh ./start.sh"
die "服务启动超时"
