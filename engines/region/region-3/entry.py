"""region-3 entry point — idealize-first + dedicated ink layer.

Same contract as every other version (run(image_path, params=None) -> svg).
Reuses engines/quant/quant-11/src for the geometry/emission backend. Does NOT
hard-downscale to 1024 (R1); works at its own cap and upscales small art.
See src/exp_pipeline.py and research/docs/BLUEPRINT.md.
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
