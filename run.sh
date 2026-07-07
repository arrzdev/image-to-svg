#!/usr/bin/env bash
# Launch the version-testing frontend: http://127.0.0.1:8000
set -euo pipefail
cd "$(dirname "$0")"
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:/usr/local/lib:${DYLD_FALLBACK_LIBRARY_PATH:-}"
PORT="${PORT:-8000}"
exec .venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port "$PORT" "$@"
