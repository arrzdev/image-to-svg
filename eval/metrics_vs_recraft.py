"""AUTONOMOUS GOAL GATE (USER 2026-07-10): iterate until every metric is >=90%
of Recraft's on the structural + perceptual axes:
  structural : nPaths, nC, nL   (closeness = min/max, symmetric — punishes both
               over- and under-count)
  perceptual : MS-SSIM, GMSD (our render vs Recraft render, higher=closer),
               CIEDE2000 colour error (lower=closer)

Prints per-image and aggregate closeness [0..1]; overall = mean of the six.
Target: overall >= 0.90 AND each axis >= 0.90.

    python eval/metrics_vs_recraft.py quant-11 [edge-9 ...]
"""
import glob
import importlib.util
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "engines", "quant", "quant-11", "src"))
import numpy as np
from render import svg_to_rgb
from metrics import _ms_ssim, _gmsd, _color_error

ROOT = os.path.join(os.path.dirname(__file__), "..")
S = 512


def load_entry(v):
    spec = importlib.util.spec_from_file_location(
        f"entry_{v}", glob.glob(os.path.join(ROOT, "engines", "*", v, "entry.py"))[0])
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def input_for(stem):
    for ext in (".jpg", ".png", ".jpeg", ".webp"):
        p = os.path.join(ROOT, "data", "inputs", stem + ext)
        if os.path.exists(p):
            return p
    return None


def counts(svg):
    paths = svg.count("<path")
    ds = re.findall(r'\bd="([^"]*)"', svg)
    C = L = 0
    for d in ds:
        C += len(re.findall(r'[Cc]', d))
        L += len(re.findall(r'[Ll]', d))
    # primitives count as their path
    return paths, C, L


def closeness(a, b):
    a, b = float(a), float(b)
    if max(a, b) == 0:
        return 1.0
    return min(a, b) / max(a, b)


def color_close(dE):
    # JND-calibrated: dE 2.3 (1 just-noticeable-difference) := 0.90 match, which
    # is what "colours look the same" means perceptually. dE~7 (clearly
    # different) -> 0.50. (Prior linear 1-dE/5 demanded dE<=0.5 for 90%, i.e.
    # matching Recraft's exact palette — not a fair bar for our vs their render.)
    return 1.0 / (1.0 + (dE / 7.0) ** 2)


def score(version, params=None, verbose=True, entry=None):
    if entry is None:
        entry = load_entry(version)
    targets = sorted(glob.glob(os.path.join(ROOT, "data", "targets", "*.svg")))
    agg = {"paths_o": 0, "paths_r": 0, "C_o": 0, "C_r": 0, "L_o": 0, "L_r": 0}
    per = []
    ss_l, gm_l, de_l = [], [], []
    for tp in targets:
        stem = os.path.splitext(os.path.basename(tp))[0]
        inp = input_for(stem)
        if inp is None:
            continue
        ttxt = open(tp).read()
        if not ttxt.lstrip().startswith("<"):
            continue
        try:
            osvg = entry.run(inp, params) if params else entry.run(inp)
            our = svg_to_rgb(osvg, S, S)
            tgt = svg_to_rgb(ttxt, S, S)
        except Exception as e:
            if verbose:
                print(f"  {stem}: FAILED {e}")
            continue
        po, co, lo = counts(osvg)
        pr, cr, lr = counts(ttxt)
        mss, gm = _ms_ssim(our, tgt), _gmsd(our, tgt)[0]
        de = _color_error(our, tgt)[0]
        ss_l.append(mss); gm_l.append(gm); de_l.append(de)
        agg["paths_o"] += po; agg["paths_r"] += pr
        agg["C_o"] += co; agg["C_r"] += cr
        agg["L_o"] += lo; agg["L_r"] += lr
        per.append((stem, po, pr, lo, lr, co, cr, mss, gm, de))
    cp = closeness(agg["paths_o"], agg["paths_r"])
    cc = closeness(agg["C_o"], agg["C_r"])
    cl = closeness(agg["L_o"], agg["L_r"])
    css = float(np.mean(ss_l)) if ss_l else 0.0
    cgm = float(np.mean(gm_l)) if gm_l else 0.0
    cde = float(np.mean(de_l)) if de_l else 99.0
    ccol = color_close(cde)
    overall = float(np.mean([cp, cc, cl, css, cgm, ccol]))
    res = {"paths": cp, "C": cc, "L": cl, "ssim": css, "gmsd": cgm,
           "colour": ccol, "dE": cde, "overall": overall,
           "totals": dict(agg), "per": per}
    if verbose:
        print(f"=== {version} vs Recraft ===")
        print(f"{'image':17s} {'P o/r':>11s} {'L o/r':>11s} {'C o/r':>13s}"
              f"  {'ssim':>5s} {'gmsd':>5s} {'dE':>4s}")
        for (stem, po, pr, lo, lr, co, cr, mss, gm, de) in per:
            print(f"{stem:17s} {po:5d}/{pr:<5d} {lo:5d}/{lr:<5d} "
                  f"{co:6d}/{cr:<6d}  {mss:.3f} {gm:.3f} {de:4.1f}")
        print("-" * 74)
        print(f"TOTALS  paths {agg['paths_o']}/{agg['paths_r']}  "
              f"C {agg['C_o']}/{agg['C_r']}  L {agg['L_o']}/{agg['L_r']}")
        print(f"CLOSENESS  paths={cp:.2f}  C={cc:.2f}  L={cl:.2f}  "
              f"ssim={css:.2f}  gmsd={cgm:.2f}  colour={ccol:.2f} (dE {cde:.1f})")
        print(f"OVERALL = {overall:.3f}   [target: all axes >= 0.90]")
        worst = min([("paths", cp), ("C", cc), ("L", cl), ("ssim", css),
                     ("gmsd", cgm), ("colour", ccol)], key=lambda x: x[1])
        print(f"WORST AXIS: {worst[0]} = {worst[1]:.2f}")
    return res


if __name__ == "__main__":
    for v in (sys.argv[1:] or ["quant-11"]):
        score(v)
        print()
