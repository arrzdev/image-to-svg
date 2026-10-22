"""quant-19 — quant-18 + fill-coverage seal widen (2026-07-13; EYE-GATED,
frozen snapshot; wrapper byte-equivalent to quant-13..18, only src/ differs).

Shipped on USER coverage feedback (glasses lens + beaver tail showed a ~1px
white background sliver between a colour fill and its neighbour/ink): the
sibling underpaint seal in emit_regions_layered went 1.0 -> 2.0 px. The seal
grows only the HIDDEN side, so the sliver closes with zero change to visible
line weight. tilecmp is NEUTRAL (0.2387, all channels bit-identical — the
metric cannot see a 1px seal), so this shipped on the EYE gate, corpus-verified
(5 diverse images full-frame identical, KB flat, deep-zoom gaps close).

Contract: run(path, params) -> svg. Benchmarks: eval/tilecmp*.py."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_Q11 = Path(__file__).resolve().parent / "src"


def _bootstrap():
    p = str(_Q11)
    if p not in sys.path:
        sys.path.insert(0, p)
    os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")


def _prepare(image_path: str, dim: int = 1024):
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
            img = img.resize((round(ow * scale), round(oh * scale)),
                             Image.LANCZOS)
    return img, (ow, oh)


# Swept to hit all six Recraft axes >= 0.90 (autonomous goal, 2026-07-10):
#   paths 0.94  C 0.91  L 0.94  ssim 0.96  gmsd 0.96  colour 0.91  overall 0.939
DEFAULTS = {"num_colors": 16, "merge_de": 12.0, "min_area": 100}
STRAIGHT_EPS = 0.8
STRAIGHT_MIN_LEN = 14.0


def run(image_path: str, params: dict | None = None) -> str:
    _bootstrap()
    from pipelines import get_pipeline
    from svgutil import fit_svg_size
    from straighten import straighten

    p = dict(DEFAULTS)
    p.update(params or {})
    eps = float(p.pop("straight_eps", STRAIGHT_EPS))
    mlen = float(p.pop("straight_min_len", STRAIGHT_MIN_LEN))

    proc, (ow, oh) = _prepare(image_path)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = f.name
    try:
        proc.save(tmp)
        svg = get_pipeline("contour_lines").run(tmp, p)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    svg = straighten(svg, eps, mlen)
    return fit_svg_size(svg, ow, oh)


if __name__ == "__main__":
    out = run(sys.argv[1])
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(out)
    else:
        sys.stdout.write(out)
