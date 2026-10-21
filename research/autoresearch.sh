#!/usr/bin/env bash
# LOCKED eval harness — the regression SANITY CHECK, not the keep/discard gate.
#
# Per research/docs/PROJECT_SPEC.md §4 the real keep/discard decision is the agent's EYE
# verdict on tb.crops({'new':…, 'prev':…, 'recraft': tb.target()}). This script
# only emits `METRIC name=number` lines for the plugin dashboard and catches
# external regressions AFTER an eye verdict already passed. DO NOT EDIT during
# the loop (see research/autoresearch.md "Off Limits") — an agent that edits its own
# scorer will game it.
#
# Usage: ./autoresearch.sh [FOCUS_BASENAME] [SEED]
#   FOCUS defaults to `autoresearch.focus` contents, else 'elephant'.
set -euo pipefail

cd "$(dirname "$0")/.."   # repo root; LIVE engine = models/quant-hifi/src

# Fast fail: syntax-check the pipeline entry + harness before the slow render.
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m py_compile \
  models/quant-hifi/src/ar_eval.py models/quant-hifi/src/contours_exp.py models/quant-hifi/src/strokes.py

# Per-experiment wall-clock cap (kill + non-zero exit = crash). `timeout` from
# coreutils (gtimeout on macOS/brew); fall back to plain run if absent.
TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"
RUN=(env DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python models/quant-hifi/src/ar_eval.py "$@")
if [ -n "$TIMEOUT_BIN" ]; then
  "$TIMEOUT_BIN" 300 "${RUN[@]}"
else
  "${RUN[@]}"
fi
