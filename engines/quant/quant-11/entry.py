"""Stable version entry point.

Every models/vN/entry.py exposes the same contract so the CLI and frontend can
route between versions non-destructively, whatever the internal code layout:

    run(image_path: str, params: dict | None = None) -> str   # SVG text

One version per process: entry prepends its own src/ to sys.path, and the
module names inside src/ (pipelines, contours_exp, ...) are shared across
versions. The root CLI (run_model.py) isolates every call in a subprocess.

Requires the repo venv (svgcore Rust extension is pip-installed there) and
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib on macOS for cairo rendering.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"


def _bootstrap():
    p = str(_SRC)
    if p not in sys.path:
        sys.path.insert(0, p)
    os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")


def _prepare(image_path: str, dim: int = 1024):
    """White-flattened raster, longest side `dim` (matching the app's prep).

    Upscaling is skipped for flat/crisp art (Lanczos ringing around hard edges
    gets traced as junk points) — same gate the engine used.
    """
    from PIL import Image
    import numpy as np

    img = Image.open(image_path)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img)
    img = img.convert("RGB")
    ow, oh = img.size

    scale = dim / max(ow, oh)
    if scale < 1.0:
        img = img.resize((round(ow * scale), round(oh * scale)), Image.LANCZOS)
    elif scale > 1.0:
        allow_up = True
        try:
            from imgstats import analyze
            allow_up = analyze(np.asarray(img))["kind"] != "flat"
        except Exception:
            allow_up = False
        if allow_up:
            img = img.resize((round(ow * scale), round(oh * scale)), Image.LANCZOS)
    return img, (ow, oh)


def run(image_path: str, params: dict | None = None) -> str:
    """Vectorize `image_path` with this version's contour_lines pipeline."""
    _bootstrap()
    from pipelines import get_pipeline
    from svgutil import fit_svg_size

    proc, (ow, oh) = _prepare(image_path)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = f.name
    try:
        proc.save(tmp)
        svg = get_pipeline("contour_lines").run(tmp, dict(params or {}))
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return fit_svg_size(svg, ow, oh)


if __name__ == "__main__":
    out = run(sys.argv[1])
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(out)
    else:
        sys.stdout.write(out)
