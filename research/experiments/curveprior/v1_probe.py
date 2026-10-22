"""Door-2 probe: is Recraft's curve placement predictable FROM THE IMAGE?

Training-free ladder on the 1,311 mined pairs (research/experiments/curveprior/pairs.jsonl),
evaluated in the ABSOLUTE 2048-canvas frame (position matters here — the v0
canonicalization is deliberately NOT applied; positionally-mismatched instances
are gated out instead of re-centered):

  R0 identity        — our dense polyline as-is
  R1 oracle smooth   — box_smooth_leash sweep, best picked ON the eval set
                       (v0's B1, ported; the geometry ceiling)
  R2 classical snap  — sub-pixel edge localization from the SOURCE IMAGE:
                       sample Lab profile along each point normal, snap to the
                       50% crossing between the two side colors (+ median/box
                       smoothing of the offset profile). Zero training.
  R2b snap+smooth    — R2 then R1's smoothing (fixed w5/leash2.0)
  R3 oracle normal   — project THEIR polyline onto our normals: the ceiling
                       for ANY per-point normal-offset method (incl. a model)

Decision rule (stated before running):
  - R3 barely better than R0  -> door 2 dead at geometry level (the residual
    is tangential/route change, not placement) — do not train.
  - R3 meaty, R2 captures most -> ship classical snap in the pipeline; no model.
  - R3 meaty, R2 far from it   -> the residual is the learnable part; train v1.

Metric: symmetric chamfer (mean nearest-neighbor distance both ways, canvas px)
between dense polylines. Also reported: |normal offset| distribution, coverage,
per-stem breakdown, gate sensitivity. Holdout stems (fox/shield/elephant) are
the verdict set; train stems shown for reference.

Outputs: v1_probe_report.json, v1_probe_overlays.png, stdout tables.
Run: .venv/bin/python research/experiments/curveprior/v1_probe.py
"""
import json
import math
import os
import sys

import cv2
import numpy as np
from scipy.spatial import cKDTree

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PAIRS = os.path.join(ROOT, "research", "experiments", "curveprior", "pairs.jsonl")
OUTDIR = os.path.join(ROOT, "research", "experiments", "curveprior")
INPUTS = os.path.join(ROOT, "data", "inputs")

CANVAS_W = 2048.0            # mining canvas width (mine_pairs.py NATIVE)
HOLDOUT = {"fox", "shield", "elephant"}
DS = 2.0                     # dense resample step, canvas px
EPS = 1e-9

# probe geometry
PROJ_W = 12.0                # oracle projection search window (canvas px)
TAP_HALF = 8.0               # profile half-extent (canvas px)
TAP_STEP = 0.5               # profile tap spacing (canvas px)
SNAP_MAX = 4.0               # classical snap max |offset|
SIDE_DE_MIN = 5.0            # min Lab dE between sides for a usable edge
GATE_CHAMFER = 12.0          # co-location gate (supervision validity)
GATE_CENTROID = 24.0


# ---------------------------------------------------------------- geometry --

def resample_step(pts, step, closed):
    """Arc-length-uniform resample at ~step px. Closed loops include the wrap
    segment and drop the duplicate endpoint; open keep endpoints."""
    pts = np.asarray(pts, dtype=np.float64)
    if closed and np.allclose(pts[0], pts[-1], atol=1e-6):
        pts = pts[:-1]
    loop = np.vstack([pts, pts[:1]]) if closed else pts
    seg = np.hypot(*np.diff(loop, axis=0).T)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    L = s[-1]
    if L < EPS:
        return np.repeat(pts[:1], 4, axis=0)
    n = int(np.clip(round(L / step) + 1, 8, 512))
    t = np.linspace(0, L, n, endpoint=not closed)
    x = np.interp(t, s, loop[:, 0])
    y = np.interp(t, s, loop[:, 1])
    return np.stack([x, y], axis=1)


def normals(pts, closed):
    """Unit tangents via central differences (wrap if closed), rotated +90.
    Returns (tangent, normal), each (N,2)."""
    if closed:
        nxt, prv = np.roll(pts, -1, axis=0), np.roll(pts, 1, axis=0)
        d = nxt - prv
    else:
        d = np.empty_like(pts)
        d[1:-1] = pts[2:] - pts[:-2]
        d[0] = pts[1] - pts[0]
        d[-1] = pts[-1] - pts[-2]
    ln = np.hypot(d[:, 0], d[:, 1])[:, None] + EPS
    t = d / ln
    n = np.stack([-t[:, 1], t[:, 0]], axis=1)
    return t, n


def box_smooth_leash(pts, win, leash, closed):
    """v0 B1 semantics (train_idealizer.py port)."""
    n = len(pts)
    if n < win + 2 or win < 3:
        return pts
    k = win // 2
    idx = np.arange(-k, k + 1)
    sm = np.empty_like(pts, dtype=np.float64)
    for i in range(n):
        j = (i + idx) % n if closed else np.clip(i + idx, 0, n - 1)
        sm[i] = pts[j].mean(axis=0)
    if not closed:
        sm[0], sm[-1] = pts[0], pts[-1]
    d = sm - pts
    dist = np.hypot(d[:, 0], d[:, 1])
    over = dist > leash
    if over.any():
        sm[over] = pts[over] + d[over] * (leash / dist[over, None])
    return sm


def chamfer(a, b):
    """Symmetric mean nearest-neighbor distance, canvas px."""
    ta, tb = cKDTree(a), cKDTree(b)
    da = tb.query(a)[0].mean()
    db = ta.query(b)[0].mean()
    return float((da + db) / 2)


def ray_project(pts, nrm, target, w=PROJ_W):
    """Signed offset t per point where (pt + t*nrm) intersects the target
    polyline, |t|<=w, min-|t| among intersections. Returns (t, valid)."""
    a = target[:-1]                       # (M,2) segment starts
    ab = target[1:] - a                   # (M,2)
    N, M = len(pts), len(a)
    t_out = np.zeros(N)
    valid = np.zeros(N, dtype=bool)
    # solve p + t*n = a + u*ab  ->  [n, -ab] [t,u]^T = a - p
    for i in range(N):
        p, n = pts[i], nrm[i]
        ap = a - p                        # (M,2)
        det = n[0] * (-ab[:, 1]) - n[1] * (-ab[:, 0])
        ok = np.abs(det) > 1e-12
        t = (ap[:, 0] * (-ab[:, 1]) - ap[:, 1] * (-ab[:, 0])) / np.where(ok, det, 1.0)
        u = (n[0] * ap[:, 1] - n[1] * ap[:, 0]) / np.where(ok, det, 1.0)
        hit = ok & (u >= 0.0) & (u <= 1.0) & (np.abs(t) <= w)
        if hit.any():
            th = t[hit]
            t_out[i] = th[np.argmin(np.abs(th))]
            valid[i] = True
    return t_out, valid


# ------------------------------------------------------------------- image --

_IMG_CACHE = {}

def load_image(stem):
    """Source image as float32 Lab (H,W,3), plus canvas->image scale."""
    if stem in _IMG_CACHE:
        return _IMG_CACHE[stem]
    path = None
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = os.path.join(INPUTS, stem + ext)
        if os.path.exists(p):
            path = p
            break
    if path is None:
        raise FileNotFoundError(stem)
    raw = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if raw.ndim == 2:
        raw = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
    if raw.shape[2] == 4:                 # composite on white
        al = raw[:, :, 3:4].astype(np.float32) / 255.0
        raw = (raw[:, :, :3].astype(np.float32) * al
               + 255.0 * (1 - al)).astype(np.uint8)
    rgb = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2Lab)   # L 0..100, a/b signed
    scale = raw.shape[1] / CANVAS_W       # canvas px -> image px
    _IMG_CACHE[stem] = (lab, scale)
    return _IMG_CACHE[stem]


def bilinear(img, xy):
    """Bilinear sample img (H,W,C) at image-space xy (...,2), edge-clamped."""
    h, w = img.shape[:2]
    x = np.clip(xy[..., 0], 0, w - 1.001)
    y = np.clip(xy[..., 1], 0, h - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    p00 = img[y0, x0]
    p01 = img[y0, x0 + 1]
    p10 = img[y0 + 1, x0]
    p11 = img[y0 + 1, x0 + 1]
    return (p00 * (1 - fx) * (1 - fy) + p01 * fx * (1 - fy)
            + p10 * (1 - fx) * fy + p11 * fx * fy)


def snap_offsets(pts, nrm, lab, scale):
    """Classical sub-pixel snap: offset per point to the 50% crossing between
    side colors along the normal Lab profile. Returns (delta, usable)."""
    taps = np.arange(-TAP_HALF, TAP_HALF + 1e-6, TAP_STEP)   # (T,)
    T = len(taps)
    # (N,T,2) canvas coords -> image coords
    coords = (pts[:, None, :] + taps[None, :, None] * nrm[:, None, :]) * scale
    prof = bilinear(lab, coords)                              # (N,T,3)
    nside = int(round(3.0 / TAP_STEP))                        # outer 3px
    side_a = prof[:, :nside].mean(axis=1)                     # (N,3)
    side_b = prof[:, -nside:].mean(axis=1)
    d_ab = side_b - side_a
    de = np.linalg.norm(d_ab, axis=1)                         # (N,)
    usable = de >= SIDE_DE_MIN
    # project profile onto the a->b color axis: alpha in [0,1]
    alpha = ((prof - side_a[:, None, :]) * d_ab[:, None, :]).sum(-1) \
        / (de[:, None] ** 2 + EPS)
    # find crossing of 0.5 nearest to tap 0
    delta = np.zeros(len(pts))
    sgn = np.sign(alpha - 0.5)
    cross = np.nonzero(np.diff(sgn, axis=1))                  # rows, cols
    best = {}
    for r, c in zip(*cross):
        a0, a1 = alpha[r, c], alpha[r, c + 1]
        if abs(a1 - a0) < 1e-9:
            continue
        u = taps[c] + (0.5 - a0) / (a1 - a0) * TAP_STEP
        if abs(u) > SNAP_MAX:
            continue
        if r not in best or abs(u) < abs(best[r]):
            best[r] = u
    for r, u in best.items():
        delta[r] = u
    usable &= np.isin(np.arange(len(pts)), list(best.keys()))
    # profile cleanup along the curve: median-3 then box-3, zeros where unusable
    delta = np.where(usable, delta, 0.0)
    if len(delta) >= 5:
        med = np.copy(delta)
        for i in range(1, len(delta) - 1):
            med[i] = np.median(delta[i - 1:i + 2])
        k = np.array([0.25, 0.5, 0.25])
        sm = np.convolve(med, k, mode="same")
        sm[0], sm[-1] = med[0], med[-1]
        delta = sm
    return delta, usable


# -------------------------------------------------------------------- main --

def main():
    recs = []
    with open(PAIRS) as f:
        for line in f:
            recs.append(json.loads(line))
    print(f"{len(recs)} pairs loaded")

    rows = []
    for ri, d in enumerate(recs):
        closed = bool(d["closed"])
        ours = resample_step(np.asarray(d["our_pts"]), DS, closed)
        theirs = resample_step(np.asarray(d["their_pts"]), DS, closed)
        cen_off = float(np.linalg.norm(ours.mean(0) - theirs.mean(0)))
        c0 = chamfer(close_pts(ours, closed), close_pts(theirs, closed))
        rows.append(dict(i=ri, stem=d["stem"], closed=closed, ours=ours,
                         theirs=theirs, cen=cen_off, c0=c0,
                         strict=bool(d["strict"])))
        if (ri + 1) % 300 == 0:
            print(f"  prep {ri + 1}/{len(recs)}")

    # ---- co-location gate sensitivity -------------------------------------
    print("\nGate sensitivity (pairs surviving chamfer<=X & centroid<=2X):")
    for g in (8.0, 12.0, 16.0, 24.0):
        surv = [r for r in rows if r["c0"] <= g and r["cen"] <= 2 * g]
        h = sum(1 for r in surv if r["stem"] in HOLDOUT)
        print(f"  gate {g:5.1f}px: {len(surv):4d} total, {h:3d} holdout")

    kept = [r for r in rows
            if r["c0"] <= GATE_CHAMFER and r["cen"] <= GATE_CENTROID]
    hold = [r for r in kept if r["stem"] in HOLDOUT]
    train = [r for r in kept if r["stem"] not in HOLDOUT]
    print(f"\nprimary gate {GATE_CHAMFER}px: {len(kept)} kept "
          f"({len(hold)} holdout / {len(train)} train-stems)")

    # ---- ladder ------------------------------------------------------------
    for r in kept:
        ours, theirs, closed = r["ours"], r["theirs"], r["closed"]
        _, nrm = normals(ours, closed)
        lab, scale = load_image(r["stem"])
        tgt_closed = close_pts(theirs, closed)

        # R1 oracle smoothing: sweep, keep per-pair best chamfer later; store all
        r1 = {}
        for w in (3, 5, 9, 13, 17):
            for leash in (1.25, 2.0, 3.0):
                sm = box_smooth_leash(ours, w, leash, closed)
                r1[(w, leash)] = chamfer(close_pts(sm, closed), tgt_closed)
        r["r1"] = r1

        # R2 classical snap
        delta, usable = snap_offsets(ours, nrm, lab, scale)
        snapped = ours + delta[:, None] * nrm
        r["r2"] = chamfer(close_pts(snapped, closed), tgt_closed)
        r["r2_usable"] = float(usable.mean())
        sm = box_smooth_leash(snapped, 5, 2.0, closed)
        r["r2b"] = chamfer(close_pts(sm, closed), tgt_closed)

        # R3 oracle normal projection
        toff, valid = ray_project(ours, nrm, tgt_closed)
        oracle = ours + np.where(valid, toff, 0.0)[:, None] * nrm
        r["r3"] = chamfer(close_pts(oracle, closed), tgt_closed)
        r["r3_cov"] = float(valid.mean())
        r["toff_med"] = float(np.median(np.abs(toff[valid]))) if valid.any() else 0.0
        r["toff_p90"] = float(np.percentile(np.abs(toff[valid]), 90)) if valid.any() else 0.0
        r["snap_vs_oracle"] = float(np.mean(np.abs(delta[valid] - toff[valid]))) if valid.any() else 0.0

    def ladder(rs, name):
        c0 = np.mean([r["c0"] for r in rs])
        # oracle-picked single smoothing setting for the whole set (v0 B1 style)
        keys = rs[0]["r1"].keys()
        r1_best_key = min(keys, key=lambda k: np.mean([r["r1"][k] for r in rs]))
        r1 = np.mean([r["r1"][r1_best_key] for r in rs])
        r2 = np.mean([r["r2"] for r in rs])
        r2b = np.mean([r["r2b"] for r in rs])
        r3 = np.mean([r["r3"] for r in rs])
        cov = np.mean([r["r3_cov"] for r in rs])
        tm = np.median([r["toff_med"] for r in rs])
        tp = np.median([r["toff_p90"] for r in rs])
        print(f"\n== {name} (n={len(rs)}) ==")
        print(f"  R0 identity            {c0:7.3f} px")
        print(f"  R1 oracle smooth {str(r1_best_key):>9s} {r1:7.3f} px  ({pct(r1, c0)})")
        print(f"  R2 classical snap      {r2:7.3f} px  ({pct(r2, c0)})")
        print(f"  R2b snap+smooth        {r2b:7.3f} px  ({pct(r2b, c0)})")
        print(f"  R3 oracle normal       {r3:7.3f} px  ({pct(r3, c0)})  cov {cov:.0%}")
        print(f"  |t| median {tm:.2f}px  p90 {tp:.2f}px")
        return dict(n=len(rs), r0=c0, r1=r1, r1_key=list(r1_best_key),
                    r2=r2, r2b=r2b, r3=r3, cov=cov,
                    toff_med=tm, toff_p90=tp)

    def pct(v, base):
        return f"{(v - base) / base * 100:+.1f}%"

    report = {"gate_chamfer": GATE_CHAMFER, "gate_centroid": GATE_CENTROID}
    report["holdout"] = ladder(hold, "HOLDOUT (fox+shield+elephant)")
    report["train_stems"] = ladder(train, "train stems (reference)")

    print("\nPer-stem (holdout), mean chamfer px:")
    print(f"  {'stem':10s} {'n':>4s} {'R0':>7s} {'R1':>7s} {'R2':>7s} {'R2b':>7s} {'R3':>7s}")
    per_stem = {}
    for stem in sorted({r["stem"] for r in kept}):
        rs = [r for r in kept if r["stem"] == stem]
        keys = rs[0]["r1"].keys()
        k1 = min(keys, key=lambda k: np.mean([r["r1"][k] for r in rs]))
        row = [np.mean([r["c0"] for r in rs]),
               np.mean([r["r1"][k1] for r in rs]),
               np.mean([r["r2"] for r in rs]),
               np.mean([r["r2b"] for r in rs]),
               np.mean([r["r3"] for r in rs])]
        per_stem[stem] = dict(n=len(rs), r0=row[0], r1=row[1], r2=row[2],
                              r2b=row[3], r3=row[4])
        mark = " *HOLD*" if stem in HOLDOUT else ""
        print(f"  {stem:10s} {len(rs):4d} " + " ".join(f"{v:7.3f}" for v in row) + mark)
    report["per_stem"] = per_stem

    with open(os.path.join(OUTDIR, "v1_probe_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nwrote {os.path.join(OUTDIR, 'v1_probe_report.json')}")

    make_overlays(hold if hold else kept)


def close_pts(pts, closed):
    return np.vstack([pts, pts[:1]]) if closed else pts


def make_overlays(rs):
    """12 example crops: source image + ours(red) theirs(green) snap(blue)
    oracle(yellow), 4x zoom."""
    rs = sorted(rs, key=lambda r: r["c0"])
    picks = [rs[int(q * (len(rs) - 1))] for q in np.linspace(0.05, 0.9, 12)]
    Z = 4
    tiles = []
    for r in picks:
        ours, theirs, closed = r["ours"], r["theirs"], r["closed"]
        lab, scale = load_image(r["stem"])
        _, nrm = normals(ours, closed)
        delta, _ = snap_offsets(ours, nrm, lab, scale)
        snapped = ours + delta[:, None] * nrm
        toff, valid = ray_project(ours, nrm, close_pts(theirs, closed))
        oracle = ours + np.where(valid, toff, 0.0)[:, None] * nrm

        allp = np.vstack([ours, theirs])
        lo = allp.min(0) - 10
        hi = allp.max(0) + 10
        # crop in image space
        rgbpath = None
        img = cv2.cvtColor((cv2.cvtColor(lab, cv2.COLOR_Lab2RGB) * 255)
                           .astype(np.uint8), cv2.COLOR_RGB2BGR)
        x0, y0 = (lo * scale).astype(int)
        x1, y1 = np.ceil(hi * scale).astype(int) + 1
        h, w = img.shape[:2]
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(w, x1), min(h, y1)
        crop = img[y0:y1, x0:x1]
        if crop.size == 0:
            continue
        cw = int(crop.shape[1] * Z / scale * scale)  # zoom factor on image px
        big = cv2.resize(crop, None, fx=Z / scale, fy=Z / scale,
                         interpolation=cv2.INTER_NEAREST)

        def draw(poly, color):
            p = ((close_pts(poly, closed)) * scale)
            p = (p - [x0, y0]) * (Z / scale)
            cv2.polylines(big, [p.astype(np.int32)], False, color, 1,
                          cv2.LINE_AA)
        draw(ours, (0, 0, 255))
        draw(theirs, (0, 200, 0))
        draw(snapped, (255, 120, 0))
        draw(oracle, (0, 220, 255))
        cv2.putText(big, f"{r['stem']} c0={r['c0']:.1f} r2={r['r2']:.1f} r3={r['r3']:.1f}",
                    (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 0), 1,
                    cv2.LINE_AA)
        tiles.append(big)

    # pack into a grid of max-dim tiles
    if not tiles:
        return
    th = max(t.shape[0] for t in tiles)
    tw = max(t.shape[1] for t in tiles)
    grid = np.full((3 * th + 8, 4 * tw + 6, 3), 255, np.uint8)
    for i, t in enumerate(tiles[:12]):
        r0, c0_ = divmod(i, 4)
        y, x = r0 * (th + 2), c0_ * (tw + 2)
        grid[y:y + t.shape[0], x:x + t.shape[1]] = t
    out = os.path.join(OUTDIR, "v1_probe_overlays.png")
    cv2.imwrite(out, grid)
    print(f"wrote {out}  (red=ours green=recraft orange=snap yellow=oracle)")


if __name__ == "__main__":
    main()
