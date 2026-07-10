"""Differentiable refinement in the SHARED-EDGE parameterization.

Plain DiffVG on a shared-boundary scene cheats: each region's copy of a shared
edge is an independent tensor, and the loss happily moves the two copies APART
(regions overlap, AA seams get swallowed — measured mean 2.5px anchor
divergence). The metric improves; the deep-zoom structure is destroyed.

Here the scene is parameterized the way the geometry actually is: ONE tensor
per boundary edge interior + ONE tensor per junction node. Every region path
is rebuilt each iteration by differentiable concatenation (reversal = flip) of
the shared tensors, so overlap is not expressible — the gradient must move the
single shared boundary to the best compromise between both regions. Honest
gain, coincidence by construction at every iteration.

Variant _c: OPTIONAL per-region fill-color optimization. The quantized
palette caps post-DV quality on low num_colors runs (colors are frozen in
refine_shared); here each emitted region's fill is a small-lr parameter
(second Adam, clamped to [0,1], alpha pinned to 1) so the palette can settle
alongside the geometry.
"""
from __future__ import annotations

import numpy as np


def refine_shared(ctx: dict, target_rgb, iters: int = 60, size: int = 512,
                  lr: float = 0.3, optimize_colors: bool = True,
                  color_lr: float = 0.008, return_info: bool = False):
    """ctx: build_context() dict from the shared_boundary pipeline.
    target_rgb: HxWx3 uint8 (the processing raster the labels came from).
    Returns refined SVG string (label-lattice coordinate space); with
    return_info=True returns (svg, info) where info reports color drift."""
    import torch
    import pydiffvg
    import boundary

    pydiffvg.set_use_gpu(False)
    try:
        import os
        torch.set_num_threads(max(2, (os.cpu_count() or 8) // 2))
    except Exception:
        pass

    labels, centers = ctx["labels"], ctx["centers"]
    edges, loops, fitted = ctx["edges"], ctx["loops"], ctx["fitted"]
    H, W = labels.shape
    scale = size / max(W, H)
    RW, RH = int(W * scale), int(H * scale)

    # ---- shared parameters ------------------------------------------------
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
        return np.asarray(rows, dtype=np.float64) * scale

    import torch
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
    import pydiffvg as dv
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

    target = torch.from_numpy(
        _resize(target_rgb, RW, RH).astype("float32") / 255.0)

    params = list(node_params.values()) + list(interior.values())
    opt = torch.optim.Adam(params, lr=lr)
    copt = torch.optim.Adam(color_params, lr=color_lr) if color_params else None
    render = dv.RenderFunction.apply

    best, stall = float("inf"), 0
    for it in range(iters):
        opt.zero_grad()
        if copt is not None:
            copt.zero_grad()
        shapes = []
        for lp, ncp in zip(path_specs, ncp_cache):
            pts = torch.cat([edge_points(eid, rev) for eid, rev in lp])
            shapes.append(dv.Path(num_control_points=ncp, points=pts,
                                  is_closed=True))
        args = dv.RenderFunction.serialize_scene(RW, RH, shapes, groups)
        img = render(RW, RH, 2, 2, it, None, *args)
        rgb = img[:, :, :3] * img[:, :, 3:4] + (1 - img[:, :, 3:4])
        loss = ((rgb - target) ** 2).mean()
        loss.backward()
        opt.step()
        if copt is not None:
            copt.step()
            with torch.no_grad():
                for cp in color_params:
                    cp.clamp_(0.0, 1.0)
                    cp[3] = 1.0   # fills stay opaque
        cur = float(loss.detach())
        if cur < best * 0.995:
            best, stall = cur, 0
        else:
            stall += 1
            if stall >= 6 and it >= 10:
                break

    # ---- rebuild fitted chains from final parameters ----------------------
    new_fitted = {}
    with torch.no_grad():
        for eid in fitted:
            n = len(fitted[eid])
            fwd = edge_points(eid, False) / scale
            pts = edges[eid]["pts"]
            if is_closed_edge[eid]:
                last = fwd[0]
            else:
                last = node_params[tuple(pts[-1])] / scale
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
