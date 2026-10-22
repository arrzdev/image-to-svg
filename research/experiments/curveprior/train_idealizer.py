#!/usr/bin/env python
"""curve idealizer v0 — learn OUR noisy detected curve -> RECRAFT clean curve.

Self-contained: data load, preprocessing, training, baselines, holdout eval,
overlay plots, runtime measurement.  See REPORT.md for results.

Usage:  .venv/bin/python research/experiments/curveprior/train_idealizer.py [--epochs 300]
"""
import argparse, json, math, os, time
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
PAIRS = os.path.join(HERE, "pairs.jsonl")
HOLDOUT_STEMS = {"fox", "shield", "elephant"}
N = 64
EPS = 1e-9
SEED = 0

# ---------------------------------------------------------------- geometry --

def resample(pts: np.ndarray, n: int, closed: bool) -> np.ndarray:
    """Arc-length-uniform resample. Closed: parametrized over the full loop
    (wrap segment included), n samples in [0,L) so no duplicate endpoint;
    start correspondence (index 0) is preserved.  Open: endpoints included."""
    pts = np.asarray(pts, dtype=np.float64)
    if closed and np.allclose(pts[0], pts[-1], atol=1e-6):
        pts = pts[:-1]                       # drop duplicated closing vertex
    if closed:
        loop = np.vstack([pts, pts[:1]])
    else:
        loop = pts
    seg = np.hypot(*np.diff(loop, axis=0).T)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    L = s[-1]
    if L < EPS:
        return np.repeat(pts[:1], n, axis=0)
    t = np.linspace(0, L, n, endpoint=not closed)
    x = np.interp(t, s, loop[:, 0])
    y = np.interp(t, s, loop[:, 1])
    return np.stack([x, y], axis=1)


def canon_transform(pts: np.ndarray):
    """Normalization transform from OUR resampled curve: translate to centroid,
    scale by RMS radius, rotate so the principal axis is horizontal (sign fixed
    by x-skewness so the frame is deterministic)."""
    c = pts.mean(axis=0)
    q = pts - c
    scale = math.sqrt((q ** 2).sum(axis=1).mean()) + EPS
    cov = (q.T @ q) / len(q)
    theta = 0.5 * math.atan2(2 * cov[0, 1], cov[0, 0] - cov[1, 1])
    R = np.array([[math.cos(-theta), -math.sin(-theta)],
                  [math.sin(-theta),  math.cos(-theta)]])
    xr = (q / scale) @ R.T
    if (xr[:, 0] ** 3).sum() < 0:            # 180-degree disambiguation
        R = -R
    return c, scale, R


def apply_tf(pts, c, scale, R):
    return ((np.asarray(pts) - c) / scale) @ R.T


def invert_tf(pts, c, scale, R):
    return (np.asarray(pts) @ R) * scale + c


# --- turning distance, ported from eval/pathflow.py --------------

def turning_fn(pts, n=64):
    d = np.diff(pts, axis=0)
    seglen = np.hypot(d[:, 0], d[:, 1])
    keep = seglen > EPS
    d, seglen = d[keep], seglen[keep]
    if len(seglen) < 2:
        return np.zeros(n)
    ang = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    ang -= ang[0]
    s = np.concatenate([[0.0], np.cumsum(seglen)])
    s = s / (s[-1] + EPS)
    return np.interp(np.linspace(0, 1, n), s[:-1], ang)


def turning_dist(a, b):
    ta, tb = turning_fn(a), turning_fn(b)
    diff = ta - tb
    diff = diff - diff.mean()
    return float(np.sqrt((diff ** 2).mean()))


def close_if(pts, closed):
    return np.vstack([pts, pts[:1]]) if closed else pts


# --- geometric smoothing baseline (mirrors engines/edge/edge-10/src/arcfit.py) ----

def box_smooth_leash(pts: np.ndarray, win: int, leash: float,
                     closed: bool) -> np.ndarray:
    """Box smooth with a positional leash (px).  Closed: circular indexing
    (smooth_closed semantics).  Open: edge-clamped window, endpoints pinned."""
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


# ------------------------------------------------------------------- data --
# NOTE on alignment: the stored their_pts are NOT positionally registered to
# our_pts (the mining gate — turning distance — is translation/scale blind;
# small repeated shapes matched other instances across the canvas, corr of
# raw point-L2 with centroid offset = 0.995).  We therefore re-canonicalize
# here: theirs is centered on ITS OWN centroid (position is not something an
# idealizer should learn), scaled/rotated by OUR transform, and the
# orientation x cyclic-roll nuisance is resolved by min point-L2 at N=64.
# The residual aligned L2 is stored per pair and used to gate TRAINING pairs
# (align_l2 <= 1.0: drops shape-mismatched instances); holdout is reported
# both on all pairs and on the same-gated clean subset.

def align_pair(d):
    closed = bool(d["closed"])
    ours_px = resample(d["our_pts"], N, closed)
    c, s, R = canon_transform(ours_px)
    on = apply_tf(ours_px, c, s, R)
    best = None                              # (l2, rev, roll, theirs_norm)
    for rev in (False, True):
        tp = np.asarray(d["their_pts"], dtype=np.float64)
        if rev:
            tp = tp[::-1]
        t = resample(tp, N, closed)
        tn = ((t - t.mean(axis=0)) / s) @ R.T   # THEIR centroid, OUR scale+rot
        if closed:
            for r in range(N):
                tr = np.roll(tn, r, axis=0)
                v = np.linalg.norm(tr - on, axis=1).mean()
                if best is None or v < best[0]:
                    best = (v, rev, r, tr)
        else:
            v = np.linalg.norm(tn - on, axis=1).mean()
            if best is None or v < best[0]:
                best = (v, rev, 0, tn)
    return ours_px, on, best, (c, s, R)


def load_pairs():
    recs = []
    with open(PAIRS) as f:
        for line in f:
            d = json.loads(line)
            closed = bool(d["closed"])
            ours_px, on, (al2, rev, roll, tn), (c, s, R) = align_pair(d)
            recs.append(dict(
                stem=d["stem"], closed=closed, tile=d["tile"],
                ours_px=ours_px,
                theirs_px=invert_tf(tn, c, s, R),
                ours=on, theirs=tn,
                c=c, s=s, R=R, align_l2=al2,
                turning_aligned=d["turning_aligned"], strict=d["strict"]))
    return recs


# ------------------------------------------------------------------ model --

class PadConv(nn.Module):
    """Conv1d with per-sample padding: circular for closed curves,
    replicate for open ones."""
    def __init__(self, cin, cout, k, dil):
        super().__init__()
        self.k, self.dil = k, dil
        self.pad = dil * (k // 2)
        self.conv = nn.Conv1d(cin, cout, k, dilation=dil)

    def forward(self, x, closed_mask):
        p = self.pad
        wrap = torch.cat([x[..., -p:], x, x[..., :p]], dim=-1)
        edge = F.pad(x, (p, p), mode="replicate")
        xp = torch.where(closed_mask.view(-1, 1, 1), wrap, edge)
        return self.conv(xp)


class IdealizerNet(nn.Module):
    """~142K-param dilated 1D CNN over the 64-point sequence.
    Input features (computed in forward from raw xy): xy, unit tangent,
    signed turn angle, closed flag.  Output: per-point offsets, added to
    the input polyline (residual)."""
    def __init__(self, ch=96):
        super().__init__()
        dils = [1, 2, 4, 8, 1]
        cins = [6] + [ch] * (len(dils) - 1)
        couts = [ch] * (len(dils) - 1) + [2]
        self.convs = nn.ModuleList(
            PadConv(a, b, 5, d) for a, b, d in zip(cins, couts, dils))

    @staticmethod
    def features(xy, closed_mask):
        # xy: (B,2,N)
        B, _, n = xy.shape
        nxt = torch.roll(xy, -1, dims=-1)
        prv = torch.roll(xy, 1, dims=-1)
        open_m = ~closed_mask
        if open_m.any():                     # one-sided diffs at open ends
            nxt[open_m, :, -1] = xy[open_m, :, -1]
            prv[open_m, :, 0] = xy[open_m, :, 0]
        fwd = nxt - xy
        bwd = xy - prv
        tan = fwd + bwd
        tan = tan / (tan.norm(dim=1, keepdim=True) + 1e-8)
        cross = fwd[:, 0] * bwd[:, 1] - fwd[:, 1] * bwd[:, 0]
        dot = (fwd * bwd).sum(dim=1)
        turn = torch.atan2(cross, dot + 1e-12).unsqueeze(1)
        flag = closed_mask.float().view(-1, 1, 1).expand(-1, 1, n)
        return torch.cat([xy, tan, turn, flag], dim=1)

    def forward(self, xy, closed_mask):
        h = self.features(xy, closed_mask)
        for i, cv in enumerate(self.convs):
            h = cv(h, closed_mask)
            if i < len(self.convs) - 1:
                h = F.gelu(h)
        return xy + h                        # residual: predict offsets


# ------------------------------------------------------------ train / eval --

def second_diff(x, closed_mask):
    nxt = torch.roll(x, -1, dims=-1)
    prv = torch.roll(x, 1, dims=-1)
    d2 = nxt - 2 * x + prv
    m = torch.ones_like(d2[:, :1])           # mask out invalid open endpoints
    m[~closed_mask, :, 0] = 0
    m[~closed_mask, :, -1] = 0
    return d2 * m


def augment(x, y, closed, gen, noise=0.015, rot_deg=15.0, roll=True):
    """x,y: (B,2,N) normalized; same-transform augmentation."""
    B = x.shape[0]
    dev = x.device
    # cyclic roll (closed only)
    if roll:
        rolls = torch.randint(0, N, (B,), generator=gen, device=dev)
        for i in range(B):                   # small B; fine
            if closed[i]:
                x[i] = torch.roll(x[i], int(rolls[i]), dims=-1)
                y[i] = torch.roll(y[i], int(rolls[i]), dims=-1)
    # mirror flip
    flip = torch.rand(B, generator=gen, device=dev) < 0.5
    x[flip, 1] *= -1
    y[flip, 1] *= -1
    # small rotation around canonical frame
    ang = (torch.rand(B, generator=gen, device=dev) - 0.5) * \
        (2 * math.pi * rot_deg / 180.0)
    ca, sa = torch.cos(ang), torch.sin(ang)
    rot = torch.stack([torch.stack([ca, -sa], -1),
                       torch.stack([sa, ca], -1)], -2)   # (B,2,2)
    x = torch.einsum("bij,bjn->bin", rot, x)
    y = torch.einsum("bij,bjn->bin", rot, y)
    # input-only jitter
    if noise > 0:
        x = x + torch.randn(x.shape, generator=gen, device=dev) * noise
    return x, y


def to_tensors(recs, device):
    x = torch.tensor(np.stack([r["ours"].T for r in recs]),
                     dtype=torch.float32, device=device)
    y = torch.tensor(np.stack([r["theirs"].T for r in recs]),
                     dtype=torch.float32, device=device)
    cm = torch.tensor([r["closed"] for r in recs], device=device)
    return x, y, cm


def mean_point_l2(pred, tgt):                # (B,2,N) -> scalar per batch mean
    return (pred - tgt).norm(dim=1).mean(dim=-1)


def eval_metrics(pred_np, recs):
    """pred_np: list of (N,2) normalized-frame predictions."""
    m1 = np.array([np.linalg.norm(p - r["theirs"], axis=1).mean()
                   for p, r in zip(pred_np, recs)])
    m2 = np.array([turning_dist(close_if(p, r["closed"]),
                                close_if(r["theirs"], r["closed"]))
                   for p, r in zip(pred_np, recs)])
    return m1, m2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=300)
    ap.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    ap.add_argument("--lam", type=float, default=1.0, help="smoothness-match loss weight")
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--noise", type=float, default=0.015)
    ap.add_argument("--rot-deg", type=float, default=15.0)
    ap.add_argument("--no-roll", action="store_true")
    ap.add_argument("--tag", default="v0", help="suffix for output files")
    args = ap.parse_args()
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    dev = torch.device(args.device)

    recs = load_pairs()
    GATE = 1.0                               # supervision-quality gate
    hold = [r for r in recs if r["stem"] in HOLDOUT_STEMS]
    pool = [r for r in recs if r["stem"] not in HOLDOUT_STEMS
            and r["align_l2"] <= GATE]
    n_drop = sum(1 for r in recs if r["stem"] not in HOLDOUT_STEMS) - len(pool)
    rng = np.random.RandomState(SEED)
    perm = rng.permutation(len(pool))
    n_val = int(round(0.15 * len(pool)))
    val = [pool[i] for i in perm[:n_val]]
    trn = [pool[i] for i in perm[n_val:]]
    print(f"pairs total={len(recs)} train={len(trn)} val={len(val)} "
          f"(dropped {n_drop} train-stem pairs with align_l2>{GATE}) "
          f"holdout={len(hold)} ({sorted(HOLDOUT_STEMS)})")

    xt, yt, ct = to_tensors(trn, dev)
    xv, yv, cv = to_tensors(val, dev)
    xh, yh, chm = to_tensors(hold, dev)

    model = IdealizerNet().to(dev)
    n_par = sum(p.numel() for p in model.parameters())
    print(f"params: {n_par:,}")
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    gen = torch.Generator(device=dev.type).manual_seed(SEED)

    lam = args.lam                           # smoothness/curvature-match weight
    bs = 128
    best_val, best_state, best_ep = 1e9, None, -1
    hist = []
    t0 = time.time()
    for ep in range(args.epochs):
        model.train()
        order = torch.randperm(len(trn), generator=gen, device=dev)
        tot, nb = 0.0, 0
        for i in range(0, len(trn), bs):
            idx = order[i:i + bs]
            xb, yb, cb = xt[idx].clone(), yt[idx].clone(), ct[idx]
            xb, yb = augment(xb, yb, cb, gen, noise=args.noise,
                             rot_deg=args.rot_deg, roll=not args.no_roll)
            pred = model(xb, cb)
            loss = F.mse_loss(pred, yb) + lam * F.mse_loss(
                second_diff(pred, cb), second_diff(yb, cb))
            opt.zero_grad(); loss.backward(); opt.step()
            tot += float(loss); nb += 1
        sched.step()
        model.eval()
        with torch.no_grad():
            pv = model(xv, cv)
            vall2 = float(mean_point_l2(pv, yv).mean())
        hist.append((ep, tot / nb, vall2))
        if vall2 < best_val:
            best_val, best_ep = vall2, ep
            best_state = {k: v.detach().cpu().clone()
                          for k, v in model.state_dict().items()}
        if ep - best_ep > 40:
            print(f"early stop at ep {ep} (best ep {best_ep})")
            break
        if ep % 20 == 0:
            print(f"ep {ep:3d} train {tot/nb:.5f} val-L2 {vall2:.5f}")
    train_s = time.time() - t0
    print(f"training took {train_s:.0f}s; best val-L2 {best_val:.5f} @ ep {best_ep}")
    model.load_state_dict(best_state)
    torch.save({"state_dict": best_state, "n_points": N,
                "params": n_par, "best_val_l2": best_val},
               os.path.join(HERE, f"model_{args.tag}.pt"))

    # ------------------------------------------------------------ baselines
    model.eval()
    with torch.no_grad():
        ph = model(xh, chm).cpu().numpy()
    pred_h = [p.T for p in ph]
    m1_model, m2_model = eval_metrics(pred_h, hold)
    m1_b0, m2_b0 = eval_metrics([r["ours"] for r in hold], hold)

    b1 = {}
    for win in (3, 5, 9, 13, 17):
        for leash in (1.25, 2.0, 3.0):
            sm = [apply_tf(box_smooth_leash(r["ours_px"], win, leash,
                                            r["closed"]),
                           r["c"], r["s"], r["R"]) for r in hold]
            b1[(win, leash)] = eval_metrics(sm, hold)

    clean = np.array([r["align_l2"] <= GATE for r in hold])
    px_scale = np.array([r["s"] for r in hold])

    def summarize(mask):
        best_m1_key = min(b1, key=lambda k: b1[k][0][mask].mean())
        best_m2_key = min(b1, key=lambda k: b1[k][1][mask].mean())
        return {
            "n": int(mask.sum()),
            "B0": {"m1": float(m1_b0[mask].mean()),
                   "m2": float(m2_b0[mask].mean()),
                   "m1_px": float((m1_b0 * px_scale)[mask].mean())},
            "B1_best_m1": {"key": best_m1_key,
                           "m1": float(b1[best_m1_key][0][mask].mean()),
                           "m2": float(b1[best_m1_key][1][mask].mean()),
                           "m1_px": float((b1[best_m1_key][0] * px_scale)[mask].mean())},
            "B1_best_m2": {"key": best_m2_key,
                           "m1": float(b1[best_m2_key][0][mask].mean()),
                           "m2": float(b1[best_m2_key][1][mask].mean())},
            "model": {"m1": float(m1_model[mask].mean()),
                      "m2": float(m2_model[mask].mean()),
                      "m1_px": float((m1_model * px_scale)[mask].mean())},
        }

    results = {
        "counts": {"train": len(trn), "val": len(val), "holdout": len(hold),
                   "holdout_clean": int(clean.sum()), "gate": GATE},
        "params": n_par, "best_val_l2": best_val, "best_ep": best_ep,
        "train_seconds": train_s, "device": args.device,
        "hist": hist,
        "holdout_all": summarize(np.ones(len(hold), bool)),
        "holdout_clean": summarize(clean),
        "B1_full": {f"w{k[0]}_l{k[1]}": [float(v[0].mean()), float(v[1].mean())]
                    for k, v in b1.items()},
    }
    # per-stem breakdown (clean subset — supervision noise dominates otherwise)
    bk1 = results["holdout_clean"]["B1_best_m1"]["key"]
    per = {}
    for stem in sorted(HOLDOUT_STEMS):
        sel = np.array([r["stem"] == stem for r in hold]) & clean
        per[stem] = {
            "n": int(sel.sum()),
            "B0": [float(m1_b0[sel].mean()), float(m2_b0[sel].mean())],
            "B1_m1best": [float(b1[bk1][0][sel].mean()),
                          float(b1[bk1][1][sel].mean())],
            "model": [float(m1_model[sel].mean()), float(m2_model[sel].mean())],
        }
    results["per_stem_clean"] = per

    # ------------------------------------------------------- runtime probe
    with torch.no_grad():
        xb = xh[:1]
        for _ in range(5):
            model(xb, chm[:1])               # warmup
        if dev.type == "mps":
            torch.mps.synchronize()
        t = time.time()
        for _ in range(50):
            model(xb, chm[:1])
        if dev.type == "mps":
            torch.mps.synchronize()
        single_ms = (time.time() - t) / 50 * 1000
        big = xh.repeat(3, 1, 1)[:512]
        cbig = chm.repeat(3)[:512]
        model(big, cbig)
        if dev.type == "mps":
            torch.mps.synchronize()
        t = time.time()
        for _ in range(10):
            model(big, cbig)
        if dev.type == "mps":
            torch.mps.synchronize()
        batch_ms = (time.time() - t) / 10 / 512 * 1000
        # cpu single
        mc = IdealizerNet(); mc.load_state_dict(best_state); mc.eval()
        xc, cc = xh[:1].cpu(), chm[:1].cpu()
        for _ in range(5):
            mc(xc, cc)
        t = time.time()
        for _ in range(50):
            mc(xc, cc)
        cpu_single_ms = (time.time() - t) / 50 * 1000
    results["runtime_ms_per_curve"] = {
        f"{args.device}_single": single_ms, f"{args.device}_batch512": batch_ms,
        "cpu_single": cpu_single_ms}

    with open(os.path.join(HERE, f"results_{args.tag}.json"), "w") as f:
        json.dump(results, f, indent=1, default=str)

    for tag in ("holdout_all", "holdout_clean"):
        hd = results[tag]
        print(f"\n=== {tag} (n={hd['n']}, normalized frame) ===")
        print(f"B0 identity          m1={hd['B0']['m1']:.4f}  m2={hd['B0']['m2']:.4f}  (~{hd['B0']['m1_px']:.2f}px)")
        print(f"B1 best(m1) {hd['B1_best_m1']['key']}  m1={hd['B1_best_m1']['m1']:.4f}  m2={hd['B1_best_m1']['m2']:.4f}  (~{hd['B1_best_m1']['m1_px']:.2f}px)")
        print(f"B1 best(m2) {hd['B1_best_m2']['key']}  m1={hd['B1_best_m2']['m1']:.4f}  m2={hd['B1_best_m2']['m2']:.4f}")
        print(f"model                m1={hd['model']['m1']:.4f}  m2={hd['model']['m2']:.4f}  (~{hd['model']['m1_px']:.2f}px)")
    print("per-stem (clean):", json.dumps(per, indent=1))
    print("runtime:", results["runtime_ms_per_curve"])

    # ------------------------------------------------------------ overlays
    make_overlays(model, hold, m1_model, m1_b0, clean, dev, args.tag)


def make_overlays(model, hold, m1_model, m1_b0, clean, dev, tag="v0"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    delta = m1_b0 - m1_model                 # >0 model improves
    big = (np.array([r["s"] for r in hold]) > 15) & clean  # sizeable, clean sup
    order = np.argsort(delta)
    cand = [i for i in order if big[i]]
    picks = ([("fail", i) for i in cand[:2]] +
             [("tie", i) for i in cand[len(cand)//2 - 1: len(cand)//2 + 1]] +
             [("win", i) for i in cand[-2:]])
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    for ax, (kind, i) in zip(axes.flat, picks):
        r = hold[i]
        with torch.no_grad():
            p = model(torch.tensor(r["ours"].T[None], dtype=torch.float32,
                                   device=dev),
                      torch.tensor([r["closed"]], device=dev))[0].cpu().numpy().T
        p_px = invert_tf(p, r["c"], r["s"], r["R"])
        for pts, col, lw, lab in ((r["ours_px"], "0.55", 2.0, "ours"),
                                  (r["theirs_px"], "tab:green", 1.6, "recraft"),
                                  (p_px, "tab:red", 1.4, "model")):
            q = close_if(pts, r["closed"])
            ax.plot(q[:, 0], q[:, 1], color=col, lw=lw, label=lab)
        ax.set_aspect("equal"); ax.invert_yaxis()
        ax.set_title(f"{kind}: {r['stem']} tile{r['tile']} "
                     f"dL2={delta[i]:+.4f} ({delta[i]*r['s']:+.2f}px)",
                     fontsize=9)
        ax.legend(fontsize=7)
    fig.suptitle("curve idealizer v0 — holdout overlays "
                 "(grey=ours, green=Recraft target, red=model)")
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, f"overlays_{tag}.png"), dpi=110)
    # training curve
    res = json.load(open(os.path.join(HERE, f"results_{tag}.json")))
    h = np.array([(a, b, c) for a, b, c in res["hist"]], dtype=float)
    fig2, ax = plt.subplots(figsize=(7, 4))
    ax.plot(h[:, 0], h[:, 1], label="train loss (L2+smooth)")
    ax.plot(h[:, 0], h[:, 2], label="val mean point-L2")
    ax.set_xlabel("epoch"); ax.set_yscale("log"); ax.legend()
    fig2.tight_layout()
    fig2.savefig(os.path.join(HERE, f"training_curve_{tag}.png"), dpi=110)
    print(f"wrote overlays_{tag}.png, training_curve_{tag}.png")


if __name__ == "__main__":
    main()
