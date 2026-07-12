"""quant-16 — quant-15 + it67 graft-strokes (runs 67-68, 2026-07-12; frozen
snapshot of the live tree, self-contained src/; wrapper byte-equivalent to
quant-13/14/15's — only src/ differs).

Shipped change (worktree agent x2 waves, orchestrator-integrated combination
gate + own-render eye audits):
  * STRUCTURAL-LINE RESCUE (stroke_graft.py, the edge-11 graft): thin dark
    structural lines the label chain LOSES (pizza-box checker separators,
    apex roof diagonal, underline bar) are re-detected from the source
    raster (morphological blackhat), evidence-gated (provably-lost dE vs
    rendered fill, thin, uniform width, darker than BOTH flanks, straight
    runs at corners), and SYNTHESIZED as constant-width round-cap strokes
    painted last; fills tuck underneath. Dash completion marches through
    source-dark evidence and SUPPRESSES the old half-kept dash strokes
    (nothing emits twice). Wave-2: per-piece (corner-split) sagitta for
    completions + curved structural rescue behind an in-image context
    precondition (>=3 pass-1 accepts) — structurally inert on organic stems
    (measured 0 accepts on rabbit/fox/chopchop/elephant).

Fires ONLY on pizza-box (0.3159 -> 0.2982; edge-11's whole-engine reference
was 0.2949); 10/10 other corpus stems BYTE-IDENTICAL. Corpus tilecmp
0.2442 -> 0.2426 (census -0.0003, flow -0.0019, color -0.0026). History: the
run-67 combination first landed +0.0014 (0.0001 below the bar) and was
REVERTED, then wave-2 earned the margin (+0.0020 standalone) instead of the
gate bending.

Contract: run(path, params) -> svg. Benchmarks: research/design/tilecmp*.py."""
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
