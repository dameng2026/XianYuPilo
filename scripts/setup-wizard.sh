#!/usr/bin/env bash
# Setup wizard for first-time users on Linux/macOS.
# Checks Docker, generates random secrets, validates .env, and starts compose.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[错误]${NC} $1"; }

# Step 1: Check Docker
log_info "检查 Docker..."
if ! command -v docker >/dev/null 2>&1; then
  log_error "Docker 未安装。请先安装 Docker：https://docs.docker.com/get-docker/。安装完成后重新运行本脚本。"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  log_error "Docker Compose v2 不可用。请安装 Docker Compose v2：https://docs.docker.com/compose/install/。"
  exit 1
fi
log_info "Docker 已就绪。"

# Step 2: Check .env
if [ ! -f ".env" ]; then
  log_info ".env 不存在，从 .env.example 复制..."
  cp .env.example .env
fi

# Step 3: Ensure ./secrets directory with random values
SECRETS_DIR="./secrets"
if [ ! -d "$SECRETS_DIR" ]; then
  log_info "创建 $SECRETS_DIR 目录并生成随机 secrets..."
  mkdir -p "$SECRETS_DIR"
  chmod 700 "$SECRETS_DIR"

  gen_secret() {
    openssl rand -base64 48 | tr -d '\n' | head -c "$1"
  }

  # bcrypt hash for default password "admin123" (cost 12). User should change later.
  # We write a placeholder hash; user must regenerate with their own password.
  echo '$2b$12$placeholder.admin.password.hash.replace.me' > "$SECRETS_DIR/admin-password-hash"
  gen_secret 32 > "$SECRETS_DIR/mysql-root-password"
  gen_secret 32 > "$SECRETS_DIR/mysql-app-password"
  gen_secret 32 > "$SECRETS_DIR/mysql-migrate-password"
  gen_secret 32 > "$SECRETS_DIR/redis-password"
  gen_secret 48 > "$SECRETS_DIR/jwt-secret"
  gen_secret 48 > "$SECRETS_DIR/cookie-crypto-secret"
  gen_secret 32 > "$SECRETS_DIR/internal-api-token"
  # Optional integrations: empty files
  : > "$SECRETS_DIR/commercial-backend-access-token"
  : > "$SECRETS_DIR/embedding-api-key"
  : > "$SECRETS_DIR/ai-provider-api-key"
  : > "$SECRETS_DIR/amap-api-key"
  chmod 600 "$SECRETS_DIR"/*
  log_warn "已在 $SECRETS_DIR 生成随机 secrets。"
  log_warn "admin-password-hash 是占位符，请用 bcrypt cost>=12 重新生成你自己的密码 hash："
  log_warn "  python -c \"import bcrypt; print(bcrypt.hashpw(b'YOUR_PASSWORD', bcrypt.gensalt(rounds=12)).decode())\" > $SECRETS_DIR/admin-password-hash"
fi

# Step 4: Validate compose config
log_info "校验 docker compose 配置..."
if ! docker compose config --quiet; then
  log_error "docker compose 配置校验失败。请检查 .env 文件是否填写完整。"
  exit 1
fi
log_info "配置校验通过。"

# Step 5: Check port 8080
if command -v lsof >/dev/null 2>&1; then
  if lsof -i :8080 -sTCP:LISTEN >/dev/null 2>&1; then
    log_warn "端口 8080 已被占用。请在 .env 中修改 WEB_PORT 后重试。"
    log_warn "或运行：WEB_PORT=8081 sh ./start.sh"
    exit 1
  fi
fi

# Step 6: Start
log_info "启动 docker compose（首次会拉取/构建镜像，请耐心等待）..."
docker compose up -d --wait

log_info "✅ 启动成功！"
log_info "访问 http://localhost:${WEB_PORT:-8080}"
log_info "默认账号: ${ADMIN_USERNAME:-admin}"
log_warn "默认密码请参考 $SECRETS_DIR/admin-password-hash 生成时使用的原文。"
