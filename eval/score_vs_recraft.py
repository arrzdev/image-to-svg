"""Algorithmic improvement gate: score a version's output against the Recraft
targets (USER 2026-07-10 — orchestrator visual judgment proved unreliable;
use an algorithm to decide whether we IMPROVED, visuals only for exploration).

Renders our output and the Recraft target for every image that has a target,
and scores similarity-to-Recraft: MS-SSIM (structure, higher=better), GMSD
(edges, higher=better), CIEDE2000 mean colour error (lower=better).

    python eval/score_vs_recraft.py ideal-6 [ideal-5 ...]
"""
import glob
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "engines", "quant", "quant-11", "src"))
import numpy as np
from render import svg_to_rgb
from metrics import _ms_ssim, _gmsd, _color_error

ROOT = os.path.join(os.path.dirname(__file__), "..")
S = 512


def load_entry(version):
    spec = importlib.util.spec_from_file_location(
        f"entry_{version}", glob.glob(os.path.join(ROOT, "engines", "*", version, "entry.py"))[0])
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def input_for(stem):
    for ext in (".jpg", ".png", ".jpeg", ".webp"):
        p = os.path.join(ROOT, "data", "inputs", stem + ext)
        if os.path.exists(p):
            return p
    return None


def score(version):
    entry = load_entry(version)
    targets = sorted(glob.glob(os.path.join(ROOT, "data", "targets", "*.svg")))
    rows = []
    for tp in targets:
        stem = os.path.splitext(os.path.basename(tp))[0]
        inp = input_for(stem)
        if inp is None:
            continue
        ttxt = open(tp).read()
        if not ttxt.lstrip().startswith("<"):
            continue
        try:
            our = svg_to_rgb(entry.run(inp), S, S)
            tgt = svg_to_rgb(ttxt, S, S)
        except Exception as e:
            print(f"  {stem}: FAILED {e}")
            continue
        mss = _ms_ssim(our, tgt)
        gms = _gmsd(our, tgt)[0]
        ce = _color_error(our, tgt)[0]
        rows.append((stem, mss, gms, ce))
    return rows


if __name__ == "__main__":
    versions = sys.argv[1:] or ["ideal-6"]
    for v in versions:
        rows = score(v)
        print(f"\n=== {v} vs Recraft ===")
        print(f"{'image':16s} {'MS-SSIM↑':>9s} {'GMSD↑':>7s} {'dE↓':>6s}")
        for stem, mss, gms, ce in rows:
            print(f"{stem:16s} {mss:9.3f} {gms:7.3f} {ce:6.1f}")
        if rows:
            a = np.array([[r[1], r[2], r[3]] for r in rows])
            print(f"{'MEAN':16s} {a[:,0].mean():9.3f} {a[:,1].mean():7.3f} "
                  f"{a[:,2].mean():6.1f}   (n={len(rows)})")
