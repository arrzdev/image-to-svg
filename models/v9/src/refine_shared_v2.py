"""Differentiable refinement in the SHARED-EDGE parameterization — fast path.

Same honesty property as refine_shared.py: ONE tensor per boundary-edge
interior + ONE per junction node; every region path is rebuilt each iteration
by differentiable concatenation of the shared tensors, so region overlap is
not expressible and shared boundaries coincide by construction at every step.

What changed vs v1 (why it is ~3x faster at equal quality):
- The diffvg CPU backward pass is >90% of wall-clock and scales linearly with
  rendered pixels x AA samples. v1 spent every iteration at 512px / 2x2
  (~2.1s/iter on one core).
- Parameters now live in LATTICE coordinates (label-map space) instead of
  render space, so the render resolution can change mid-run: a coarse
  256px/2x2 stage moves the geometry cheaply (0.6s/iter), then a full-res
  512px polish runs at 1x1 sampling (0.6s/iter, 3.7x cheaper than 2x2).
- 1x1 sampling makes the gradient noisy; instead of paying for 2x2 the
  polish stage averages the parameters over its last `avg_tail` iterations
  (Polyak-style tail averaging), which cancels the jitter for free. Measured
  on the elephant scene this BEATS a 2x2 polish of equal wall-clock and
  matches v1 final quality within 0.001.
- Early stopping is per stage; the noisy 1x1 stage is forced to run a
  minimum number of iterations (4th element of its stage tuple) because its
  loss readings stall-count too eagerly.
- Per-region fill-color optimization (ported from refine_shared_c): each
  region's fill is a small-lr parameter on a second Adam (clamped to [0,1],
  alpha pinned to 1) so the quantized palette can settle alongside the
  geometry. Colors step only in the last stage, which the colors-on default
  schedule makes a short full-res 2x2 stage (see DEFAULT_STAGES_COLOR — the
  color gradient is dishonest under 1x1 sampling or coarse targets). Color
  tensors ride the same Polyak tail average as the geometry and are folded
  back into `centers` before emission. Default ON (~+0.005 q, ~3% max drift
  toward the source); optimize_colors=False reproduces the previous
  geometry-only two-stage behavior exactly.
"""
from __future__ import annotations

import numpy as np

# (render_size, aa_samples, max_iters[, min_iters]) per stage.
DEFAULT_STAGES = ((256, 2, 30), (512, 1, 30, 26))
# Colors-on default: colors only step in the LAST stage, and that stage must
# be full-res 2x2 — under 1x1 sampling (or a downscaled target) the fills
# absorb AA/edge-bleed error instead of honest palette signal (measured:
# colors in the 1x1 stage LOWER quality by 0.013+ with ~30/255 drift, while a
# 2x2 tail stage reproduces v1+colors drift of ~8/255). The 1x1 stage is
# shortened to part-fund the more expensive 2x2 color/polish tail.
DEFAULT_STAGES_COLOR = ((256, 2, 30), (512, 1, 26, 22), (512, 2, 14, 12))


def refine_shared(ctx: dict, target_rgb, iters: int = 60, size: int = 512,
                  lr: float = 0.3, stages=None, patience: int = 4,
                  min_iters: int = 8, improve: float = 0.995,
                  final_decay: bool = False, avg_tail: int = 12,
                  optimize_colors: bool = True, color_lr: float = 0.008,
                  return_info: bool = False, debug: bool = False):
    """ctx: build_context() dict from the shared_boundary pipeline.
    target_rgb: HxWx3 uint8 (the processing raster the labels came from).
    stages: sequence of (render_size, aa_samples, max_iters[, min_iters]);
    defaults to DEFAULT_STAGES (DEFAULT_STAGES_COLOR when optimize_colors).
    `iters`/`size` are kept for signature compatibility with v1 and are only
    used when an explicit single-stage schedule is wanted via
    stages=[(size, 2, iters)].
    patience/min_iters/improve: per-stage early stopping — a stage stops after
    `patience` consecutive iterations whose loss fails to beat the stage best
    by factor `improve`, never before its min_iters (stage tuple's optional
    4th element overrides the global `min_iters`).
    final_decay: cosine-decay the lr over the last stage (1.0 -> 0.1).
    avg_tail: average the parameters over the last `avg_tail` iterations of
    the last stage before emitting (cancels low-sample gradient jitter).
    optimize_colors/color_lr: per-region fill colors as a second Adam param
    group (clamped [0,1], alpha pinned); colors step ONLY during the last
    stage — with the default color schedule that is a full-res 2x2 stage,
    the only regime where the color gradient is honest (see
    DEFAULT_STAGES_COLOR note). Colors ride the same Polyak tail average as
    the geometry and are folded back into the palette before emission.
    Returns refined SVG string (label-lattice coordinate space); with
    return_info=True returns (svg, info) where info reports color drift."""
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
    # open edge i: chain rows [a0, c,c,a, ..., c,c, aN] (1+3n) -> node a0,
    # node aN, interior rows[1:-1] (3n-1 rows). closed edge: rows[:-1] (3n).
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
    # v1 used lr=0.3 on render-space params at 512px (scale = 512/L); the
    # equivalent step in lattice space is lr / (512 / L). Adam's moments stay
    # valid across stage switches because the parameterization never changes.
    base_lr = lr * L / 512.0
    opt = torch.optim.Adam(params, lr=base_lr)
    # Colors live in [0,1] regardless of render size/lattice scale, so
    # color_lr needs no rescaling and no stage-decay coupling.
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
            loss = ((rgb - target) ** 2).mean()
            loss.backward()
            opt.step()
            # Colors only move during the final full-res stage: the coarse
            # stage's INTER_AREA-downsampled target blends neighboring
            # regions, so fills absorb edge bleed there (measured -0.013 q
            # and 29/255 drift when colors run from stage 1).
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
                  f"loss={best:.6f}", file=_sys.stderr, flush=True)

    if len(tail) > 1:
        with torch.no_grad():
            for i, p in enumerate(tail_params):
                p.copy_(torch.stack([snap[i] for snap in tail]).mean(0))
            # snapshots are already clamped/alpha-pinned, so the mean is too;
            # re-pin alpha defensively anyway.
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
