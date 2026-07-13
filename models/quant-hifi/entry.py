"""quant-hifi — ADAPTIVE-FIDELITY FORK (USER 2026-07-14: "our outputs are too
smoothed/simplified... fork things even if benchmarks say worse").

The metric-tuned lineage (quant-24) runs every image at work-dim 1024, which
OVER-SMOOTHS detailed illustrations: measured points/KB are 0.55-0.71x Recraft
on chopchop/crystals/fox (we throw away 30-45% of the drawn detail). But naively
running everything at native 2048 DESTROYS flat/geometric art (shield/logo/
elephant become 10-77x over-detailed). Recraft matches fidelity to CONTENT.

This fork does the same: an image DETAIL signal (Canny edge density, corr +0.83
with Recraft's own point budget) picks the working resolution + detail params.
Detailed art (edge_density >= 0.065: chopchop 0.085, crystals 0.078, fox 0.065)
renders at native 2048 with finer quantisation (more tone bands, smaller
min_area) -> points/KB toward Recraft, tilecmp chopchop +0.027 / crystals +0.049.
Flat/geometric art (< 0.065) keeps the tuned 1024 path = byte-identical to
quant-24. Bigger files ON PURPOSE where the source has the detail to justify it.

Contract: run(path, params) -> svg.
"""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"


def _edge_density(bgr) -> float:
    import cv2
    g = cv2.cvtColor(cv2.resize(bgr, (512, 512)), cv2.COLOR_BGR2GRAY)
    return float(cv2.Canny(g, 50, 150).mean() / 255.0)


def run(image_path: str, params: dict | None = None) -> str:
    p = str(_SRC)
    if p not in sys.path:
        sys.path.insert(0, p)
    os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")
    import cv2
    import numpy as np
    from PIL import Image
    from pipelines import get_pipeline
    from svgutil import fit_svg_size
    from straighten import straighten

    bgr = cv2.imread(image_path, cv2.IMREAD_COLOR)
    ed = _edge_density(bgr) if bgr is not None else 0.0
    if ed < 0.065:
        # flat / geometric / low-detail: the tuned 1024 path is correct and
        # already matches Recraft's low point budget — delegate to quant-24
        # verbatim (byte-identical; this fork ONLY changes detailed art).
        import importlib.util as _u
        _s = _u.spec_from_file_location(
            "_q24", str(Path(__file__).resolve().parent.parent
                        / "quant-24" / "entry.py"))
        _m = _u.module_from_spec(_s)
        _s.loader.exec_module(_m)
        return _m.run(image_path, params)

    dim = 2048
    pr = {"num_colors": 24, "merge_de": 8.0, "min_area": 40}
    if params:
        pr.update(params)

    img = Image.open(image_path)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        img = Image.alpha_composite(Image.new("RGBA", img.size,
                                              (255, 255, 255, 255)), img)
    img = img.convert("RGB")
    ow, oh = img.size
    s = dim / max(ow, oh)
    if s != 1.0:
        img = img.resize((round(ow * s), round(oh * s)), Image.LANCZOS)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = f.name
    try:
        img.save(tmp)
        svg = get_pipeline("contour_lines").run(tmp, pr)
    finally:
        os.unlink(tmp)
    svg = straighten(svg, 0.8, 14)
    return fit_svg_size(svg, ow, oh)


if __name__ == "__main__":
    out = run(sys.argv[1])
    (Path(sys.argv[2]).write_text(out) if len(sys.argv) > 2
     else sys.stdout.write(out))
