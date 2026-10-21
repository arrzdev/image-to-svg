"""E5 teeth census (run 57) — regularity of the monster's tooth zigzag.

Extract the mouth's white component from ORIGINAL raster / OURS(v11) render /
RECRAFT render at 2048; trace the tooth-edge profile; find zigzag extrema =
tooth tips/valleys; report per-source stats: tooth count, spacing mean/CV,
depth mean/CV. Hypothesis (VISION item 6): recraft's teeth are MORE regular
than the original; ours are LESS. The gap defines it26's E5 acceptance.
"""
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'models/quant-hifi/src'))
import numpy as np
import cv2
from PIL import Image
from render import svg_to_rgb

RES = 2048
# mouth bbox (normalized, from audit24 crops)
X0, Y0, X1, Y1 = 0.40, 0.22, 0.64, 0.36

def mouth_profile(rgb):
    crop = rgb[int(Y0*RES):int(Y1*RES), int(X0*RES):int(X1*RES)]
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    white = (gray > 128).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(white, 8)
    if n < 2:
        return None
    # biggest white component fully inside the crop = the mouth
    inner = [i for i in range(1, n)
             if stats[i, 0] > 2 and stats[i, 1] > 2
             and stats[i, 0] + stats[i, 2] < white.shape[1] - 2]
    if not inner:
        return None
    mi = max(inner, key=lambda i: stats[i, 4])
    mask = (lab == mi)
    H, W = mask.shape
    # top-edge profile: highest white y per column (teeth hang down from the
    # upper lip, so the zigzag is the white component's TOP boundary)
    ys = np.array([np.min(np.nonzero(mask[:, x])[0]) if mask[:, x].any() else -1
                   for x in range(W)], float)
    cv2.imwrite(f'/tmp/teeth_mask_{id(mask) % 100}.png', mask.astype(np.uint8) * 255)
    ok = ys >= 0
    return ys, ok

def zigzag_stats(name, rgb):
    r = mouth_profile(rgb)
    if r is None:
        print(f'{name:10s}  no mouth found'); return
    ys, ok = r
    xs = np.nonzero(ok)[0]
    y = ys[xs]
    # smooth slightly to kill 1px jitter, then find local extrema
    k = 5
    ysm = np.convolve(y, np.ones(k)/k, 'same')
    tips, valleys = [], []
    for i in range(3, len(ysm) - 3):
        w = ysm[i-3:i+4]
        if ysm[i] == w.max() and (w.max() - w.min()) > 4: tips.append(i)
        if ysm[i] == w.min() and (w.max() - w.min()) > 4: valleys.append(i)
    def dedupe(idx, min_gap=8):
        out = []
        for i in idx:
            if not out or i - out[-1] > min_gap: out.append(i)
        return out
    tips, valleys = dedupe(tips), dedupe(valleys)
    if len(tips) < 3:
        print(f'{name:10s}  tips={len(tips)} (too few to measure)'); return
    sp = np.diff([xs[i] for i in tips])
    # tooth depth: tip y minus neighboring valley y
    depths = []
    for t in tips:
        vs = [v for v in valleys if abs(v - t) < 40]
        if vs:
            depths.append(ysm[t] - min(ysm[v] for v in vs))
    sp_cv = np.std(sp)/np.mean(sp) if len(sp) > 1 else 0
    d_cv = np.std(depths)/np.mean(depths) if len(depths) > 1 else 0
    print(f'{name:10s}  teeth={len(tips):2d}  spacing px: mean {np.mean(sp):5.1f} CV {sp_cv:.2f}   '
          f'depth px: mean {np.mean(depths):5.1f} CV {d_cv:.2f}')

if __name__ == '__main__':
    im = Image.open(ROOT/'data/inputs/monster-flat-line.jpg').convert('RGB')
    bg = Image.new('RGB', (RES, RES), 'white')
    r = min(RES/im.width, RES/im.height)
    im2 = im.resize((round(im.width*r), round(im.height*r)), Image.LANCZOS)
    bg.paste(im2, ((RES-im2.width)//2, (RES-im2.height)//2))
    zigzag_stats('ORIGINAL', np.asarray(bg))
    ours = svg_to_rgb((ROOT/'models/v11/examples/monster-flat-line.svg').read_text(), RES, RES).astype(np.uint8)
    zigzag_stats('OURS-v11', ours)
    rec = svg_to_rgb((ROOT/'data/targets/monster-flat-line.svg').read_text(), RES, RES).astype(np.uint8)
    zigzag_stats('RECRAFT', rec)
