"""Rasterize an SVG string back to a numpy RGB image for fidelity metrics."""
from __future__ import annotations

import io
import os

# cairocffi resolves libcairo via dlopen at import time, reading the live
# environment. Homebrew installs to /opt/homebrew/lib (Apple Silicon) or
# /usr/local/lib (Intel), neither on the default dyld search path. Add them
# before importing cairosvg so this works regardless of how the app is launched.
for _libdir in ("/opt/homebrew/lib", "/usr/local/lib"):
    if os.path.isdir(_libdir):
        for _var in ("DYLD_FALLBACK_LIBRARY_PATH", "LD_LIBRARY_PATH"):
            cur = os.environ.get(_var, "")
            if _libdir not in cur.split(os.pathsep):
                os.environ[_var] = (_libdir + os.pathsep + cur) if cur else _libdir

import shutil
import subprocess
import tempfile

import numpy as np
from PIL import Image

# resvg (Rust/tiny-skia) renders our multi-MB traced SVGs ~13x faster than
# cairosvg with near-identical pixels (mean |diff| 0.1/255). Use it when
# installed (brew install resvg); fall back to cairosvg otherwise.
_RESVG = shutil.which("resvg")


def _render_resvg(svg: str, width: int, height: int) -> np.ndarray:
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
        f.write(svg)
        svg_path = f.name
    png_path = svg_path + ".png"
    try:
        subprocess.run(
            [_RESVG, svg_path, png_path, "--width", str(width),
             "--height", str(height), "--background", "white"],
            check=True, capture_output=True,
        )
        img = Image.open(png_path).convert("RGB")
        # resvg derives the aspect-fit dimension with its own rounding, which
        # can differ from the caller's by 1px on non-square images — enforce
        # the exact requested size so metric arrays always align.
        if img.size != (width, height):
            img = img.resize((width, height), Image.BILINEAR)
        return np.asarray(img)
    finally:
        for p in (svg_path, png_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def _render_cairo(svg: str, width: int, height: int) -> np.ndarray:
    import cairosvg
    png_bytes = cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        output_width=width,
        output_height=height,
        background_color="white",
    )
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    return np.asarray(img)


def svg_to_rgb(svg: str, width: int, height: int) -> np.ndarray:
    """Render SVG to an (H, W, 3) uint8 RGB array at the given size.

    Transparent regions are composited over white, matching how these SVGs are
    typically viewed and how the source raster (opaque) looks.
    """
    if _RESVG:
        try:
            return _render_resvg(svg, width, height)
        except Exception:
            pass  # e.g. resvg rejects an exotic feature; cairo is the safety net
    return _render_cairo(svg, width, height)
