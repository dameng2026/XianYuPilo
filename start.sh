#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT_DIR"

# First-time setup: if .env or ./secrets missing, run the wizard
if [ ! -f ".env" ] || [ ! -d "./secrets" ]; then
  echo "检测到首次使用，启动设置向导..."
  sh "$ROOT_DIR/scripts/setup-wizard.sh"
  exit $?
fi

exec sh "$ROOT_DIR/scripts/verify-production.sh" "$@"
