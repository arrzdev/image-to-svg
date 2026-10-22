"""Aggregate sweep across ALL sample images: find the pipeline + parameter
combination that generalizes best (highest mean `quality`), not just the winner
on a single image.

For each config (pipeline + param combo) we score every image and aggregate.
Processing resolution is fixed (default 1024) so the comparison isolates the
parameter effect rather than just rewarding higher resolution.

Usage:
    python backend/sweep_all.py [--dim 1024] [--pipelines a,b] [--top 10]
                                [--exclude logo_geometric,...] [--images a,b]
"""
from __future__ import annotations

# Pin native libs to one thread each before numpy/OpenCV load; the pool owns the
# parallelism (see parallel.py).
import os as _os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ.setdefault(_v, "1")

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from app import _prepare, SAMPLES            # noqa: E402
from pipelines import get_pipeline, REGISTRY  # noqa: E402
from svgutil import fit_svg_size              # noqa: E402
import metrics as M                           # noqa: E402
from sweep import SEARCH_SPACES, _grid        # noqa: E402
from parallel import process_map, default_workers, limit_native_threads  # noqa: E402
import sweep_worker                            # noqa: E402

OUTPUTS = HERE.parent / "outputs"
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")


def list_images(include, exclude):
    names = sorted(p.name for p in SAMPLES.iterdir() if p.suffix.lower() in IMG_EXT)
    if include:
        names = [n for n in names if Path(n).stem in include]
    if exclude:
        names = [n for n in names if Path(n).stem not in exclude]
    return names


def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dim", type=int, default=1024)
    ap.add_argument("--pipelines", default=",".join(REGISTRY.keys()))
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--images", default="")
    ap.add_argument("--exclude", default="")
    ap.add_argument("--workers", type=int, default=default_workers())
    args = ap.parse_args()

    limit_native_threads()
    pipelines = [p for p in args.pipelines.split(",")
                 if p in REGISTRY and getattr(get_pipeline(p), "available", True)]
    include = {s for s in args.images.split(",") if s}
    exclude = {s for s in args.exclude.split(",") if s}
    images = list_images(include, exclude)
    print(f"images ({len(images)}): {images}")
    print(f"pipelines: {pipelines}  dim={args.dim}\n")

    # Prepare each image once: save the trace raster + eval target to disk so
    # worker processes can load them (no big arrays over the pickling wire).
    prep = {}
    for name in images:
        raw = (SAMPLES / name).read_bytes()
        proc, ev, wh = _prepare(raw, args.dim)
        stem = Path(name).stem
        proc_path = OUTPUTS / f"_sa_{stem}_proc.png"
        eval_path = OUTPUTS / f"_sa_{stem}_eval.png"
        proc.save(proc_path)
        ev.save(eval_path)
        prep[name] = (str(proc_path), str(eval_path), wh)

    # Build config list, then a flat (config, image) job list for the pool.
    configs = []
    for pid in pipelines:
        for params in _grid(SEARCH_SPACES.get(pid, {})):
            configs.append((pid, params))
    jobs = []
    for ci, (pid, params) in enumerate(configs):
        for name in images:
            proc_path, eval_path, (ow, oh) = prep[name]
            jobs.append(((ci, name), pid, params, proc_path, eval_path, ow, oh))
    total_runs = len(jobs)
    print(f"{len(configs)} configs x {len(images)} images = {total_runs} runs "
          f"on {args.workers} workers\n")

    t_start = time.time()
    def progress(done, total):
        if done % 50 == 0 or done == total:
            el = time.time() - t_start
            eta = el / done * (total - done)
            print(f"\r  {done}/{total}  ({el:.0f}s elapsed, ~{eta:.0f}s left)", end="", flush=True)
    outcomes = process_map(sweep_worker.run_job, jobs, workers=args.workers,
                           on_progress=progress, initializer=sweep_worker.init_worker)
    print(f"\r  done {total_runs}/{total_runs} in {time.time()-t_start:.0f}s\n")

    # Aggregate job outcomes back per config.
    agg = {ci: {"quals": [], "gzips": [], "per_img": {}} for ci in range(len(configs))}
    for o in outcomes:
        if not o or "__error__" in o or "error" in o or o.get("metrics") is None:
            continue
        ci, name = o["tag"]
        m = o["metrics"]
        if m.get("quality") is None:
            continue
        o = {"ci": ci, "name": name, "quality": m["quality"], "gzip": m.get("gzip_bytes", 0)}
        a = agg[o["ci"]]
        a["quals"].append(o["quality"])
        a["gzips"].append(o["gzip"])
        a["per_img"][o["name"]] = o["quality"]

    rows = []
    for ci, (pid, params) in enumerate(configs):
        a = agg[ci]
        if not a["quals"]:
            continue
        rows.append({
            "pipeline": pid,
            "params": params,
            "mean": round(statistics.mean(a["quals"]), 4),
            "median": round(statistics.median(a["quals"]), 4),
            "min": round(min(a["quals"]), 4),
            "mean_gzip": int(statistics.mean(a["gzips"])) if a["gzips"] else 0,
            "n": len(a["quals"]),
            "per_image": {k: round(v, 4) for k, v in a["per_img"].items()},
        })

    rows.sort(key=lambda r: r["mean"], reverse=True)

    print("=== TOP CONFIGS (ranked by mean quality across all images) ===")
    print(f"{'#':>2}  {'mean':>6} {'median':>6} {'min':>6} {'gzip':>7}  pipeline  params")
    for i, r in enumerate(rows[:args.top], 1):
        print(f"{i:>2}  {r['mean']:>6.4f} {r['median']:>6.4f} {r['min']:>6.4f} {r['mean_gzip']//1:>6}B  "
              f"{r['pipeline']:<18} {r['params']}")

    # Efficiency view: best quality-per-byte (rewards compact SVGs).
    print("\n=== TOP CONFIGS BY EFFICIENCY (quality - 0.02*log10(gzip)) ===")
    import math
    eff = sorted(rows, key=lambda r: r["mean"] - 0.02 * math.log10(max(1, r["mean_gzip"])), reverse=True)
    for i, r in enumerate(eff[:5], 1):
        print(f"{i:>2}  q={r['mean']:.4f}  {r['mean_gzip']//1:>6}B  {r['pipeline']:<18} {r['params']}")

    print("\n=== BEST CONFIG PER PIPELINE ===")
    for pid in pipelines:
        best = max((r for r in rows if r["pipeline"] == pid), key=lambda r: r["mean"], default=None)
        if best:
            print(f"  {pid:<18} mean={best['mean']:.4f}  {best['params']}")

    print("\n=== PER-IMAGE WINNER (best config for each image) ===")
    for name in images:
        best = max(rows, key=lambda r: r["per_image"].get(name, -1))
        print(f"  {name[:42]:<44} q={best['per_image'].get(name):.4f}  {best['pipeline']} {best['params']}")

    report = OUTPUTS / "sweep_all.json"
    report.write_text(json.dumps(rows, indent=2))
    for proc_path, eval_path, _ in prep.values():
        for p in (proc_path, eval_path):
            try:
                Path(p).unlink()
            except OSError:
                pass
    print(f"\nfull report -> {report}")


if __name__ == "__main__":
    run()
