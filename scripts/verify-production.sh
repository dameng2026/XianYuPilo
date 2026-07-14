#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENV_FILE=${ENV_FILE:-"$ROOT_DIR/.env"}
WAIT_TIMEOUT_SECONDS=${WAIT_TIMEOUT_SECONDS:-300}

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "Python 3 is required for the secret-safe production verifier." >&2
  exit 127
fi

case "${1:-}" in
  "")
    exec "$PYTHON" "$ROOT_DIR/scripts/verify_production.py" \
      --env-file "$ENV_FILE" --wait-timeout "$WAIT_TIMEOUT_SECONDS"
    ;;
  --no-build)
    exec "$PYTHON" "$ROOT_DIR/scripts/verify_production.py" \
      --env-file "$ENV_FILE" --wait-timeout "$WAIT_TIMEOUT_SECONDS" --no-build
    ;;
  *)
    echo "Usage: scripts/verify-production.sh [--no-build]" >&2
    exit 64
    ;;
esac
