"""vectorark-1 — classical VectorArk/Layered fusion lineage (2026-07-10).

New lineage prototyped from the deep-read of arXiv 2605.24398 (VectorArk) and
2406.05404 (Layered Vectorization): bilateral simplification cascade decides
topology, masks layer back-to-front by the Layered containment rules, boundaries
fit with line+circular-arc rounded polygons, fills = visible-pixel source
medians. Targets the three measured tilecmp gaps of quant-12 (UNDER-RESOLVE /
FITTER / COLOR) structurally rather than by parameter tuning.

Contract: run(image_path, params) -> svg string (same as other lineages).
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"


def run(image_path: str, params: dict | None = None) -> str:
    p = str(_SRC)
    if p not in sys.path:
        sys.path.insert(0, p)
    from pipeline import run_pipeline
    return run_pipeline(image_path, params)


if __name__ == "__main__":
    out = run(sys.argv[1])
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(out)
    else:
        sys.stdout.write(out)
