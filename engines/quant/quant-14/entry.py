"""quant-14 — quant-13 + it9 wander-erasure (run 65, 2026-07-12; frozen
snapshot of the live tree, self-contained src/; wrapper byte-equivalent to
quant-13's — only src/ differs).

Shipped change (orchestrator-adjudicated; the first keep under the gate's
recalibration to the MEASURED 0.0000 noise floor, MIN_GAIN 0.004 -> 0.0015;
eye-audited before ship):
  * WANDER ERASURE — the FITTER's residual lumpiness was measured to be a
    6-30px-wavelength, ~1-2px-amplitude wander of the k-means label boundary
    (the iso-line through a soft ramp has no pixel-exact home), NOT the 1px
    crack staircase. Fix at the polyline, band-limited: a coarse reference
    fit (coordinates shrunk 0.5x, so sub-2px wander cannot mint polygon
    segments) defines low-frequency truth; only the HIGH-frequency signed
    residual about it is removed (window-21 moving-average split). Raw
    >=25deg kinks corner-protected, corrections leash-clamped 0.9px, curves
    <40pts untouched, FLAT art scene-gated off (drawn ink is never
    re-idealized). Downstream anchors/fits unchanged.

tilecmp corpus 0.2487 -> 0.2457 (census -0.0068, flow -0.0027, color +0.0007
< eps). Wins: shield -0.0159, app-asset -0.0146 (eye: rim wobble + shadow-
fringe teeth gone); chopchop +0.0023 eye-invisible; flat art untouched (0.0).

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
