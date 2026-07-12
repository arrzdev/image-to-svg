"""quant-18 — quant-17 + the run-75 BATCH (2026-07-13; frozen snapshot of
the live tree, self-contained src/; wrapper byte-equivalent to quant-13..17).

Three mechanisms shipped as one gated batch (+0.0024, orchestrator-assembled;
each solo eye-verified, combination eye-verified at interaction spots):
  * PEN CALIBRATION (it75, the headline): width_scale=0.85 had been eye-tuned
    to track ELEPHANT — which routes ZERO ink through the stroke system at
    current HEAD. Every stroke ever emitted was 15% thinner than source
    against a phantom calibration target (we covered 87.7% of source ink px;
    Recraft covers 97.6%). Now: per-image source-anchored pen scale
    clip(gw_src/gw, ws, 1.0) behind three independently-margined evidence
    gates (fires chopchop/crystals/fox/mountain/shield at 0.93-0.97;
    pizza/rabbit held out by measured fringe-overhang — a blind global
    retune was rejected for eye-verified pizza gap-pinch).
  * TONE RE-ANCHOR EXTENSION (it74): shared outside-ink-candidacy predicate
    on parent + minted tone — crystals crimson band (dE 17.8) and kin fixed.
  * DARK-RING CARVE (it71): thin dark ribbons minted from fill-grade parents
    (enclosure-gated) — shield rivet rings, mountain ridge streak.

Corpus tilecmp 0.2411 -> 0.2387 (color 0.1677 -> 0.1610, COLOR share
18.9 -> 17.2); chopchop -0.0195 (USER benchmark, biggest single-stem win of
segment 3); 6 stems byte-identical. Segment 3 total: 0.2487 -> 0.2387 (-4.0%).

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
