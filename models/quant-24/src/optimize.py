"""Per-image auto-optimizer: parallel coordinate ascent over the FULL knob
space — tracer params + processing resolution + post-simplify strength.

Why not the grid? The interesting space (5+ dims incl. process_dim and
simplify_eps) is thousands of grid cells; coordinate ascent converges in a few
dozen evaluations. Each coordinate is line-searched in PARALLEL (all candidate
values at once on the process pool), so a full pass costs only a few
wall-clock steps.

Usage:
    python backend/optimize.py <image-or-sample> [options]

Options:
    --pipeline vtracer      pipeline to tune (default vtracer)
    --lambda L              objective = quality - L*log10(points); 0 = pure
                            fidelity. Use ~0.02 to favor editable/compact SVGs.
    --budget N              max evaluations (default 80)
    --workers N             pool size (default cores-2)

Prints the ascent trajectory and best config; writes outputs/optimize_<img>.json.
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from app import _prepare, SAMPLES                  # noqa: E402
from parallel import process_map, default_workers, limit_native_threads  # noqa: E402
import sweep_worker                                 # noqa: E402

OUTPUTS = HERE.parent / "outputs"

# Ordered candidate lists per coordinate. `process_dim` and `simplify_eps` are
# pseudo-params handled by the harness; the rest go to the pipeline.
SPACES = {
    "vtracer": {
        "process_dim": [1024, 1536, 2048, 3072],
        "simplify_eps": [0.0, 0.5, 1.0, 2.0, 3.0],
        "posterize": [0, 12, 16, 24],
        "color_precision": [7, 8],
        "filter_speckle": [1, 2, 4, 8],
        "corner_threshold": [15, 30, 45, 60, 90],
        "layer_difference": [4, 8, 12, 16, 24],
    },
    "quantize_contours": {
        "process_dim": [768, 1024, 1536],
        "simplify_eps": [0.0, 1.0, 2.0],
        "num_colors": [8, 12, 16, 24],
        "simplify": [0.5, 1.0, 2.0, 3.0],
        "corner_deg": [20, 30, 40, 55],
        "blur": [0, 1, 2],
    },
    "potrace_layers": {
        "process_dim": [768, 1024, 1536, 2048],
        "simplify_eps": [0.0, 1.0, 2.0],
        "num_colors": [8, 12, 16, 24],
        "gap_fill": [0, 1, 2],
        "alphamax": [0.8, 1.0, 1.2],
        "opttolerance": [0.2, 0.35, 0.5],
    },
}

START = {
    "vtracer": {"process_dim": 2048, "simplify_eps": 1.0, "posterize": 0, "color_precision": 8,
                "filter_speckle": 2, "corner_threshold": 60, "layer_difference": 8},
    "quantize_contours": {"process_dim": 1024, "simplify_eps": 0.0, "num_colors": 12,
                          "simplify": 1.0, "corner_deg": 30, "blur": 1},
    "potrace_layers": {"process_dim": 1024, "simplify_eps": 0.0, "num_colors": 12,
                       "gap_fill": 1, "alphamax": 1.0, "opttolerance": 0.2},
}


def _load_bytes(arg: str) -> bytes:
    p = Path(arg)
    if p.exists():
        return p.read_bytes()
    sp = SAMPLES / arg
    if sp.exists():
        return sp.read_bytes()
    sys.exit(f"image not found: {arg}")


class Evaluator:
    """Evaluates configs on the process pool with memoization + prep caching."""

    def __init__(self, raw: bytes, pipeline: str, lam: float, workers: int):
        self.raw = raw
        self.pipeline = pipeline
        self.lam = lam
        self.workers = workers
        self.prep_cache = {}
        self.memo = {}
        self.evals = 0
        self.files = []
        self.uid = uuid.uuid4().hex[:8]  # unique prefix: concurrent runs can't collide

    def _prep(self, dim: int):
        if dim not in self.prep_cache:
            proc, ev, wh = _prepare(self.raw, dim)
            pp = OUTPUTS / f"_opt_{self.uid}_{dim}_proc.png"
            ep = OUTPUTS / f"_opt_{self.uid}_{dim}_eval.png"
            proc.save(pp)
            ev.save(ep)
            self.prep_cache[dim] = (str(pp), str(ep), wh)
            self.files += [pp, ep]
        return self.prep_cache[dim]

    def _key(self, cfg: dict):
        return tuple(sorted(cfg.items()))

    def score_many(self, cfgs: list) -> list:
        """Evaluate configs in parallel; returns objective scores (or -1)."""
        todo = [c for c in cfgs if self._key(c) not in self.memo]
        jobs = []
        for i, cfg in enumerate(todo):
            pp, ep, (ow, oh) = self._prep(cfg["process_dim"])
            params = {k: v for k, v in cfg.items() if k not in ("process_dim", "simplify_eps")}
            jobs.append((i, self.pipeline, params, pp, ep, ow, oh, cfg["simplify_eps"]))
        if jobs:
            outcomes = process_map(sweep_worker.run_job, jobs, workers=self.workers,
                                   initializer=sweep_worker.init_worker)
            self.evals += len(jobs)
            for o in outcomes:
                if not o or "__error__" in o or "error" in o:
                    continue
                i = o["tag"]
                m = o["metrics"]
                q = m.get("quality")
                if q is None:
                    continue
                obj = q - self.lam * math.log10(max(1, m.get("num_points", 1)))
                self.memo[self._key(todo[i])] = (obj, m)
        return [self.memo.get(self._key(c), (-1.0, None)) for c in cfgs]

    def cleanup(self):
        for f in self.files:
            try:
                Path(f).unlink()
            except OSError:
                pass


def coordinate_ascent(ev: Evaluator, space: dict, start: dict, budget: int):
    cur = dict(start)
    (cur_obj, cur_m), = ev.score_many([cur])
    print(f"start: obj={cur_obj:.4f}  {cur}")
    trajectory = [{"config": dict(cur), "objective": cur_obj}]

    improved = True
    while improved and ev.evals < budget:
        improved = False
        for param, cands in space.items():
            if ev.evals >= budget:
                break
            trials = [dict(cur, **{param: v}) for v in cands if v != cur[param]]
            if not trials:
                continue
            results = ev.score_many(trials)
            best_i = max(range(len(trials)), key=lambda i: results[i][0])
            if results[best_i][0] > cur_obj + 1e-5:
                cur = trials[best_i]
                cur_obj, cur_m = results[best_i]
                improved = True
                print(f"  {param} -> {cur[param]}   obj={cur_obj:.4f} "
                      f"(q={cur_m['quality']}, pts={cur_m['num_points']}, "
                      f"gz={cur_m['gzip_bytes']//1024}KB)")
                trajectory.append({"config": dict(cur), "objective": cur_obj})
    return cur, cur_obj, cur_m, trajectory


def optimize_bytes(raw: bytes, pipeline: str = "vtracer", lam: float = 0.0,
                   budget: int = 48, workers: int = None) -> dict:
    """Programmatic entry point (used by the web UI's Auto-optimize).

    Runs coordinate ascent and returns {best, objective, metrics, evals,
    seconds, svg} where svg is the final SVG produced by the winning config.
    """
    from pipelines import get_pipeline
    from svgutil import fit_svg_size
    from postprocess import simplify_svg

    limit_native_threads()
    ev = Evaluator(raw, pipeline, lam, workers or default_workers())
    t0 = time.time()
    try:
        best, obj, m, traj = coordinate_ascent(ev, SPACES[pipeline], START[pipeline], budget)
        # Regenerate the winning SVG once, in-process.
        pp, _, (ow, oh) = ev._prep(best["process_dim"])
        params = {k: v for k, v in best.items() if k not in ("process_dim", "simplify_eps")}
        svg = get_pipeline(pipeline).run(pp, params)
        if best["simplify_eps"] > 0:
            svg = simplify_svg(svg, best["simplify_eps"])
        svg = fit_svg_size(svg, ow, oh)
    finally:
        ev.cleanup()
    return {"best": best, "objective": obj, "metrics": m, "evals": ev.evals,
            "seconds": round(time.time() - t0, 1), "trajectory": traj, "svg": svg}


def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--pipeline", default="vtracer", choices=list(SPACES.keys()))
    ap.add_argument("--lambda", dest="lam", type=float, default=0.0)
    ap.add_argument("--budget", type=int, default=80)
    ap.add_argument("--workers", type=int, default=default_workers())
    args = ap.parse_args()

    limit_native_threads()
    raw = _load_bytes(args.image)
    ev = Evaluator(raw, args.pipeline, args.lam, args.workers)
    t0 = time.time()
    best, obj, m, traj = coordinate_ascent(ev, SPACES[args.pipeline], START[args.pipeline], args.budget)
    dt = time.time() - t0

    grid_size = math.prod(len(v) for v in SPACES[args.pipeline].values())
    print(f"\nconverged in {ev.evals} evals ({dt:.1f}s) — grid would be {grid_size} cells")
    print(f"best: obj={obj:.4f} quality={m['quality']} local={m['local_score']} "
          f"pts={m['num_points']} gzip={m['gzip_bytes']//1024}KB")
    print(f"config: {best}")

    out = OUTPUTS / f"optimize_{Path(args.image).stem}.json"
    out.write_text(json.dumps({"best": best, "objective": obj, "metrics": m,
                               "evals": ev.evals, "seconds": round(dt, 1),
                               "trajectory": traj}, indent=2))
    ev.cleanup()
    print(f"report -> {out}")


if __name__ == "__main__":
    run()
