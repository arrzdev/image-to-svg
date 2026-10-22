"""edge-11 — synthesized strokes over buckets (USER architecture 2026-07-12).

Lines are detected STRUCTURALLY (thin + uniform + not-a-blend, any colour)
and REBUILT from their centerline + width profile instead of traced — pixel
noise cannot reach the stroke layer. Buckets as edge-10 (RAG merge, seam glue,
arcfit smoothing). Reference edges are topology-only. The Edge Lab tab runs
this same module.

Contract: run(image_path, params) -> svg string.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"


def run(image_path: str, params: dict | None = None) -> str:
    p = str(_SRC)
    if p not in sys.path:
        sys.path.insert(0, p)
    from pipeline import run as _run
    return _run(image_path, params)


if __name__ == "__main__":
    out = run(sys.argv[1])
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(out)
    else:
        sys.stdout.write(out)
