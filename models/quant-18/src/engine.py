"""The tournament engine: one call, many candidates, best SVG wins.

Instead of picking a pipeline+config up front, we:

  1. ANALYZE the image cheaply (palette size, edge density, dark-line fraction)
  2. GENERATE a diverse candidate portfolio adapted to that analysis
     (different pipelines, posterize/simplify variants, resolutions)
  3. SCORE every candidate in parallel on the process pool with the composite
     perceptual metric (quality; optionally complexity-penalized)
  4. Optionally REFINE the winner with a short coordinate ascent
  5. Return the winner + full leaderboard, and save a labeled contact sheet
     for visual (human or AI) inspection — the metric guides, eyes verify.

Made practical by the speed work: a candidate costs ~1s, so a 12-candidate
tournament lands in ~15s wall-clock.

CLI:
    python backend/engine.py <image-or-sample> [--mode fidelity|balanced|editable]
                             [--top 6] [--refine] [--workers N]
"""
from __future__ import annotations

import os as _os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ.setdefault(_v, "1")

import argparse
import json
import math
import sys
import time
import uuid
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from app import _prepare, SAMPLES                    # noqa: E402
from parallel import process_map, thread_map, default_workers, limit_native_threads  # noqa: E402
import sweep_worker                                   # noqa: E402

OUTPUTS = HERE.parent / "outputs"

# grail = the compact-editable mode: its λ must be strong enough that a clean
# ~1k-pt candidate beats a 80k-pt one of slightly higher raw quality, while
# still letting the safety net win when flat-color families collapse (~0.14).
LAMBDA = {"fidelity": 0.0, "balanced": 0.03, "editable": 0.06, "grail": 0.07,
          "fast": 0.07}


# ---------------------------------------------------------------- analysis

from imgstats import analyze  # shared with app._prepare (upscale gating)


# ---------------------------------------------------------------- portfolio

def portfolio(info: dict, mode: str) -> list:
    """Candidate list: (label, pipeline, params, process_dim, simplify_eps)."""
    if mode == "fast":
        # ~5s tier: shared-boundary curves only (each ~2s at 1024), no DV.
        # Gap-free by construction — the guarantee DV would soften, kept intact.
        sb = {"num_colors": 16, "merge_de": 12, "min_area": 120, "blur": 1}
        return [
            # smooth_win=5 (pipeline default) beats every unsmoothed config on
            # ALL axes at once: q 0.9151 @ 1337pts/18KB vs 0.9129 @ 1926/24KB.
            ("sb-t10", "shared_boundary", {**sb, "tol": 1.0}, 1024, 0.0),
            # Potrace-parsimony fitter: wobble-free by construction, beats
            # smooth+Schneider on all axes at opttol 0.2 (eye-verified 8k).
            ("sb-pars02", "shared_boundary", {**sb, "parsimony": 0.2}, 1024, 0.0),
            # bilateral aggregation rescues soft-shaded (AI-art) inputs:
            # rabbit's shattered coat seams come back solid (q .669->.757).
            ("sb-bilat", "shared_boundary", {**sb, "tol": 1.0, "preproc": "bilateral"}, 1024, 0.0),
            ("sb-k12", "shared_boundary", {**sb, "num_colors": 12, "tol": 1.0}, 1024, 0.0),
            # centerline strokes for thin line art: clean tapered tips,
            # constant widths, ~14-30% fewer points (won fox outright).
            ("sb-strokes", "stroke_hybrid", {**sb, "tol": 1.0}, 1024, 0.0),
            # width-constant contour network (eye-verified Recraft-class line
            # confidence; 703 pts / 39 paths / 2.6s on the elephant).
            ("sb-contour", "contour_lines", {**sb}, 1024, 0.0),
            # gradient safety nets at 1024: a 2048 vtracer run forces a second
            # prep + a 30k-pt metric eval and doubles the tier's wall-clock.
            # vt-simplify1 is NON-posterize — on gradient/texture content every
            # flat-color candidate (incl. poster16) collapses to q~0.14.
            ("vt-poster16-s1", "vtracer", {"posterize": 16}, 1024, 1.0),
            ("vt-simplify1", "vtracer", {}, 1024, 1.0),
        ]
    if mode == "grail":
        # Recraft-corner family: flat-partition regions + Schneider fitting.
        # Few candidates, DV refinement finishes the job (see tournament()).
        base = {"num_colors": 16, "merge_de": 12, "smoothing": "schneider",
                "corner_deg": 40, "min_area": 120, "blur": 1, "morph": 0}
        sb = {"num_colors": 16, "merge_de": 12, "min_area": 120, "blur": 1}
        # kmeans partitions are a seeded lottery (good draw 0.89, bad draw
        # 0.14, same config) — so the candidates ARE different draws, and the
        # tournament judges the maps.
        return [
            # Shared-boundary curves: fits each region boundary ONCE (zero
            # gaps/spurs by construction). Shared-edge DV converges post-DV
            # quality to ~0.93 REGARDLESS of fit coarseness (measured tol
            # 1.0..4.0 all land 0.927-0.933), so coarse fits dominate the
            # objective — points are nearly free to cut pre-DV.
            # Frontier (pareto sweep): post-DV q falls off gradually past
            # tol=3 (0.9303) -> tol=4 (0.9258) -> tol=5 (0.9207, 679 pts —
            # UNDER Recraft's 690); cliff below ~660 pts. smooth_win=13
            # strictly beats 9 at coarse tol. num_colors=12 is poisonous
            # (frozen fill colors can't absorb palette error).
            # Potrace-parsimony family: minimal knots, structurally
            # wobble-free (0.5/1.0 march into the Recraft point corner:
            # 1023pts@0.9157 / 937@0.9134 pre-DV).
            ("grail-pars05", "shared_boundary", {**sb, "parsimony": 0.5}, 1024, 0.0),
            ("grail-pars10", "shared_boundary", {**sb, "parsimony": 1.0}, 1024, 0.0),
            ("grail-bilat", "shared_boundary", {**sb, "tol": 3.0, "smooth_win": 9, "preproc": "bilateral"}, 1024, 0.0),
            ("grail-ms", "shared_boundary", {**sb, "parsimony": 0.5, "preproc": "meanshift"}, 1024, 0.0),
            ("grail-sb50-w13", "shared_boundary", {**sb, "tol": 5.0, "smooth_win": 13}, 1024, 0.0),
            ("grail-sb40-w13", "shared_boundary", {**sb, "tol": 4.0, "smooth_win": 13}, 1024, 0.0),
            ("grail-sb30-w9", "shared_boundary", {**sb, "tol": 3.0, "smooth_win": 9}, 1024, 0.0),
            ("grail-sb10", "shared_boundary", {**sb, "tol": 1.0}, 1024, 0.0),
            # edge-support dissolution: kills quantizer-manufactured shading
            # splits (pizza +0.03 obj) but can merge faint REAL contours
            # (shield collapses) — the judge decides per image.
            ("grail-sb-d18", "shared_boundary", {**sb, "tol": 3.0, "smooth_win": 9, "dissolve": 18.0}, 1024, 0.0),
            ("grail-sb12k", "shared_boundary", {**sb, "num_colors": 12, "tol": 1.5}, 1024, 0.0),
            ("grail-sb24k", "shared_boundary", {**sb, "num_colors": 24, "tol": 1.5}, 1024, 0.0),
            # centerline-stroke hybrid: cleanest tips/widths at deep zoom,
            # fewer points; not DV-refined (stroked paths stay untouched).
            ("grail-strokes", "stroke_hybrid", {**sb, "tol": 1.0}, 1024, 0.0),
            ("grail-contour", "contour_lines", {**sb}, 1024, 0.0),
            # quantize family kept for diversity but NOT DV-refined in grail
            # mode: independent-point DV cheats via region overlap (hairlines
            # at deep zoom) — only the shared-edge parameterization is honest.
            ("grail-s20", "quantize_contours", {**base, "simplify": 2.0, "seed": 0}, 1024, 0.0),
            ("grail-k24", "quantize_contours", {**base, "num_colors": 24, "simplify": 1.5, "seed": 0}, 1024, 0.0),
            ("vt-poster16-s1", "vtracer", {"posterize": 16}, 2048, 1.0),  # sanity rival
            # Safety net: flat-color families GENUINELY collapse on gradient
            # content (crystals: every posterized candidate ~0.14, correctly
            # flagged by `local`). A non-posterize candidate keeps grail mode
            # gracefully degrading to a solid conversion on such images.
            ("vt-simplify1", "vtracer", {}, 2048, 1.0),
        ]
    cands = [
        ("vt-fidelity",      "vtracer", {}, 2048, 0.0),
        ("vt-simplify1",     "vtracer", {}, 2048, 1.0),
        ("vt-simplify2",     "vtracer", {}, 2048, 2.0),
        ("vt-poster16",      "vtracer", {"posterize": 16}, 2048, 0.0),
        ("vt-poster16-s1",   "vtracer", {"posterize": 16}, 2048, 1.0),
        ("vt-poster24",      "vtracer", {"posterize": 24}, 2048, 0.0),
        ("potrace-k12",      "potrace_layers", {"num_colors": 12, "gap_fill": 1}, 1536, 0.0),
        ("potrace-k16",      "potrace_layers", {"num_colors": 16, "gap_fill": 1}, 1536, 0.0),
    ]
    if info["kind"] == "flat":
        cands += [
            ("quant-k8",     "quantize_contours", {"num_colors": 8}, 1024, 0.0),
            ("quant-k12",    "quantize_contours", {"num_colors": 12}, 1024, 0.0),
            ("potrace-k8",   "potrace_layers", {"num_colors": 8, "gap_fill": 1}, 1536, 0.0),
        ]
        # mono-direct is cheap and CHAMPION-grade on glyphs (beats published
        # Potrace on SVG-Bench fonts: 0.0017/0.990 vs 0.002/0.988) — field it
        # for every flat image; anti-aliasing inflates n_colors so a palette
        # gate would wrongly exclude it. The judge decides.
        cands += [
            ("mono-direct", "potrace_layers", {"mono": True}, 2048, 0.0),
        ]
    if info["kind"] == "lineart":
        cands += [
            ("vt-poster12",  "vtracer", {"posterize": 12}, 2048, 0.0),
            ("vt-poster20-s1", "vtracer", {"posterize": 20}, 2048, 1.0),
        ]
    if info["kind"] == "detailed":
        cands += [
            ("vt-hi-3072",   "vtracer", {}, 3072, 0.0),
            ("vt-hi-3072-s1", "vtracer", {}, 3072, 1.0),
        ]
    if mode == "editable":
        cands += [
            ("vt-poster16-s2", "vtracer", {"posterize": 16}, 2048, 2.0),
            ("vt-simplify3",  "vtracer", {}, 2048, 3.0),
        ]
    return cands


# ---------------------------------------------------------------- DV worker

def _dv_shared_worker(args):
    """Shared-boundary DV refinement of ONE candidate, in a child process.

    The 2-3 grail refine targets are independent torch/pydiffvg CPU jobs that
    used to run sequentially in the main process (the dominant grail cost);
    each now runs here so they proceed concurrently. The certified
    refine_shared_v2 module is called UNCHANGED — this only rebuilds its
    inputs from picklable pieces (paths + params) and caps torch's intra-op
    threads so N concurrent refiners don't oversubscribe the machine.

    args: (pp, proc_path, eval_path, ow, oh, params, lam, torch_threads)
    Returns {"svg", "metrics", "objective"} on success, None when the refiner
    declines, or {"__error__": traceback} (loud — a dead refiner once silently
    cost pizza its win).
    """
    (pp, proc_path, eval_path, ow, oh, params, lam, torch_threads) = args
    try:
        import torch
        torch.set_num_threads(max(1, torch_threads))
        # refine_shared_v2 sets its own single-process-tuned thread count (6);
        # under a pool of N refiners the parent's cap must win, so neutralize
        # further set_num_threads calls in THIS process only. (Orchestration —
        # the certified module itself is untouched.)
        torch.set_num_threads = lambda *_a, **_k: None

        from PIL import Image as _Im
        from pipelines import get_pipeline
        from svgutil import fit_svg_size
        # v3 = v2 + deadband fidelity + MVC curvature fairing (sliver-gated):
        # stops paying for sub-AA raster noise, so lines idealize instead of
        # wobbling. Validated GO across 5 images (eye equal-or-better, no new
        # artifact class; the ~0.5pt metric drop is the designed trade).
        import refine_shared_v3 as RS
        import metrics as M

        proc_img = np.asarray(_Im.open(proc_path).convert("RGB"))
        ctx = get_pipeline("shared_boundary").build_context(pp, params)
        refined = RS.refine_shared(ctx, proc_img)
        if not refined:
            return None
        refined = fit_svg_size(refined, ow, oh)
        eval_img = np.asarray(_Im.open(eval_path).convert("RGB"))
        m2 = M.all_metrics(refined, eval_img)
        obj2 = (m2.get("quality") or 0) - lam * math.log10(max(1, m2.get("num_points", 1)))
        return {"svg": refined, "metrics": m2, "objective": obj2}
    except Exception:
        import traceback
        return {"__error__": traceback.format_exc()}


# ---------------------------------------------------------------- tournament

def tournament(raw: bytes, mode: str = "fidelity", workers: int = None,
               top_n: int = 6, refine: bool = False, dv: bool = False) -> dict:
    limit_native_threads()
    workers = workers or default_workers()
    lam = LAMBDA.get(mode, 0.0)
    uid = uuid.uuid4().hex[:8]
    t0 = time.time()
    phases = {}          # phase -> seconds, reported in the result for tuning
    _pt = [t0]

    def _phase(name):
        now = time.time()
        phases[name] = round(now - _pt[0], 1)
        _pt[0] = now

    # quick analysis on a small decode
    from PIL import Image
    import io
    probe = np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"))
    info = analyze(probe)

    cands = portfolio(info, mode)

    # prepare rasters per distinct dim
    prep, files = {}, []
    for dim in sorted({c[3] for c in cands}):
        proc, ev, wh = _prepare(raw, dim)
        pp = OUTPUTS / f"_tn_{uid}_{dim}_proc.png"
        ep = OUTPUTS / f"_tn_{uid}_{dim}_eval.png"
        proc.save(pp)
        ev.save(ep)
        prep[dim] = (str(pp), str(ep), wh)
        files += [pp, ep]

    jobs = []
    for i, (label, pid, params, dim, eps) in enumerate(cands):
        pp, ep, (ow, oh) = prep[dim]
        jobs.append((i, pid, params, pp, ep, ow, oh, eps, True))

    _phase("prep")
    outcomes = process_map(sweep_worker.run_job, jobs, workers=workers,
                           initializer=sweep_worker.init_worker)
    _phase("generate")

    board = []
    for o in outcomes:
        if not o or "__error__" in o or "error" in o or not o.get("metrics"):
            continue
        i = o["tag"]
        label, pid, params, dim, eps = cands[i]
        m = o["metrics"]
        q = m.get("quality")
        if q is None:
            continue
        obj = q - lam * math.log10(max(1, m.get("num_points", 1)))
        board.append({"label": label, "pipeline": pid, "params": params,
                      "process_dim": dim, "simplify_eps": eps,
                      "objective": round(obj, 4), "metrics": m, "svg": o["svg"]})
    board.sort(key=lambda r: r["objective"], reverse=True)

    if refine and board:
        try:
            import optimize as opt
            w = board[0]
            start = dict(opt.START[w["pipeline"]])
            start.update(w["params"])
            start["process_dim"] = w["process_dim"]
            start["simplify_eps"] = w["simplify_eps"]
            ev2 = opt.Evaluator(raw, w["pipeline"], lam, workers)
            best, obj, m, _ = opt.coordinate_ascent(
                ev2, opt.SPACES[w["pipeline"]], start, budget=24)
            if obj > board[0]["objective"] + 1e-4:
                pp, _, (ow, oh) = ev2._prep(best["process_dim"])
                from pipelines import get_pipeline
                from svgutil import fit_svg_size
                from postprocess import simplify_svg
                params = {k: v for k, v in best.items()
                          if k not in ("process_dim", "simplify_eps")}
                svg = get_pipeline(w["pipeline"]).run(pp, params)
                if best["simplify_eps"] > 0:
                    svg = simplify_svg(svg, best["simplify_eps"])
                svg = fit_svg_size(svg, ow, oh)
                board.insert(0, {"label": w["label"] + "+refined",
                                 "pipeline": w["pipeline"], "params": params,
                                 "process_dim": best["process_dim"],
                                 "simplify_eps": best["simplify_eps"],
                                 "objective": round(obj, 4), "metrics": m, "svg": svg})
            ev2.cleanup()
        except Exception:
            pass  # refinement is best-effort

    # Optional DiffVG post-refinement of the winner: gradient-descend its
    # control points against the trace raster. Only for low-complexity scenes
    # (diverges on dense stacked-patch scenes); zero added points.
    # (Runs before prep-file cleanup — it needs the proc/eval rasters.)
    if mode == "grail":
        dv = True   # refinement IS the grail recipe's second half
    if dv and board:
        import refine_diffvg as RD
        import metrics as M
        from PIL import Image as _Im

        # Grail mode: refine ONLY shared-boundary candidates (independent-point
        # DV cheats by sliding region copies apart — hairlines at deep zoom;
        # refine_shared is the honest path). Shared-edge DV converges post-DV
        # quality regardless of fit coarseness, so the best target is the
        # FEWEST-POINTS sane partition, plus the pre-DV leader if it differs.
        if mode == "grail":
            # Partition sanity is judged by the BEST sb candidate (the fine
            # fit): coarse fits can pre-score 0.14 on images where a warped
            # region tanks the worst-region metric, yet shared DV fully
            # recovers them (pizza 0.14->0.88, rabbit 0.14->0.85). Only when
            # ALL sb candidates collapse (gradient content, ~0.14 across the
            # board) is the partition genuinely broken — then skip DV.
            sb_all = [r for r in board if r["pipeline"] == "shared_boundary"]
            sb_best = max((r["metrics"].get("quality") or 0 for r in sb_all),
                          default=0.0)
            sane = sb_all if sb_best >= 0.70 else []
            targets = []
            if sane:
                # Refine the two most compact partitions (post-DV quality is
                # coarseness-insensitive) AND the highest-quality fine fit.
                # Coarse fits may carry pre-DV slivers — on some images
                # shared DV heals them (elephant tol5: pre-DV damaged, post-DV
                # integrity 1.0), on others not (pizza) — so damage is judged
                # AFTER refinement by the final integrity penalty below, and
                # the fine fit guarantees a clean refined candidate either way.
                by_pts = sorted(sane, key=lambda r: r["metrics"]["num_points"])
                fine = max(sane, key=lambda r: r["metrics"].get("quality") or 0)
                for cand in (by_pts[0],
                             by_pts[1] if len(by_pts) > 1 else None,
                             fine):
                    if cand is not None and cand not in targets:
                        targets.append(cand)
        else:
            targets = [board[0]]

        inserted = False
        eligible = [w for w in targets
                    if RD.available()
                    and w["metrics"]["num_points"] <= RD.MAX_POINTS
                    and w["metrics"]["num_paths"] <= RD.MAX_PATHS]
        # independent-point DV CHEATS on shared-boundary scenes: the two
        # copies of every shared edge drift apart (measured 2.5px mean) —
        # regions overlap to swallow AA seams, wrecking the deep-zoom
        # structure the pipeline exists for. Refine those in the shared-edge
        # parameterization instead (refine_shared_v2: staged 256->512 +
        # Polyak tail, guards certified): overlap is not expressible,
        # coincidence holds at every iteration.
        shared = [w for w in eligible if w["pipeline"] == "shared_boundary"]
        other = [w for w in eligible if w["pipeline"] != "shared_boundary"]

        if shared:
            # The refines are independent torch/pydiffvg CPU jobs — run them
            # concurrently in child processes (they used to run sequentially
            # in the main process and dominated grail wall-clock). torch
            # intra-op threads are capped per worker so the pool owns the
            # parallelism; ceiling 6 matches refine_shared_v2's own
            # single-process tuning when there is only one target.
            n = len(shared)
            cap = min(6, max(2, (_os.cpu_count() or 8) // n))
            jobs2 = []
            for w in shared:
                pp, ep, (ow, oh) = prep[w["process_dim"]]
                jobs2.append((pp, pp, ep, ow, oh, w["params"], lam, cap))
            _tdv = time.time()
            outs = process_map(_dv_shared_worker, jobs2, workers=n)
            phases["dv_shared_pool"] = round(time.time() - _tdv, 1)
            for w, o in zip(shared, outs):
                if o and "__error__" in o:
                    # a dead refiner must be loud — it silently cost pizza its win
                    print(f"[dv {w['label']}] {o['__error__']}", file=sys.stderr)
                    continue
                if o and o["objective"] > w["objective"]:
                    board.append({**w, "label": w["label"] + "+dv",
                                  "objective": round(o["objective"], 4),
                                  "metrics": o["metrics"], "svg": o["svg"]})
                    inserted = True

        for w in other:
            _tdv = time.time()
            m = w["metrics"]
            proc_img = np.asarray(_Im.open(prep[w["process_dim"]][0]).convert("RGB"))
            eval_img = np.asarray(_Im.open(prep[w["process_dim"]][1]).convert("RGB"))
            refined = RD.refine_svg_str(w["svg"], proc_img, num_points=m["num_points"])
            if refined:
                m2 = M.all_metrics(refined, eval_img)
                obj2 = (m2.get("quality") or 0) - lam * math.log10(max(1, m2.get("num_points", 1)))
                if obj2 > w["objective"]:
                    board.append({**w, "label": w["label"] + "+dv",
                                  "objective": round(obj2, 4),
                                  "metrics": m2, "svg": refined})
                    inserted = True
            phases[f"dv:{w['label']}"] = round(time.time() - _tdv, 1)
        if inserted:
            board.sort(key=lambda r: r["objective"], reverse=True)
        _phase("dv_total")

    if mode == "grail" and board:
        # Structural-integrity pass: the perceptual metric renders at 1536 and
        # CANNOT see subpixel boundary damage (independent-point DV inflated
        # quality +0.022 while opening deep-zoom hairlines). structcheck reads
        # the alpha plane of a 4096 transparent render — hairlines score ~0.06,
        # clean coincident boundaries 0.93-1.0 — so cheated candidates lose
        # on merit here (~1s per candidate, top of board only).
        import structcheck

        def _intg(r):
            try:
                return structcheck.integrity(r["svg"])["score"]
            except Exception:
                return 1.0

        # the render is a resvg subprocess (GIL released) — thread it.
        head = board[:6]
        for r, s in zip(head, thread_map(_intg, head, workers=len(head))):
            s = float(s) if isinstance(s, (int, float)) else 1.0
            r["metrics"]["integrity"] = round(s, 3)
            r["objective"] = round(r["objective"] - 0.08 * (1.0 - s), 4)
        board.sort(key=lambda r: r["objective"], reverse=True)
        _phase("structcheck")

    for f in files:
        try:
            Path(f).unlink()
        except OSError:
            pass

    # Lossless output shrink on the returned candidates (scores already final;
    # drift from 1dp rounding is ≤0.004 and the download is what users keep).
    from svgopt import optimize_svg
    board = board[:top_n]
    for r in board:
        try:
            r["svg"] = optimize_svg(r["svg"])
        except Exception:
            pass

    return {"analysis": info, "mode": mode, "seconds": round(time.time() - t0, 1),
            "candidates": len(cands), "board": board, "phases": phases}


# ---------------------------------------------------------------- contact sheet

def contact_sheet(raw: bytes, result: dict, out_path: Path, cell: int = 340):
    """Source + top candidates rendered side by side, labeled with scores."""
    import io
    from PIL import Image, ImageDraw
    from render import svg_to_rgb

    board = result["board"]
    src = Image.open(io.BytesIO(raw)).convert("RGB")
    src.thumbnail((cell - 8, cell - 8))
    cols = 1 + len(board)
    sheet = Image.new("RGB", (cell * cols, cell + 40), (30, 30, 36))
    d = ImageDraw.Draw(sheet)
    d.text((6, 4), f"SOURCE  [{result['analysis']['kind']}]", fill=(230, 230, 240))
    sheet.paste(src, (4, 24))
    for i, r in enumerate(board):
        m = r["metrics"]
        d.text(((i + 1) * cell + 6, 4),
               f"{r['label']}  q={m['quality']:.3f} obj={r['objective']:.3f}",
               fill=(140, 230, 170) if i == 0 else (230, 230, 240))
        d.text(((i + 1) * cell + 6, cell + 26),
               f"{m['num_paths']}p/{m['num_points']}pt {m['gzip_bytes'] // 1024}KB",
               fill=(150, 155, 170))
        img = Image.fromarray(svg_to_rgb(r["svg"], cell - 8, cell - 8))
        sheet.paste(img, ((i + 1) * cell + 4, 24))
    sheet.save(out_path)


def _load_bytes(arg: str) -> bytes:
    p = Path(arg)
    if p.exists():
        return p.read_bytes()
    sp = SAMPLES / arg
    if sp.exists():
        return sp.read_bytes()
    sys.exit(f"image not found: {arg}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--mode", default="fidelity", choices=list(LAMBDA.keys()))
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--refine", action="store_true")
    ap.add_argument("--dv", action="store_true",
                    help="DiffVG post-refine the winner (low-complexity scenes only)")
    ap.add_argument("--workers", type=int, default=default_workers())
    args = ap.parse_args()

    raw = _load_bytes(args.image)
    res = tournament(raw, mode=args.mode, workers=args.workers,
                     top_n=args.top, refine=args.refine, dv=args.dv)
    stem = Path(args.image).stem
    print(f"analysis: {res['analysis']}  ({res['candidates']} candidates, {res['seconds']}s)")
    if res.get("phases"):
        print("phases: " + "  ".join(f"{k}={v}s" for k, v in res["phases"].items()))
    print(f"{'#':>2} {'label':>16} {'obj':>7} {'qual':>6} {'local':>6} {'paths':>6} {'pts':>7} {'gzip':>7}")
    for i, r in enumerate(res["board"], 1):
        m = r["metrics"]
        print(f"{i:>2} {r['label']:>16} {r['objective']:>7.4f} {m['quality']:>6.4f} "
              f"{m['local_score']:>6.3f} {m['num_paths']:>6} {m['num_points']:>7} "
              f"{m['gzip_bytes'] // 1024:>6}K")

    winner = res["board"][0]
    (OUTPUTS / f"tournament_{stem}.svg").write_text(winner["svg"])
    sheet = OUTPUTS / f"tournament_{stem}.png"
    contact_sheet(raw, res, sheet)
    print(f"\nwinner: {winner['label']}  -> outputs/tournament_{stem}.svg")
    print(f"contact sheet -> {sheet}")


if __name__ == "__main__":
    main()
