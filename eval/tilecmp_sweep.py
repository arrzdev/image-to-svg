"""Run tilecmp across the whole target corpus: for each Recraft target, generate
our engine's output, compare tile-by-tile, and print per-image + aggregate
labelled distances and the corpus-wide failure-mode fingerprint.

    python eval/tilecmp_sweep.py [engine] [--tiles 48]

engine defaults to quant-12. Writes heatmaps per image under
eval/tilecmp_out/<stem>/.
"""
import glob
import importlib.util as u
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import tilecmp  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(os.path.dirname(__file__), "tilecmp_out")


def load_engine(name):
    spec = u.spec_from_file_location(
        "eng", glob.glob(os.path.join(ROOT, "engines", "*", name, "entry.py"))[0])
    m = u.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def input_for(stem):
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = os.path.join(ROOT, "data", "inputs", stem + ext)
        if os.path.exists(p):
            return p
    return None


def main():
    engine = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") \
        else "quant-12"
    tiles = 48
    if "--tiles" in sys.argv:
        tiles = int(sys.argv[sys.argv.index("--tiles") + 1])
    eng = load_engine(engine)
    targets = sorted(glob.glob(os.path.join(ROOT, "data", "targets", "*.svg")))

    print(f"=== tilecmp sweep: {engine} vs Recraft  ({tiles}x{tiles}) ===")
    print(f"{'image':18s} {'census':>7s} {'flow':>6s} {'color':>6s} "
          f"{'overall':>7s}   dominant failure")
    rows = []
    corpus_mix = {}
    for tp in targets:
        stem = os.path.splitext(os.path.basename(tp))[0]
        inp = input_for(stem)
        if inp is None:
            continue
        theirs = open(tp).read()
        if not theirs.lstrip().startswith("<"):
            continue
        try:
            ours = eng.run(inp)
        except Exception as e:
            print(f"{stem:18s}  ENGINE FAILED: {e}")
            continue
        res = tilecmp.compare(ours, theirs, n=tiles, native=2048, input_img=inp)
        ag = res["agg"]
        # per-image failure mix (ink-weighted)
        w = res["weight"]
        mix = {}
        for i in range(tiles):
            for j in range(tiles):
                if w[i, j] > 0:
                    lab = res["labels"][i, j]
                    mix[lab] = mix.get(lab, 0.0) + w[i, j]
                    corpus_mix[lab] = corpus_mix.get(lab, 0.0) + w[i, j]
        dom = max(mix, key=mix.get) if mix else "-"
        rows.append((stem, ag, dom))
        print(f"{stem:18s} {ag['census']:7.3f} {ag['flow']:6.3f} "
              f"{ag['color']:6.3f} {ag['overall']:7.3f}   {dom}")
        d = os.path.join(OUT, stem)
        os.makedirs(d, exist_ok=True)
        tilecmp._heatmaps(res, os.path.join(d, "heatmaps.png"))

    if rows:
        print("-" * 62)
        mc = np.mean([r[1]["census"] for r in rows])
        mf = np.mean([r[1]["flow"] for r in rows])
        mk = np.mean([r[1]["color"] for r in rows])
        mo = np.mean([r[1]["overall"] for r in rows])
        print(f"{'CORPUS MEAN':18s} {mc:7.3f} {mf:6.3f} {mk:6.3f} {mo:7.3f}")
        tot = sum(corpus_mix.values()) + 1e-9
        print("corpus failure-mode fingerprint (ink-weighted):")
        for lab, v in sorted(corpus_mix.items(), key=lambda x: -x[1]):
            print(f"    {lab:14s} {100 * v / tot:5.1f}%")


if __name__ == "__main__":
    main()
