"""EXPERIMENTAL version entry point — same contract as models/vN/entry.py.

    run(image_path, params=None) -> str   # SVG text

This is the "how I think Recraft works" architecture (geometry-before-colour,
idealize-before-vectorize). See src/exp_pipeline.py and
research/docs/BLUEPRINT.md. It reuses models/v11/src for the geometry/
emission backend, so both this src/ and v11/src/ go on the path.

Unlike the vN entries, this one does NOT hard-downscale to 1024 (R1): the
pipeline works at its own (higher) cap and upscales small art toward it.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"


def _bootstrap():
    p = str(_SRC)
    if p not in sys.path:
        sys.path.insert(0, p)
    os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")


def run(image_path: str, params: dict | None = None) -> str:
    _bootstrap()
    from exp_pipeline import run_pipeline
    from svgutil import fit_svg_size
    from PIL import Image

    with Image.open(image_path) as im:
        ow, oh = im.size
    svg = run_pipeline(image_path, dict(params or {}))
    return fit_svg_size(svg, ow, oh)


if __name__ == "__main__":
    out = run(sys.argv[1])
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(out)
    else:
        sys.stdout.write(out)
