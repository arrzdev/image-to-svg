"""Differentiable refinement, shared-edge parameterization — v3 OBJECTIVE.

Same parameterization and staged schedule as refine_shared_v2 (one tensor per
boundary-edge interior + one per junction node, lattice coordinates, region
paths rebuilt per iteration by differentiable concatenation, staged
256@2x2 -> 512@1x1 (+ full-res 2x2 color tail), Polyak tail averaging).

What changed vs v2 — the LOSS, not the machinery. v2's plain MSE chases
raster noise: any sub-pixel AA ambiguity in the target produces gradient, so
curves wobble to absorb it. v3 stops paying for that:

1. DEADBAND FIDELITY. Per-pixel psi(r) = max(0, |r| - tau)^2 instead of r^2.
   Residuals smaller than what one pixel of AA ambiguity produces are FREE,
   so inside the band the fairness term wins uncontested. tau is expressed in
   the loss's own units (rgb in [0,1]); ~1-4 gray levels (1/255..4/255) is
   the useful range.

2. MVC (minimum variation of curvature) FAIRNESS. For every edge's cubic
   chain we sample ~14 points per cubic, compute curvature closed-form from
   the control points (autograd-friendly, guarded denominator), approximate
   dk/ds with finite differences over arclength, and penalize
   sum (dk/ds)^2 ds. Penalizing curvature VARIATION (not curvature) drives
   wobble to zero while leaving circles/straights untouched — the "confident
   digital curve" prior. Computed in lattice coordinates so it is invariant
   to the render stage.

3. CORNER PROTECTION. Junction nodes are protected by construction: the
   finite differences never cross an edge boundary, so fairness is never
   applied ACROSS a node. Interior corners are detected on each edge's raw
   polyline pre-refinement (turning angle over a small window) and the MVC
   penalty is masked in a radius around them — fair aggressively BETWEEN
   corners, never across them (the PolyVector-flow lesson).

4. SLIVER GATE. Tiny/thin geometry is exempt from the MVC term.
   (a) Edge-level: a short edge (polyline length below ~30 lattice px) or
   one bordering a very small region (< ~200 px area) gets no fairness at
   all — (dk/ds)^2 has almost no arclength to spread over there, so fairing
   dominates fidelity and inflates/curls tips into blobs.
   (b) Sample-level: MVC samples currently sitting in a LOCALLY thin part
   of the label map (pixels erased by a morphological opening with a
   ~(2*sliver_thin_r+1) px disk) are masked, re-evaluated every iteration
   at the CURRENT sample positions. Thin protrusions of large regions —
   eye-slit lash tips, whisker ends — fail the edge tests (long edge, huge
   outline region) and only reach the thin zone mid-optimization as the
   curve extrudes to cover them; the dynamic lookup drops their fairness
   exactly there. Gated geometry is fidelity-only; the deadband already
   keeps it calm.

API-compatible with v2: refine_shared(ctx, target_rgb, ...) plus new kwargs
deadband_tau / fair_weight (and corner_* tuning). Colors-on default kept.
"""
from __future__ import annotations

import numpy as np

# (render_size, aa_samples, max_iters[, min_iters]) per stage.
DEFAULT_STAGES = ((256, 2, 30), (512, 1, 30, 26))
DEFAULT_STAGES_COLOR = ((256, 2, 30), (512, 1, 26, 22), (512, 2, 14, 12))

# Recommended operating point from the elephant eye-sweep (2026-07):
# tau=1/255 frees sub-AA residual chatter without the metric cost seen at
# 4/255 (q 0.9232 vs 0.9085); fair_weight=15 is where wobble visibly dies on
# long strokes while shapes hold (5 = weaker but safer, 40 = smoothest with
# slightly curlier thin-sliver tips).
DEFAULT_DEADBAND_TAU = 1.0 / 255.0
DEFAULT_FAIR_WEIGHT = 15.0
MVC_SAMPLES = 14                     # curvature samples per cubic segment


def _moving_average(P: np.ndarray, win: int) -> np.ndarray:
    """Centered moving average of a polyline (reflect-padded)."""
    if win <= 1 or len(P) < win:
        return P
    pad = win // 2
    Q = np.pad(P, ((pad, pad), (0, 0)), mode="edge")
    k = np.ones(win) / win
    out = np.empty_like(P, dtype=np.float64)
    for d in range(P.shape[1]):
        out[:, d] = np.convolve(Q[:, d], k, mode="valid")[: len(P)]
    return out


def _detect_corners(pts, closed: bool, angle_deg: float = 55.0,
                    window: int = 4, smooth: int = 5) -> np.ndarray:
    """Interior corner locations on a crack polyline (lattice coords).

    Turning angle between the incoming and outgoing chords over `window`
    samples; candidates above `angle_deg` are non-max-suppressed into one
    corner per run. The polyline is lightly smoothed first so the unit-step
    staircase does not read as corners. Returns (K, 2) float array.
    """
    P = np.asarray(pts, dtype=np.float64)
    if closed:
        P = P[:-1]
    n = len(P)
    if n < 2 * window + 1:
        return np.empty((0, 2))
    S = _moving_average(P, smooth)
    if closed:
        idx = np.arange(n)
        v1 = S[idx] - S[(idx - window) % n]
        v2 = S[(idx + window) % n] - S[idx]
        valid = np.ones(n, bool)
    else:
        idx = np.arange(window, n - window)
        v1 = S[idx] - S[idx - window]
        v2 = S[idx + window] - S[idx]
        valid = np.ones(len(idx), bool)
    cross = v1[:, 0] * v2[:, 1] - v1[:, 1] * v2[:, 0]
    dot = (v1 * v2).sum(1)
    ang = np.abs(np.degrees(np.arctan2(cross, dot)))
    cand = valid & (ang > angle_deg)
    corners = []
    i = 0
    m = len(cand)
    while i < m:
        if not cand[i]:
            i += 1
            continue
        j = i
        while j + 1 < m and cand[j + 1]:
            j += 1
        run = np.arange(i, j + 1)
        best = run[np.argmax(ang[run])]
        corners.append(P[idx[best]])
        i = j + 1
    return np.asarray(corners) if corners else np.empty((0, 2))


def _bezier_bases(m: int):
    """Position / first- / second-derivative Bernstein matrices at midpoint
    samples t=(k+0.5)/m, each shape (m, 4), float64."""
    t = (np.arange(m) + 0.5) / m
    u = 1.0 - t
    B0 = np.stack([u ** 3, 3 * u ** 2 * t, 3 * u * t ** 2, t ** 3], axis=1)
    D1 = np.stack([-3 * u ** 2, 3 * u ** 2 - 6 * u * t,
                   6 * u * t - 3 * t ** 2, 3 * t ** 2], axis=1)
    D2 = np.stack([6 * u, -12 * u + 6 * t, 6 * u - 12 * t, 6 * t], axis=1)
    return B0, D1, D2


def refine_shared(ctx: dict, target_rgb, iters: int = 60, size: int = 512,
                  lr: float = 0.3, stages=None, patience: int = 4,
                  min_iters: int = 8, improve: float = 0.995,
                  final_decay: bool = False, avg_tail: int = 12,
                  optimize_colors: bool = True, color_lr: float = 0.008,
                  deadband_tau: float = DEFAULT_DEADBAND_TAU,
                  fair_weight: float = DEFAULT_FAIR_WEIGHT,
                  corner_angle: float = 55.0, corner_window: int = 4,
                  corner_radius: float = 4.0, mvc_samples: int = MVC_SAMPLES,
                  kappa_max: float = 2.0,
                  sliver_min_len: float = 30.0, sliver_min_area: float = 200.0,
                  sliver_thin_r: float = 1.5,
                  return_info: bool = False, debug: bool = False):
    """v2-compatible signature plus the v3 objective knobs.

    deadband_tau: fidelity deadband in rgb-[0,1] units (0 = plain MSE).
    fair_weight: weight of the MVC curvature-variation energy (0 = off).
    corner_angle/window: interior-corner detector on each edge polyline
    (turning angle in degrees over a +-window chord).
    corner_radius: MVC mask radius (lattice px) around detected corners.
    mvc_samples: curvature samples per cubic segment.
    sliver_min_len/sliver_min_area: MVC sliver gate — edges whose polyline
    is shorter than sliver_min_len (lattice px) or that border a region
    smaller than sliver_min_area (px) get NO fairness term (fidelity only).
    sliver_thin_r: sample-level gate — MVC samples currently inside a part
    of the label map locally thinner than ~2*sliver_thin_r+1 px are masked
    (thin tips of big regions; dynamic, per iteration). Set all three
    sliver_* to 0 to disable the gate.
    Everything else behaves exactly as in refine_shared_v2."""
    import torch
    import pydiffvg as dv
    import boundary

    dv.set_use_gpu(False)
    try:
        import os
        torch.set_num_threads(min(6, max(2, (os.cpu_count() or 8) // 2)))
    except Exception:
        pass

    if stages is None:
        stages = DEFAULT_STAGES_COLOR if optimize_colors else DEFAULT_STAGES

    labels, centers = ctx["labels"], ctx["centers"]
    edges, loops, fitted = ctx["edges"], ctx["loops"], ctx["fitted"]
    H, W = labels.shape
    L = max(W, H)

    # ---- shared parameters (LATTICE coordinates) ---------------------------
    node_params: dict = {}     # lattice coord -> tensor(2)
    interior: dict = {}        # eid -> tensor(3n-1, 2) or closed tensor(3n, 2)
    is_closed_edge: dict = {}

    def rows_of(eid):
        ch = fitted[eid]
        rows = [ch[0][0:2]]
        for c in ch:
            rows += [c[2:4], c[4:6], c[6:8]]
        return np.asarray(rows, dtype=np.float64)

    for eid in fitted:
        pts = edges[eid]["pts"]
        closed = tuple(pts[0]) == tuple(pts[-1])
        is_closed_edge[eid] = closed
        rows = rows_of(eid)
        if closed:
            interior[eid] = torch.tensor(rows[:-1], dtype=torch.float32,
                                         requires_grad=True)
        else:
            for key, row in ((tuple(pts[0]), rows[0]), (tuple(pts[-1]), rows[-1])):
                if key not in node_params:
                    node_params[key] = torch.tensor(row, dtype=torch.float32,
                                                    requires_grad=True)
            interior[eid] = torch.tensor(rows[1:-1], dtype=torch.float32,
                                         requires_grad=True)

    def edge_points(eid, rev):
        """3n rows for this edge in travel direction, starting at its first
        anchor and EXCLUDING its final anchor (the next edge provides it)."""
        if is_closed_edge[eid]:
            E = interior[eid]
            return E if not rev else torch.roll(torch.flip(E, [0]), 1, 0)
        pts = edges[eid]["pts"]
        a, b = node_params[tuple(pts[0])], node_params[tuple(pts[-1])]
        I = interior[eid]
        if not rev:
            return torch.cat([a.unsqueeze(0), I])
        return torch.cat([b.unsqueeze(0), torch.flip(I, [0])])

    def edge_full_rows(eid):
        """(3n+1, 2) control rows for the whole edge INCLUDING the final
        anchor — for curvature evaluation of the cubic chain."""
        fwd = edge_points(eid, False)
        if is_closed_edge[eid]:
            last = fwd[0:1]
        else:
            last = node_params[tuple(edges[eid]["pts"][-1])].unsqueeze(0)
        return torch.cat([fwd, last])

    # ---- MVC scaffolding (static indices, corner mask, normalizer) --------
    mvc_on = fair_weight > 0
    if mvc_on:
        B0np, D1np, D2np = _bezier_bases(mvc_samples)
        # ---- sliver gate: exempt tiny/thin geometry from fairing ----------
        region_areas = np.bincount(labels.ravel())

        def _sliver(eid):
            P = np.asarray(edges[eid]["pts"], dtype=np.float64)
            plen = float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())
            if plen < sliver_min_len:
                return True
            for lab in (edges[eid].get("left", -1), edges[eid].get("right", -1)):
                if (lab is not None and 0 <= lab < len(region_areas)
                        and region_areas[lab] < sliver_min_area):
                    return True
            return False

        edge_order = [eid for eid in fitted if not _sliver(eid)]
        n_gated = len(fitted) - len(edge_order)
        # sample-level thinness raster: region pixels that vanish under a
        # morphological opening are locally thinner than the kernel — thin
        # protrusions (lash tips, whisker ends) regardless of what other
        # thick geometry happens to pass nearby. The raster is static (the
        # target's thin zones don't move) but it is looked up at the
        # CURRENT sample positions each iteration, so geometry that
        # extrudes into a thin zone during optimization loses its fairness
        # term exactly there.
        thin_t = None
        if sliver_thin_r > 0:
            import cv2
            k = 2 * int(np.ceil(sliver_thin_r)) + 1
            kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
            thin = np.zeros(labels.shape, np.uint8)
            for lab in np.unique(labels):
                m = (labels == lab).astype(np.uint8)
                thin |= m & (1 - cv2.morphologyEx(m, cv2.MORPH_OPEN, kern))
            # dilate so crack-coordinate boundary samples on the rim of a
            # thin part land inside the mask
            thin = cv2.dilate(thin, np.ones((3, 3), np.uint8), iterations=2)
            thin_t = torch.from_numpy(thin.astype(bool))

        seg_rows_l, pair_a_l, pair_b_l = [], [], []
        init_pts_l = []
        row_off = samp_off = 0
        n_corners = 0
        for eid in edge_order:
            n = len(fitted[eid])
            rows0 = rows_of(eid)                       # (3n+1, 2)
            base = row_off + 3 * np.arange(n)[:, None]
            seg = base + np.arange(4)[None, :]         # (n, 4)
            seg_rows_l.append(seg)
            # initial sample positions for corner masking + ds normalizer
            segs0 = rows0[seg - row_off]               # (n, 4, 2)
            p0 = np.einsum("mk,skd->smd", B0np, segs0).reshape(-1, 2)
            init_pts_l.append(p0)
            ns = n * mvc_samples
            ok = np.ones(ns, bool)
            corners = _detect_corners(edges[eid]["pts"], is_closed_edge[eid],
                                      angle_deg=corner_angle,
                                      window=corner_window)
            n_corners += len(corners)
            for c in corners:
                ok &= np.linalg.norm(p0 - c, axis=1) > corner_radius
            a = samp_off + np.arange(ns - 1)
            b = a + 1
            keep = ok[:-1] & ok[1:]
            pair_a_l.append(a[keep])
            pair_b_l.append(b[keep])
            if is_closed_edge[eid] and ok[-1] and ok[0]:
                pair_a_l.append(np.array([samp_off + ns - 1]))
                pair_b_l.append(np.array([samp_off]))
            row_off += 3 * n + 1
            samp_off += ns
        n_pairs = int(sum(len(a) for a in pair_a_l))
        if not edge_order or n_pairs == 0:
            mvc_on = False   # everything gated/masked -> pure fidelity
        else:
            seg_rows_t = torch.from_numpy(
                np.concatenate(seg_rows_l).astype(np.int64))
            pair_a = torch.from_numpy(np.concatenate(pair_a_l).astype(np.int64))
            pair_b = torch.from_numpy(np.concatenate(pair_b_l).astype(np.int64))
            init_pts = np.concatenate(init_pts_l)
            ds0 = np.linalg.norm(
                init_pts[pair_b.numpy()] - init_pts[pair_a.numpy()], axis=1)
            mvc_norm = max(float(ds0.sum()), 1.0)  # constant: no balloon reward
        B0t = torch.from_numpy(B0np.astype(np.float32))
        D1t = torch.from_numpy(D1np.astype(np.float32))
        D2t = torch.from_numpy(D2np.astype(np.float32))
        if debug:
            import sys as _sys
            print(f"    mvc: {len(edge_order)}/{len(fitted)} edges "
                  f"({n_gated} sliver-gated), "
                  f"{sum(s.shape[0] for s in seg_rows_l)} cubics, "
                  f"{n_corners} interior corners, {n_pairs} fair pairs",
                  file=_sys.stderr, flush=True)

        def mvc_energy():
            full = torch.cat([edge_full_rows(eid) for eid in edge_order])
            segs = full[seg_rows_t]                        # (S, 4, 2)
            p = torch.einsum("mk,skd->smd", B0t, segs).reshape(-1, 2)
            d1 = torch.einsum("mk,skd->smd", D1t, segs).reshape(-1, 2)
            d2 = torch.einsum("mk,skd->smd", D2t, segs).reshape(-1, 2)
            cross = d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]
            sp2 = (d1 * d1).sum(1)
            # kappa clamp: wobble lives at ~0.01-0.4 px^-1; values beyond
            # kappa_max are corners (masked anyway) or transient handle
            # degeneracies whose unbounded (dk/ds)^2 gradients make the
            # energy stiff enough to destabilize Adam (measured: fair term
            # oscillated 0.07 <-> 20 without the clamp). Clamped spikes get
            # zero fair gradient — fidelity owns them.
            kap = torch.clamp(cross.abs() / (sp2 + 1e-6) ** 1.5,
                              max=kappa_max)
            dp = p[pair_b] - p[pair_a]
            ds = torch.clamp(torch.sqrt((dp * dp).sum(1) + 1e-12), min=0.5)
            dk = kap[pair_b] - kap[pair_a]
            # sum (dk/ds)^2 * ds == sum dk^2 / ds, per unit initial length
            e = dk * dk / ds
            if thin_t is not None:
                with torch.no_grad():
                    q = p.detach()
                    xi = q[:, 0].round().long().clamp(0, W - 1)
                    yi = q[:, 1].round().long().clamp(0, H - 1)
                    th = thin_t[yi, xi]
                    w = (~(th[pair_a] | th[pair_b])).float()
                e = e * w
            return e.sum() / mvc_norm

    # ---- region scaffolding (fixed topology) ------------------------------
    areas = np.bincount(labels.ravel())
    order = [r for r in np.argsort(areas)[::-1]
             if r < len(centers) and r in loops]
    path_specs = []    # (region, loop) in shape order
    groups = []
    color_params = []  # aligned with `order` when optimize_colors
    shape_id = 0
    for r in order:
        ids = []
        for lp in loops[r]:
            path_specs.append(lp)
            ids.append(shape_id)
            shape_id += 1
        c = centers[r]
        fill = torch.tensor([c[0] / 255, c[1] / 255, c[2] / 255, 1.0])
        if optimize_colors:
            fill.requires_grad_(True)
            color_params.append(fill)
        groups.append(dv.ShapeGroup(
            shape_ids=torch.tensor(ids),
            fill_color=fill,
            use_even_odd_rule=True))

    ncp_cache = []
    for lp in path_specs:
        nseg = sum(len(fitted[eid]) for eid, _ in lp)
        ncp_cache.append(torch.tensor([2] * nseg, dtype=torch.int32))

    params = list(node_params.values()) + list(interior.values())
    base_lr = lr * L / 512.0
    opt = torch.optim.Adam(params, lr=base_lr)
    copt = torch.optim.Adam(color_params, lr=color_lr) if color_params else None
    tail_params = params + color_params   # everything the tail average covers
    render = dv.RenderFunction.apply

    it_global = 0
    tail: list = []
    for si, stage in enumerate(stages):
        size_s, ns, max_it = stage[:3]
        min_it = stage[3] if len(stage) > 3 else min_iters
        last_stage = si == len(stages) - 1
        scale = size_s / L
        RW, RH = int(W * scale), int(H * scale)
        target = torch.from_numpy(
            _resize(target_rgb, RW, RH).astype("float32") / 255.0)
        sc = torch.tensor(scale, dtype=torch.float32)

        best, stall = float("inf"), 0
        it = -1
        fid_v = fair_v = 0.0
        for it in range(max_it):
            if last_stage and final_decay:
                import math
                f = 0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * it / max_it))
                for g in opt.param_groups:
                    g["lr"] = base_lr * f
            opt.zero_grad()
            if copt is not None:
                copt.zero_grad()
            shapes = []
            for lp, ncp in zip(path_specs, ncp_cache):
                pts = torch.cat([edge_points(eid, rev) for eid, rev in lp]) * sc
                shapes.append(dv.Path(num_control_points=ncp, points=pts,
                                      is_closed=True))
            args = dv.RenderFunction.serialize_scene(RW, RH, shapes, groups)
            img = render(RW, RH, ns, ns, it_global, None, *args)
            rgb = img[:, :, :3] * img[:, :, 3:4] + (1 - img[:, :, 3:4])
            res = rgb - target
            if deadband_tau > 0:
                fid = (torch.clamp(res.abs() - deadband_tau, min=0.0)
                       ** 2).mean()
            else:
                fid = (res * res).mean()
            if mvc_on:
                fair = mvc_energy()
                loss = fid + fair_weight * fair
                fair_v = float(fair.detach())
            else:
                loss = fid
            fid_v = float(fid.detach())
            if debug and int(debug) >= 2:
                import sys as _sys
                print(f"      it{it_global}: fid={fid_v:.6f} "
                      f"fair={fair_v:.6f}", file=_sys.stderr, flush=True)
            loss.backward()
            opt.step()
            if copt is not None and last_stage:
                copt.step()
                with torch.no_grad():
                    for cp in color_params:
                        cp.clamp_(0.0, 1.0)
                        cp[3] = 1.0   # fills stay opaque
            it_global += 1
            if last_stage and avg_tail > 0:
                tail.append([p.detach().clone() for p in tail_params])
                if len(tail) > avg_tail:
                    tail.pop(0)
            cur = float(loss.detach())
            if cur < best * improve:
                best, stall = cur, 0
            else:
                stall += 1
                if stall >= patience and it >= min_it:
                    break
        if debug:
            import sys as _sys
            print(f"    stage {size_s}px/{ns}x{ns}: {it + 1} iters, "
                  f"loss={best:.6f} (fid={fid_v:.6f}, fair={fair_v:.6f}, "
                  f"w*fair={fair_weight * fair_v:.6f})",
                  file=_sys.stderr, flush=True)

    if len(tail) > 1:
        with torch.no_grad():
            for i, p in enumerate(tail_params):
                p.copy_(torch.stack([snap[i] for snap in tail]).mean(0))
            for cp in color_params:
                cp[3] = 1.0

    # ---- rebuild fitted chains from final parameters ----------------------
    new_fitted = {}
    with torch.no_grad():
        for eid in fitted:
            n = len(fitted[eid])
            fwd = edge_points(eid, False)
            pts = edges[eid]["pts"]
            if is_closed_edge[eid]:
                last = fwd[0]
            else:
                last = node_params[tuple(pts[-1])]
            rows = torch.cat([fwd, last.unsqueeze(0)]).numpy()
            new_fitted[eid] = [tuple(rows[3 * k]) + tuple(rows[3 * k + 1])
                               + tuple(rows[3 * k + 2]) + tuple(rows[3 * k + 3])
                               for k in range(n)]

    # ---- fold optimized fills back into the palette ------------------------
    new_centers = centers
    max_drift = 0.0
    if color_params:
        new_centers = np.array(centers, copy=True)
        with torch.no_grad():
            for r, cp in zip(order, color_params):
                rgb = cp[:3].numpy() * 255.0
                drift = float(np.max(np.abs(
                    rgb - np.asarray(centers[r][:3], dtype=np.float64))))
                max_drift = max(max_drift, drift)
                new_centers[r] = np.clip(np.round(rgb), 0, 255).astype(
                    new_centers.dtype)

    if ctx.get("split_paths"):
        from boundary_split import _emit_regions_split
        svg = _emit_regions_split(labels, new_centers, loops, new_fitted, edges)
    else:
        svg, _ = boundary._emit_regions(labels, new_centers, loops, new_fitted)
    if return_info:
        return svg, {"max_color_drift": max_drift}
    return svg


def _resize(rgb, w, h):
    import cv2
    return cv2.resize(rgb, (w, h), interpolation=cv2.INTER_AREA)


def available() -> bool:
    try:
        import pydiffvg  # noqa: F401
        return True
    except Exception:
        return False
