"""Door-2 diagnostic round 2 — the train/no-train decision numbers.

D1 image-explainable oracle: t_hat = t_oracle ONLY where Recraft's curve sits
   near the image gradient peak (|t - gpos| <= k), else 0. Upper bound for any
   model that works by locating the image edge. Decomposes R3's -45% into
   image-attributable vs pure-redraw.
D2 nonlinear probe: tiny torch MLP (135 -> 128 -> 64 -> 1) on the SAME
   point features as the ridge. Holdout R2 vs ridge's 0.189 measures the
   nonlinear headroom a real conv model would tap.

Run: .venv/bin/python research/experiments/curveprior/v1_diag2.py
"""
import os
import sys

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v1_diag import curve_points
from v1_probe import HOLDOUT

EPS = 1e-9


def main():
    torch.manual_seed(0)
    np.random.seed(0)
    rows = curve_points()
    stems = np.array([r["stem"] for r in rows])
    t = np.array([r["t"] for r in rows])
    dc = np.array([r["dc"] for r in rows])
    gpos = np.array([r["gpos"] for r in rows])
    gmag = np.array([r["gmag"] for r in rows])
    curv = np.array([r["curv"] for r in rows])
    prof = np.stack([r["prof"] for r in rows])
    hold = np.isin(stems, list(HOLDOUT))

    # ---- D1: image-explainable oracle --------------------------------------
    print("\nD1 image-explainable oracle (t_hat = t where |t-gpos|<=k else 0):")
    mae0 = np.abs(t[hold]).mean()
    for k in (0.75, 1.0, 1.5, 2.0):
        expl = np.abs(t - gpos) <= k
        th = np.where(expl, t, 0.0)
        mae = np.abs(t - th)[hold].mean()
        print(f"  k={k:4.2f}px: explains {expl[hold].mean():5.1%} of holdout pts"
              f"  -> normal-MAE {mae0:.2f} -> {mae:.2f} px "
              f"({(mae - mae0) / mae0 * 100:+.1f}%)")

    # ---- D2: MLP probe ------------------------------------------------------
    X = np.concatenate([
        prof.reshape(len(prof), -1),
        np.abs(np.diff(prof[:, :, 0], axis=1)),
        dc[:, None], gpos[:, None], gmag[:, None], curv[:, None],
    ], axis=1).astype(np.float32)
    y = t.astype(np.float32)
    mu, sd = X[~hold].mean(0), X[~hold].std(0) + EPS
    X = (X - mu) / sd
    # clamp targets to the plausible band; outliers are route changes
    yc = np.clip(y, -8, 8)

    dev = "cpu"                       # 70k x 135: CPU is instant and stable
    Xtr = torch.tensor(X[~hold], device=dev)
    ytr = torch.tensor(yc[~hold], device=dev)
    Xte = torch.tensor(X[hold], device=dev)

    # small val split from train for early stop
    n = len(Xtr)
    idx = torch.randperm(n)
    nv = n // 8
    vi, ti = idx[:nv], idx[nv:]

    net = nn.Sequential(nn.Linear(X.shape[1], 128), nn.GELU(),
                        nn.Linear(128, 64), nn.GELU(),
                        nn.Linear(64, 1))
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-4)
    best = (1e9, None)
    for ep in range(60):
        net.train()
        perm = ti[torch.randperm(len(ti))]
        for i in range(0, len(perm), 4096):
            b = perm[i:i + 4096]
            opt.zero_grad()
            loss = nn.functional.huber_loss(net(Xtr[b]).squeeze(-1), ytr[b],
                                            delta=2.0)
            loss.backward()
            opt.step()
        net.eval()
        with torch.no_grad():
            vl = nn.functional.mse_loss(net(Xtr[vi]).squeeze(-1),
                                        ytr[vi]).item()
        if vl < best[0]:
            best = (vl, [p.detach().clone() for p in net.parameters()])
    for p, bp in zip(net.parameters(), best[1]):
        p.data.copy_(bp)
    net.eval()
    with torch.no_grad():
        pr_tr = net(Xtr).squeeze(-1).numpy()
        pr_te = net(Xte).squeeze(-1).numpy()

    for name, pred, m in (("train", pr_tr, ~hold), ("HOLDOUT", pr_te, hold)):
        yy = y[m]
        ss = 1 - ((yy - pred) ** 2).sum() / (((yy - yy.mean()) ** 2).sum() + EPS)
        mae_i = np.abs(yy).mean()
        mae_p = np.abs(yy - pred).mean()
        print(f"D2 MLP {name}: R2={ss:+.3f}  MAE {mae_i:.2f} -> {mae_p:.2f} px"
              f" ({(mae_p - mae_i) / mae_i * 100:+.1f}%)")

    # what the MLP's normal-MAE reduction would mean for chamfer:
    # holdout R3 removed 44.8% of chamfer via perfect offsets; scale linearly
    yy, pred = y[hold], pr_te
    frac = 1 - np.abs(yy - pred).mean() / (np.abs(yy).mean() + EPS)
    print(f"\nrough chamfer projection: MLP captures {frac:.1%} of the oracle's"
          f" normal error -> ~{frac * 44.8:.1f}% chamfer reduction "
          f"(oracle = 44.8%)")


if __name__ == "__main__":
    main()
