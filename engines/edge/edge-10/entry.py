"""edge-10 — the Edge Lab pipeline frozen as a model (USER recipe 2026-07-11).

Boundary-first, resurrected: two independent detectors — sensitive bucket
segmentation (dE 5, bilateral-1, RAG merge 22) + LCh ink extraction (L*<30,
no chroma cap, ribbons drawn on top) — with seam glue (dilated fill overlap +
transition-ribbon absorption). See src/pipeline.py; the Edge Lab web tab runs
this same module, so lab tinkering IS model behaviour.

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
