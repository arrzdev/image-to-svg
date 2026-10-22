"""recraft_gap.py — ours-vs-Recraft SVG-render distance (USER-requested direction gauge).

Rasterizes BOTH SVGs (ours + Recraft's) at the same resolution and compares
render-to-render: global SSIM + mean deltaE, plus a per-tile (grid) breakdown
that ranks the WORST tiles — mechanizing the "compare every zoomed grid
square" review. Never compares against original pixels (that metric rewards
noise-copying; see research/loop/autoresearch.md).

SPOT-FINDER / SECONDARY SIGNAL ONLY. The keep/discard gate remains the eye
(PROJECT_SPEC §4). A perfect score means "identical to Recraft" — it cannot
detect being BETTER than Recraft.

Usage:
  DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python \
    eval/recraft_gap.py [target ...]   # default: all with recraft SVGs
"""
import sys, pathlib
# ALWAYS measure the LIVE engine (engines/quant/quant-hifi).
# (Harness-maintenance fix 2026-07-10, noted in worklog: this previously pinned
# models/v5/src, so full-table runs measured STALE v5 code once the live tree
# moved on — numbers after ~run 33 with svg_ours=None are suspect.)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'engines/quant/quant-hifi/src'))
import numpy as np
from skimage.metrics import structural_similarity as ssim
from skimage.color import rgb2lab, deltaE_ciede2000
from testbed import Testbed
from pipelines import get_pipeline
from svgutil import fit_svg_size
from render import svg_to_rgb

RES, GRID = 1024, 4  # 4x4 tiles

def gap(name, svg_ours=None):
    rec_p = pathlib.Path(f'data/targets/{name}.svg')
    if not rec_p.exists():
        return None
    if svg_ours is None:
        pp, _, (ow, oh), _ = Testbed(name).prep()
        svg_ours = fit_svg_size(get_pipeline('contour_lines').run(pp, {}), ow, oh)
    a = svg_to_rgb(svg_ours, RES, RES).astype(np.float64)
    b = svg_to_rgb(rec_p.read_text(), RES, RES).astype(np.float64)
    s_all = ssim(a, b, channel_axis=2, data_range=255.0)
    de_all = float(deltaE_ciede2000(rgb2lab(a/255.0), rgb2lab(b/255.0)).mean())
    t = RES // GRID
    tiles = []
    for gy in range(GRID):
        for gx in range(GRID):
            ta, tb = a[gy*t:(gy+1)*t, gx*t:(gx+1)*t], b[gy*t:(gy+1)*t, gx*t:(gx+1)*t]
            if ta.std() < 1 and tb.std() < 1:  # both flat/empty
                continue
            s = ssim(ta, tb, channel_axis=2, data_range=255.0)
            tiles.append((s, gx, gy))
    tiles.sort()
    return s_all, de_all, tiles

def worst_spots(tiles, k=3):
    """Worst-k tiles as (y,x)@4096 crop spots for Testbed.crops (tile centers)."""
    t4 = 4096 // GRID
    return [(max(0, gy * t4 + t4 // 2 - 210), max(0, gx * t4 + t4 // 2 - 210))
            for _, gx, gy in tiles[:k]]


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '--spots']
    show_spots = '--spots' in sys.argv[1:]
    names = args or sorted(p.stem for p in pathlib.Path('data/targets').glob('*.svg'))
    print(f"{'target':20s} {'rSSIM':>6s} {'rdE':>6s}  worst tiles (gx,gy@4x4: ssim)")
    for n in names:
        r = gap(n)
        if r is None:
            print(f'{n:20s}  (no recraft target)'); continue
        s, de, tiles = r
        worst = '  '.join(f'({gx},{gy}):{ts:.2f}' for ts, gx, gy in tiles[:3])
        print(f'{n:20s} {s:6.3f} {de:6.2f}  {worst}')
        if show_spots:
            print(f'{"":20s} crop spots (y,x)@4096: {worst_spots(tiles)}')
