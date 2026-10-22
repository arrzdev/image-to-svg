"""DiffVG differentiable refinement (research notes #5/#6): take a traced SVG
as INITIALIZATION and gradient-descend its bezier control points + fill colors
against the source raster. The tracer provides topology; optimization provides
pixel alignment.

Experimental. Requires the diffvg build (torch + native module). CPU rendering
is slow on complex scenes — start with logos / low-point winners.

Usage:
    python backend/refine_diffvg.py <image-or-sample> [--iters 60] [--size 256]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def os_cpu():
    import os
    return os.cpu_count()


def refine(svg_path: str, target_rgb, iters: int = 60, size: int = 256,
           lr_pts: float = 0.5, lr_color: float = 0.01, freeze_colors: bool = False):
    """Returns (refined_svg_path, losses). target_rgb: HxWx3 uint8 numpy."""
    import numpy as np
    import torch
    import pydiffvg

    pydiffvg.set_use_gpu(False)
    # The engine pins OMP threads to 1 so the process POOL owns parallelism —
    # but DV runs in the MAIN process where torch can happily use half the
    # cores without oversubscribing anyone.
    try:
        torch.set_num_threads(max(2, (os_cpu() or 8) // 2))
    except Exception:
        pass
    canvas_w, canvas_h, shapes, shape_groups = pydiffvg.svg_to_scene(svg_path)

    # Render at a reduced size for speed: scale scene coords.
    scale = size / max(canvas_w, canvas_h)
    W, H = int(canvas_w * scale), int(canvas_h * scale)
    for s in shapes:
        if hasattr(s, "points"):
            s.points = s.points * scale
        for attr in ("stroke_width",):
            if hasattr(s, attr):
                setattr(s, attr, getattr(s, attr) * scale)

    import cv2
    tgt = cv2.resize(target_rgb, (W, H), interpolation=cv2.INTER_AREA)
    target = torch.from_numpy(tgt.astype("float32") / 255.0)

    pts_vars, color_vars = [], []
    for s in shapes:
        if hasattr(s, "points"):
            s.points.requires_grad = True
            pts_vars.append(s.points)
    for g in shape_groups:
        if g.fill_color is not None and not freeze_colors:
            g.fill_color.requires_grad = True
            color_vars.append(g.fill_color)

    render = pydiffvg.RenderFunction.apply
    opt_pts = torch.optim.Adam(pts_vars, lr=lr_pts)
    opt_col = torch.optim.Adam(color_vars, lr=lr_color) if color_vars else None

    losses = []
    best = float("inf")
    stall = 0
    for it in range(iters):
        opt_pts.zero_grad()
        if opt_col: opt_col.zero_grad()
        scene_args = pydiffvg.RenderFunction.serialize_scene(W, H, shapes, shape_groups)
        img = render(W, H, 2, 2, it, None, *scene_args)
        # composite over white like the metric does
        rgb = img[:, :, :3] * img[:, :, 3:4] + (1 - img[:, :, 3:4])
        loss = ((rgb - target) ** 2).mean()
        loss.backward()
        opt_pts.step()
        if opt_col: opt_col.step()
        for g in shape_groups:
            if g.fill_color is not None:
                g.fill_color.data.clamp_(0.0, 1.0)
        cur = float(loss.detach())
        losses.append(cur)
        # Early stop on plateau: most runs converge well before the budget
        # (logged curves flatten by ~iter 20-25); no point paying full price.
        if cur < best * 0.995:
            best = cur
            stall = 0
        else:
            stall += 1
            if stall >= 6 and it >= 10:
                break

    # scale back and save with our own serializer: pydiffvg.save_svg loses
    # subpath grouping (holes) and fill rules, destroying hole-y glyphs.
    for s in shapes:
        if hasattr(s, "points"):
            s.points = (s.points.detach() / scale)
    out_path = str(Path(svg_path).with_suffix("")) + "_refined.svg"
    Path(out_path).write_text(_scene_to_svg(canvas_w, canvas_h, shapes, shape_groups))
    return out_path, losses


def _path_to_d(shape) -> str:
    """pydiffvg Path -> SVG d string (lines + cubics, closed/open)."""
    import numpy as np
    pts = shape.points.detach().numpy() if hasattr(shape.points, "detach") else np.asarray(shape.points)
    ncp = shape.num_control_points.numpy() if hasattr(shape.num_control_points, "numpy") else shape.num_control_points
    d = f"M {pts[0][0]:.2f} {pts[0][1]:.2f} "
    i = 1
    n = len(pts)
    closed = bool(shape.is_closed)
    for seg, c in enumerate(ncp):
        c = int(c)
        if c == 0:
            end = pts[i % n]
            d += f"L {end[0]:.2f} {end[1]:.2f} "
            i += 1
        elif c == 2:
            c1, c2 = pts[i % n], pts[(i + 1) % n]
            end = pts[(i + 2) % n]
            d += (f"C {c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} {c2[1]:.2f} "
                  f"{end[0]:.2f} {end[1]:.2f} ")
            i += 3
        else:  # quadratic (1) — rare from our tracers; promote via 'Q'
            c1 = pts[i % n]
            end = pts[(i + 1) % n]
            d += f"Q {c1[0]:.2f} {c1[1]:.2f} {end[0]:.2f} {end[1]:.2f} "
            i += 2
    return d + ("Z" if closed else "")


def _scene_to_svg(w, h, shapes, shape_groups) -> str:
    import numpy as np
    body = []
    for g in shape_groups:
        ids = g.shape_ids.numpy() if hasattr(g.shape_ids, "numpy") else g.shape_ids
        d = " ".join(_path_to_d(shapes[int(i)]) for i in ids)
        if g.fill_color is None:
            fill = "none"
        else:
            c = g.fill_color.detach().numpy() if hasattr(g.fill_color, "detach") else np.asarray(g.fill_color)
            fill = f"#{int(round(c[0]*255)):02x}{int(round(c[1]*255)):02x}{int(round(c[2]*255)):02x}"
        rule = "evenodd" if getattr(g, "use_even_odd_rule", False) else "nonzero"
        body.append(f'<path d="{d}" fill="{fill}" fill-rule="{rule}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(w)}" height="{int(h)}" '
            f'viewBox="0 0 {int(w)} {int(h)}">\n' + "\n".join(body) + "\n</svg>\n")


def available() -> bool:
    try:
        import pydiffvg  # noqa: F401
        return True
    except Exception:
        return False


# Complexity gate. Dense scenes need a GENTLER lr: 0.5 diverges at 15k pts;
# tested convergent points on the lr curve: 0.05@15k (+0.023), 0.02@52k
# (+0.011), 0.01@91k (+0.005, 22s). Gate at 100k pts — beyond is untested.
MAX_POINTS = 100000
MAX_PATHS = 15000


def _adaptive_lr(num_points: int) -> float:
    """lr ~ inversely proportional to scene density, clamped to tested range.
    Upper clamp 0.35: at 0.5 a NEAR-OPTIMAL init (shared-boundary curves)
    oscillates and the loss RISES (measured 0.00053->0.00059); 0.3 on the same
    scene converged 0.00063->0.00027 and gained +0.022 quality."""
    return float(min(0.35, max(0.01, 0.5 * (2000.0 / max(num_points, 1)))))


def refine_svg_str(svg: str, target_rgb, iters: int = 40, size: int = 384,
                   num_points: int = 0):
    """String-in/string-out refinement wrapper. Returns refined svg or None."""
    if not available():
        return None
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".svg")
    os.close(fd)
    lr = _adaptive_lr(num_points) if num_points else 0.5
    # dense scenes: fewer iters at smaller render keeps wall-clock sane
    if num_points > 60000:
        iters, size = min(iters, 10), min(size, 256)
    elif num_points > 20000:
        iters, size = min(iters, 15), min(size, 256)
    elif num_points > 5000:
        iters, size = min(iters, 30), min(size, 256)
    elif num_points <= 3000:
        # compact scenes render fast — spend it on resolution + iters:
        # 512/60 beats 384/40 by +0.007 q on the same init (early stopping
        # keeps the real cost near ~40 iters).
        iters, size = max(iters, 60), max(size, 512)
    try:
        Path(path).write_text(svg)
        out_path, _ = refine(path, target_rgb, iters=iters, size=size,
                             lr_pts=lr, freeze_colors=True)
        return Path(out_path).read_text()
    except Exception:
        return None
    finally:
        for p in (path, path.rsplit(".", 1)[0] + "_refined.svg"):
            try:
                os.unlink(p)
            except OSError:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--iters", type=int, default=60)
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--freeze-colors", dest="freeze_colors", action="store_true")
    args = ap.parse_args()

    import numpy as np
    from app import _prepare, SAMPLES
    from pipelines import get_pipeline
    from svgutil import fit_svg_size
    import metrics as M

    p = Path(args.image)
    raw = (p if p.exists() else SAMPLES / args.image).read_bytes()
    proc, ev, (ow, oh) = _prepare(raw, 1024)
    proc_path = HERE.parent / "outputs" / "_dv_proc.png"
    proc.save(proc_path)
    src = np.asarray(ev)

    svg = fit_svg_size(get_pipeline("vtracer").run(str(proc_path), {}), ow, oh)
    init_path = HERE.parent / "outputs" / "_dv_init.svg"
    init_path.write_text(svg)
    m0 = M.all_metrics(svg, src)
    print(f"init:    q={m0['quality']} ssim={m0['ssim']} dE={m0['delta_e']} pts={m0['num_points']}")

    t0 = time.time()
    out_path, losses = refine(str(init_path), np.asarray(proc), iters=args.iters, size=args.size, freeze_colors=args.freeze_colors)
    dt = time.time() - t0
    refined = Path(out_path).read_text()
    m1 = M.all_metrics(refined, src)
    print(f"refined: q={m1['quality']} ssim={m1['ssim']} dE={m1['delta_e']} pts={m1['num_points']}")
    print(f"loss {losses[0]:.5f} -> {losses[-1]:.5f} over {args.iters} iters in {dt:.1f}s")
    print(f"Δquality = {m1['quality'] - m0['quality']:+.4f}")


if __name__ == "__main__":
    main()
