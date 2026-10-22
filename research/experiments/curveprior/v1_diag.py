"""Door-2 point-level diagnostic: is the oracle normal offset PREDICTABLE
from the image profile? Runs BEFORE any training (the screen v0 lacked).

Point table over gated pairs: t_oracle (signed normal offset to Recraft),
delta_classical (sub-pixel 50%-crossing snap), Lab profile (33 taps x 3),
local geometry (curvature), our-point distance to the image's own edge.

Questions answered:
  Q1 corr(delta_classical, t_oracle)      — does the image edge position
     predict Recraft's placement at all?
  Q2 E[|t_oracle|] where our curve is ON the image edge vs OFF it
     — if ours is already on the pixel edge but Recraft still deviates,
     "find the true edge" is the wrong formulation (they idealize AWAY).
  Q3 ridge linear probe profile+geom -> t, train on train-stems points,
     R^2 + chamfer-style |resid| on HOLDOUT points — cheapest signal bound.
     (If ridge ~0 and GBM ~0, a deep model has nothing to find either.)

Run: .venv/bin/python research/experiments/curveprior/v1_diag.py
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v1_probe import (PAIRS, HOLDOUT, DS, GATE_CHAMFER, GATE_CENTROID,
                      TAP_HALF, TAP_STEP, resample_step, normals, chamfer,
                      ray_project, load_image, bilinear, snap_offsets,
                      close_pts)

OUTDIR = os.path.dirname(os.path.abspath(__file__))
EPS = 1e-9


def curve_points():
    """Yield per-point rows for all gated pairs."""
    recs = [json.loads(l) for l in open(PAIRS)]
    taps = np.arange(-TAP_HALF, TAP_HALF + 1e-6, TAP_STEP)
    rows = []
    kept_pairs = 0
    for d in recs:
        closed = bool(d["closed"])
        ours = resample_step(np.asarray(d["our_pts"]), DS, closed)
        theirs = resample_step(np.asarray(d["their_pts"]), DS, closed)
        cen = float(np.linalg.norm(ours.mean(0) - theirs.mean(0)))
        c0 = chamfer(close_pts(ours, closed), close_pts(theirs, closed))
        if c0 > GATE_CHAMFER or cen > GATE_CENTROID:
            continue
        kept_pairs += 1
        lab, scale = load_image(d["stem"])
        _, nrm = normals(ours, closed)
        toff, valid = ray_project(ours, nrm, close_pts(theirs, closed))
        delta, usable = snap_offsets(ours, nrm, lab, scale)

        # profile (N,T,3)
        coords = (ours[:, None, :] + taps[None, :, None] * nrm[:, None, :]) * scale
        prof = bilinear(lab, coords)
        # local curvature: turn angle over +-2 samples (~4px)
        t_, _ = normals(ours, closed)
        ang = np.arctan2(t_[:, 1], t_[:, 0])
        ang = np.unwrap(ang)
        curv = np.zeros(len(ours))
        if len(ours) > 4:
            curv[2:-2] = np.abs(ang[4:] - ang[:-4])
        # distance from our point to the image's own edge: gradient-magnitude
        # argmax position along the profile (L channel), signed tap offset
        gL = np.abs(np.diff(prof[:, :, 0], axis=1))          # (N,T-1)
        gmax = gL.max(axis=1)
        gpos = taps[:-1][np.argmax(gL, axis=1)] + TAP_STEP / 2
        interior = np.ones(len(ours), dtype=bool)
        if not closed and len(ours) > 4:
            interior[:2] = interior[-2:] = False
        m = valid & interior
        for i in np.nonzero(m)[0]:
            rows.append(dict(stem=d["stem"], t=float(toff[i]),
                             dc=float(delta[i]), usable=bool(usable[i]),
                             gpos=float(gpos[i]), gmag=float(gmax[i]),
                             curv=float(curv[i]),
                             prof=prof[i].astype(np.float32)))
    print(f"pairs kept {kept_pairs}, points {len(rows)}")
    return rows


def main():
    rows = curve_points()
    stems = np.array([r["stem"] for r in rows])
    t = np.array([r["t"] for r in rows])
    dc = np.array([r["dc"] for r in rows])
    gpos = np.array([r["gpos"] for r in rows])
    gmag = np.array([r["gmag"] for r in rows])
    curv = np.array([r["curv"] for r in rows])
    usable = np.array([r["usable"] for r in rows])
    prof = np.stack([r["prof"] for r in rows])          # (P,T,3)
    hold = np.isin(stems, list(HOLDOUT))

    print(f"\nholdout points {hold.sum()}, train points {(~hold).sum()}")
    print(f"|t| median {np.median(np.abs(t)):.2f}  p90 "
          f"{np.percentile(np.abs(t), 90):.2f} px")

    # Q1: does classical snap / gradient-peak position predict t?
    for name, x, mask in (("classical delta (usable pts)", dc, usable),
                          ("gradient-peak pos (strong-grad pts)", gpos,
                           gmag > 5.0)):
        mh = mask & hold
        if mh.sum() > 50:
            c = np.corrcoef(x[mh], t[mh])[0, 1]
            print(f"Q1 corr({name}, t_oracle) holdout: {c:+.3f}  "
                  f"n={mh.sum()}")

    # Q2: |t| conditioned on our distance to the image edge
    on_edge = (np.abs(gpos) <= 1.0) & (gmag > 5.0)
    off_edge = (np.abs(gpos) > 2.0) & (gmag > 5.0)
    for name, m in (("ours ON image edge (|gpos|<=1px)", on_edge & hold),
                    ("ours OFF image edge (|gpos|>2px)", off_edge & hold)):
        if m.sum() > 50:
            print(f"Q2 {name}: E|t|={np.abs(t[m]).mean():.2f}px  "
                  f"med={np.median(np.abs(t[m])):.2f}  n={m.sum()}")
    # and: where ours is OFF the edge, does Recraft sit AT the image edge?
    m = off_edge & hold
    if m.sum() > 50:
        resid_edge = np.abs(t[m] - gpos[m])
        print(f"Q2b off-edge pts: |t - gpos| med={np.median(resid_edge):.2f}px"
              f"  (0 => Recraft sits ON the image edge)   |t| med="
              f"{np.median(np.abs(t[m])):.2f}  |gpos| med="
              f"{np.median(np.abs(gpos[m])):.2f}")

    # Q3: ridge probe profile+geom -> t  (train stems -> holdout)
    X = np.concatenate([
        prof.reshape(len(prof), -1),                    # 99 raw Lab taps
        np.abs(np.diff(prof[:, :, 0], axis=1)),         # 32 |dL| taps
        dc[:, None], gpos[:, None], gmag[:, None], curv[:, None],
    ], axis=1)
    y = t
    mu, sd = X[~hold].mean(0), X[~hold].std(0) + EPS
    Xn = (X - mu) / sd
    lam = 10.0
    A = Xn[~hold]
    b = y[~hold]
    w = np.linalg.solve(A.T @ A + lam * np.eye(A.shape[1]), A.T @ b)
    for name, m in (("train", ~hold), ("HOLDOUT", hold)):
        pred = Xn[m] @ w
        ss = 1 - ((y[m] - pred) ** 2).sum() / (((y[m] - y[m].mean()) ** 2).sum() + EPS)
        mae_i = np.abs(y[m]).mean()
        mae_p = np.abs(y[m] - pred).mean()
        print(f"Q3 ridge {name}: R2={ss:+.3f}  MAE {mae_i:.2f} -> {mae_p:.2f} px"
              f"  ({(mae_p - mae_i) / mae_i * 100:+.1f}%)")

    # Q3b: tiny GBM if available (nonlinear check)
    try:
        from sklearn.ensemble import HistGradientBoostingRegressor
        g = HistGradientBoostingRegressor(max_iter=300, max_depth=6,
                                          learning_rate=0.08, random_state=0)
        g.fit(X[~hold], y[~hold])
        for name, m in (("train", ~hold), ("HOLDOUT", hold)):
            pred = g.predict(X[m])
            ss = 1 - ((y[m] - pred) ** 2).sum() / (((y[m] - y[m].mean()) ** 2).sum() + EPS)
            mae_p = np.abs(y[m] - pred).mean()
            print(f"Q3b GBM {name}: R2={ss:+.3f}  MAE {np.abs(y[m]).mean():.2f}"
                  f" -> {mae_p:.2f} px")
    except ImportError:
        print("Q3b sklearn not available — skipped")

    np.savez_compressed(os.path.join(OUTDIR, "v1_points.npz"),
                        stems=stems, t=t, dc=dc, gpos=gpos, gmag=gmag,
                        curv=curv, usable=usable, hold=hold)
    print("wrote v1_points.npz (profiles omitted; rebuild via curve_points())")


if __name__ == "__main__":
    main()
