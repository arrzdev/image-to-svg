"""Benchmark edge-11 (synthesized strokes over buckets) vs the quant-13 gate
baseline on the tilecmp corpus — the never-run lineage comparison.

Mirrors tilecmp_loop.sweep() semantics exactly (n=40 tiles, native=2048,
color anchored to source) but isolates per-stem crashes: edge-11 has only
ever run on elephant/chopchop; 9 stems are first-contact.

Outputs: research/experiments/edge11-bench/<stem>.svg + report.json + stdout table.
Run: .venv/bin/python research/experiments/edge11-bench/bench_edge11.py
"""
import glob
import json
import os
import pickle
import sys
import time
import traceback

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EVAL = os.path.join(ROOT, "eval")
OUT = HERE
sys.path.insert(0, EVAL)
import tilecmp                              # noqa: E402
from tilecmp_loop import load_engine, input_for  # noqa: E402

TILES = 40
BASE = pickle.load(open(os.path.join(EVAL, ".tilecmp_cache", "gate_base.pkl"),
                        "rb"))


def main():
    os.makedirs(OUT, exist_ok=True)
    eng = load_engine("edge-11")
    targets = sorted(glob.glob(os.path.join(ROOT, "data", "targets", "*.svg")))
    per = {}
    ch = {"census": [], "flow": [], "color": [], "overall": []}
    for tp in targets:
        stem = os.path.splitext(os.path.basename(tp))[0]
        inp = input_for(stem)
        if inp is None:
            continue
        theirs = open(tp).read()
        if not theirs.lstrip().startswith("<"):
            continue
        t0 = time.time()
        try:
            ours = eng.run(inp)
            open(os.path.join(OUT, stem + ".svg"), "w").write(ours)
            res = tilecmp.compare(ours, theirs, n=TILES, native=2048,
                                  input_img=inp)
            per[stem] = {"agg": res["agg"], "seconds": round(time.time() - t0, 1),
                         "kb": round(len(ours) / 1024, 1),
                         "paths": ours.count("<path")}
            for k in ch:
                ch[k].append(res["agg"][k])
            q = BASE["per"][stem]["agg"]
            print(f"{stem:18s} edge-11 {res['agg']['overall']:.4f}  "
                  f"quant-13 {q['overall']:.4f}  "
                  f"delta {res['agg']['overall'] - q['overall']:+.4f}  "
                  f"({per[stem]['seconds']}s, {per[stem]['paths']} paths, "
                  f"{per[stem]['kb']}KB)", flush=True)
        except Exception:
            per[stem] = {"error": traceback.format_exc(limit=3)}
            print(f"{stem:18s} CRASH:\n{per[stem]['error']}", flush=True)

    ok = [s for s in per if "agg" in per[s]]
    corpus = {k: float(np.mean(v)) for k, v in ch.items()} if ok else {}
    print("\n== corpus (edge-11 vs quant-13 baseline) ==")
    for k in ("census", "flow", "color", "overall"):
        b = BASE["corpus"][k]
        e = corpus.get(k, float("nan"))
        print(f"  {k:8s} edge-11 {e:.4f}   quant-13 {b:.4f}   "
              f"delta {e - b:+.4f}")
    print(f"  ({len(ok)}/{len(per)} stems ran; crashes: "
          f"{[s for s in per if 'error' in per[s]] or 'none'})")

    # per-channel win/loss table vs baseline
    wins = {k: [] for k in ("census", "flow", "color", "overall")}
    for s in ok:
        for k in wins:
            d = per[s]["agg"][k] - BASE["per"][s]["agg"][k]
            if d < -1e-6:
                wins[k].append((s, d))
    print("\nper-stem WINS for edge-11 (delta < 0):")
    for k, v in wins.items():
        v.sort(key=lambda x: x[1])
        print(f"  {k:8s}: " + (", ".join(f"{s} {d:+.3f}" for s, d in v)
                               if v else "none"))

    json.dump({"per": {s: {k2: v2 for k2, v2 in d.items()}
                       for s, d in per.items()},
               "corpus": corpus, "tiles": TILES},
              open(os.path.join(OUT, "report.json"), "w"), indent=2,
              default=float)
    print(f"\nwrote {os.path.join(OUT, 'report.json')}")


if __name__ == "__main__":
    main()
