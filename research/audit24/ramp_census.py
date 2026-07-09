"""Edge ramp-width census (run 42, measure) — the E1/E2 population data.

For each input: sample strong edges, profile intensity along the gradient
normal, measure the 10-90% transition width in px (at native resolution).
Hypothesis: drawn/flat art edges are ~1-3px (AA only); soft shadows, blur
halos and gradients live in a >4px tail — the tail is exactly where audit24
found shrapnel (E1) and shadow blobs (E2). Output: per-target percentiles +
tail share, to set measured (not guessed) thresholds for transition
ownership and shadow idealization.
"""
import pathlib, sys
import numpy as np
import cv2

ROOT = pathlib.Path(__file__).resolve().parents[2]

def ramp_widths(img_gray, n_samples=4000, seed=0):
    g = img_gray.astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    thr = np.percentile(mag, 97)
    ys, xs = np.nonzero(mag > max(thr, 20.0))
    if len(ys) == 0:
        return np.array([])
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(ys), size=min(n_samples, len(ys)), replace=False)
    H, W = g.shape
    L = 12  # half-profile length in px
    ts = np.linspace(-L, L, 2 * L + 1)
    widths = []
    for i in idx:
        y, x = ys[i], xs[i]
        nx, ny = gx[y, x] / (mag[y, x] + 1e-6), gy[y, x] / (mag[y, x] + 1e-6)
        px = x + ts * nx
        py = y + ts * ny
        ok = (px >= 0) & (px < W - 1) & (py >= 0) & (py < H - 1)
        if ok.sum() < len(ts):
            continue
        prof = cv2.remap(g, px.astype(np.float32)[None, :],
                         py.astype(np.float32)[None, :], cv2.INTER_LINEAR)[0]
        lo, hi = prof.min(), prof.max()
        if hi - lo < 25:  # too weak to be a real edge profile
            continue
        a, b = lo + 0.1 * (hi - lo), lo + 0.9 * (hi - lo)
        inside = (prof >= a) & (prof <= b)
        # longest contiguous run of 'inside' crossing the center
        c = len(ts) // 2
        l = c
        while l > 0 and inside[l - 1]:
            l -= 1
        r = c
        while r < len(ts) - 1 and inside[r + 1]:
            r += 1
        if not inside[c]:
            continue
        widths.append(ts[r] - ts[l])
    return np.array(widths)

if __name__ == '__main__':
    print(f"{'target':20s} {'n':>5s} {'p25':>5s} {'p50':>5s} {'p75':>5s} "
          f"{'p90':>5s} {'>4px%':>6s} {'>7px%':>6s}")
    rows = []
    for p in sorted((ROOT / 'data/inputs').iterdir()):
        if p.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
            continue
        img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        w = ramp_widths(img)
        if len(w) == 0:
            continue
        row = (p.stem, len(w), *np.percentile(w, [25, 50, 75, 90]),
               100 * (w > 4).mean(), 100 * (w > 7).mean())
        rows.append(row)
        print(f"{row[0]:20s} {row[1]:5d} {row[2]:5.1f} {row[3]:5.1f} "
              f"{row[4]:5.1f} {row[5]:5.1f} {row[6]:6.1f} {row[7]:6.1f}")
