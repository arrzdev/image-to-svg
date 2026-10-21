"""E2 object-shadow census (run 43, measure) — at PIPELINE WORKING RESOLUTION.

For hand-picked shadow ROIs (from audit24 evidence) vs drawn-flat-shadow
controls, measure in the prep image: 10-90% ramp width across the shadow's
outer edge, luminance drop vs background, saturation, and how many quantize
labels the ROI holds (the fragmentation E2 must undo). Populations feed the
E2 idealizer brief with measured gates instead of guesses.

ROIs are normalized (x0,y0,x1,y1) in prep-image space.
"""
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'models/quant-hifi/src'))
import numpy as np
import cv2
from testbed import Testbed

# name -> (input file, ROI, kind)  kind: SOFT (blur halo, E2 target) / DRAWN (control)
CASES = [
    ('appasset-redicon-shadow', 'app-asset.jpg',  (0.62, 0.48, 0.82, 0.68), 'SOFT'),
    ('appasset-music-shadow',   'app-asset.jpg',  (0.68, 0.72, 0.88, 0.92), 'SOFT'),
    ('appasset-arrow-shadow',   'app-asset.jpg',  (0.52, 0.04, 0.72, 0.22), 'SOFT'),
    ('chopchop-stool-under',    'chopchop.png',   (0.05, 0.72, 0.30, 0.85), 'SOFT'),
    ('rabbit-ground-shadow',    'rabbit.jpg',     (0.30, 0.82, 0.85, 0.95), 'DRAWN'),
    ('elephant-ground-shadow',  'elephant.jpg',   (0.30, 0.78, 0.75, 0.92), 'DRAWN'),
    ('monster-hand-lines',      'monster-flat-line.jpg', (0.45, 0.60, 0.85, 0.95), 'DRAWN'),
]

def ramp_widths_roi(gray, n=800, seed=0):
    g = gray.astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, 3); gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, 3)
    mag = np.hypot(gx, gy)
    thr = max(np.percentile(mag, 90), 15.0)
    ys, xs = np.nonzero(mag > thr)
    if len(ys) < 10: return np.array([])
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(ys), min(n, len(ys)), replace=False)
    H, W = g.shape; L = 20
    ts = np.linspace(-L, L, 2 * L + 1)
    out = []
    for i in idx:
        y, x = ys[i], xs[i]
        nx, ny = gx[y, x] / (mag[y, x] + 1e-6), gy[y, x] / (mag[y, x] + 1e-6)
        px, py = x + ts * nx, y + ts * ny
        if not ((px >= 0).all() and (px < W - 1).all() and (py >= 0).all() and (py < H - 1).all()):
            continue
        prof = cv2.remap(g, px.astype(np.float32)[None], py.astype(np.float32)[None], cv2.INTER_LINEAR)[0]
        lo, hi = prof.min(), prof.max()
        if hi - lo < 20: continue
        a, b = lo + .1 * (hi - lo), lo + .9 * (hi - lo)
        ins = (prof >= a) & (prof <= b); c = len(ts) // 2
        if not ins[c]: continue
        l = c
        while l > 0 and ins[l - 1]: l -= 1
        r = c
        while r < len(ts) - 1 and ins[r + 1]: r += 1
        out.append(ts[r] - ts[l])
    return np.array(out)

if __name__ == '__main__':
    print(f"{'case':28s} {'kind':6s} {'res':>9s} {'rampP50':>7s} {'rampP90':>7s} "
          f"{'lumDrop':>7s} {'sat':>5s} {'nLabels':>7s}")
    for name, f, (x0, y0, x1, y1), kind in CASES:
        tb = Testbed(f)
        _, _, _, pp = tb.prep()
        H, W = pp.shape[:2]
        roi = pp[int(y0*H):int(y1*H), int(x0*W):int(x1*W)]
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
        hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
        w = ramp_widths_roi(gray)
        p50, p90 = (np.percentile(w, [50, 90]) if len(w) else (-1, -1))
        # luminance drop: darkest quartile vs brightest quartile of the ROI
        qs = np.percentile(gray, [25, 75])
        labels, centers = tb.labels()
        lroi = labels[int(y0*H):int(y1*H), int(x0*W):int(x1*W)]
        # count labels covering >2% of the ROI
        vals, cts = np.unique(lroi, return_counts=True)
        n_sig = int((cts / cts.sum() > 0.02).sum())
        print(f"{name:28s} {kind:6s} {W}x{H} {p50:7.1f} {p90:7.1f} "
              f"{qs[1]-qs[0]:7.0f} {hsv[...,1].mean():5.0f} {n_sig:7d}")
