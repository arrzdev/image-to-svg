"""Programmatic optimization loop: search pipeline x params x resolution, rank
by the composite `quality` score, and report the best configs.

This is the payoff of a good objective function (see metrics.py): once "better"
is a reliable number, finding the best method + settings is just search.

Usage:
    python backend/sweep.py <image-or-sample> [options]

Options:
    --pipelines a,b,c   restrict to these pipeline ids (default: all)
    --dims 1024,2048    processing resolutions to try (default: 1024,2048)
    --top N             show top N configs (default: 12)
    --max N             cap total runs; randomly samples the grid if exceeded
    --lambda L          complexity penalty: objective = quality - L*log10(points)
    --seed N            RNG seed for sampling (default: 0)

Writes a full ranked JSON report to outputs/sweep_<image>.json.
"""
from __future__ import annotations

# Must run before numpy/OpenCV import so BLAS/OpenCV stay single-threaded and the
# worker pool (not the libraries) owns the parallelism. See parallel.py.
import os as _os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ.setdefault(_v, "1")

import argparse
import itertools
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import _prepare, SAMPLES            # noqa: E402
from pipelines import get_pipeline, REGISTRY  # noqa: E402
from svgutil import fit_svg_size              # noqa: E402
import metrics as M                           # noqa: E402
from parallel import process_map, default_workers, limit_native_threads  # noqa: E402
import sweep_worker                           # noqa: E402

# Per-pipeline search space: the parameters most worth tuning, each with a few
# candidate values. Extend freely -- the loop just takes the cartesian product.
SEARCH_SPACES = {
    "vtracer": {
        # cp=8 is settled (lower deletes objects); probe the remaining knobs.
        "filter_speckle": [1, 2],
        "corner_threshold": [30, 60],
        "layer_difference": [8, 16],
    },
    "potrace_layers": {
        # Widened after the local-completeness metric fix: more colors so dark
        # ridges / highlights survive posterization.
        "num_colors": [8, 12, 16],
        "gap_fill": [1, 2],
        "alphamax": [1.0, 1.2],
        "opttolerance": [0.2, 0.5],
    },
    "quantize_contours": {
        "num_colors": [8, 12, 16],
        "simplify": [1.0, 2.0],
        "corner_deg": [25, 40],
        "blur": [0, 1],
    },
}


def _grid(space: dict):
    keys = list(space.keys())
    for combo in itertools.product(*space.values()):
        yield dict(zip(keys, combo))


def _load_bytes(arg: str) -> bytes:
    p = Path(arg)
    if p.exists():
        return p.read_bytes()
    sp = SAMPLES / arg
    if sp.exists():
        return sp.read_bytes()
    sys.exit(f"image not found: {arg} (also tried samples/{arg})")


def build_configs(pipelines, dims):
    configs = []
    for pid in pipelines:
        space = SEARCH_SPACES.get(pid, {})
        for params in (_grid(space) or [{}]):
            for d in dims:
                configs.append({"pipeline": pid, "params": params, "process_dim": d})
    return configs


def objective(m: dict, lam: float) -> float:
    q = m.get("quality")
    if q is None:
        return -1.0
    if lam <= 0:
        return q
    pts = max(1, m.get("num_points", 1))
    return q - lam * np.log10(pts)


def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--pipelines", default=",".join(REGISTRY.keys()))
    ap.add_argument("--dims", default="1024,2048")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--lambda", dest="lam", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=default_workers())
    args = ap.parse_args()

    limit_native_threads()
    pipelines = [p for p in args.pipelines.split(",") if p in REGISTRY
                 and getattr(get_pipeline(p), "available", True)]
    dims = [int(x) for x in args.dims.split(",")]
    raw = _load_bytes(args.image)

    # Prepare each resolution once, up front; save trace + eval rasters to disk
    # for the worker processes.
    out_dir = Path(__file__).resolve().parent.parent / "outputs"
    prep_cache, prep_files = {}, []
    for d in dims:
        proc, ev, wh = _prepare(raw, d)
        proc_path = out_dir / f"_sweep_{d}_proc.png"
        eval_path = out_dir / f"_sweep_{d}_eval.png"
        proc.save(proc_path)
        ev.save(eval_path)
        prep_cache[d] = (str(proc_path), str(eval_path), wh)
        prep_files += [proc_path, eval_path]

    configs = build_configs(pipelines, dims)
    if args.max and len(configs) > args.max:
        random.seed(args.seed)
        configs = random.sample(configs, args.max)

    print(f"running {len(configs)} configs over {pipelines} at dims {dims} "
          f"on {args.workers} workers ...\n")
    t_start = time.time()

    jobs = []
    for i, cfg in enumerate(configs):
        proc_path, eval_path, (ow, oh) = prep_cache[cfg["process_dim"]]
        jobs.append((i, cfg["pipeline"], cfg["params"], proc_path, eval_path, ow, oh))

    def progress(done, total):
        print(f"\r  {done}/{total}", end="", flush=True)
    outcomes = process_map(sweep_worker.run_job, jobs, workers=args.workers,
                           on_progress=progress, initializer=sweep_worker.init_worker)
    print(f"   ({time.time() - t_start:.1f}s)\n")

    results = []
    for o in outcomes:
        if not o or "__error__" in o:
            continue
        i = o["tag"]
        if "error" in o:
            results.append({**configs[i], "error": o["error"], "objective": -1.0})
            continue
        m = o["metrics"]
        results.append({**configs[i], "metrics": m,
                        "objective": round(float(objective(m, args.lam)), 4)})

    for p in prep_files:
        try:
            p.unlink()
        except OSError:
            pass

    results.sort(key=lambda r: r["objective"], reverse=True)

    label = ("obj" if args.lam > 0 else "quality")
    print(f"{'#':>2}  {label:>7}  {'qual':>6} {'struct':>6} {'color':>6} {'edge':>6}  "
          f"{'pts':>5} {'gzip':>6}  pipeline @dim  params")
    for rank, r in enumerate(results[:args.top], 1):
        if "error" in r:
            print(f"{rank:>2}  FAILED  {r['pipeline']} @{r['process_dim']}: {r['error'][:40]}")
            continue
        m = r["metrics"]
        print(f"{rank:>2}  {r['objective']:>7.4f}  {m['quality']:>6.4f} {m['ms_ssim']:>6.4f} "
              f"{m['color_score']:>6.4f} {m['edge_score']:>6.4f}  {m['num_points']:>5} "
              f"{m['gzip_bytes']//1: >5}B  {r['pipeline']} @{r['process_dim']}  {r['params']}")

    out = Path(__file__).resolve().parent.parent / "outputs" / f"sweep_{Path(args.image).stem}.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nfull ranked report -> {out}")
    if results and "metrics" in results[0]:
        b = results[0]
        print(f"best: {b['pipeline']} @ {b['process_dim']} {b['params']}  quality={b['metrics']['quality']}")


if __name__ == "__main__":
    run()
