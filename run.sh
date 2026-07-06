#!/usr/bin/env bash
# Launch the image->svg playground.
set -euo pipefail
cd "$(dirname "$0")"

# Homebrew libs (cairo) for SVG rendering. render.py also sets this, but export
# here too so it is present before the interpreter starts.
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:/usr/local/lib:${DYLD_FALLBACK_LIBRARY_PATH:-}"

# Optional: enable AI preprocessing (nano banana / Gemini 2.5 Flash Image).
#   export GEMINI_API_KEY=...        # your key
#   export GEMINI_IMAGE_MODEL=gemini-2.5-flash-image   # (default, the cheap one)

PORT="${PORT:-8000}"
exec .venv/bin/python -m uvicorn app:app --app-dir backend --host 127.0.0.1 --port "$PORT" "$@"
