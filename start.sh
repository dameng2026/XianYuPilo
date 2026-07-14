#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT_DIR"

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env 2>/dev/null || true
  echo "Created .env from .env.example. Fill every REQUIRED blank, then run start.sh again." >&2
  exit 2
fi

exec sh "$ROOT_DIR/scripts/verify-production.sh" "$@"
