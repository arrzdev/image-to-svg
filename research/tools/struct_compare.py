"""Structural comparison: OURS vs Recraft, by the numbers (NO visual judgment).

USER mandate 2026-07-13: verification is by METRICS, not by eye. This tool
reports the objective structural gap for a stem:
  * path count
  * cubic (C) / line (L) command counts + arc-length fractions
  * LONG-straight-line count (>=100/200/300 px) — the "curly vs clean" signal:
    Recraft draws a straight edge as ONE long L; fragmentation breaks it into
    short pieces, so a low long-L count vs Recraft = our straight edges are
    fragmented/wiggly even when the aggregate L-fraction matches.
  * tilecmp agg + per-tile mode shares (census/flow/color, FITTER/OVER-FRAGMENT/…)

Usage:
  .venv/bin/python research/tools/struct_compare.py <stem> [--engine quant-19] [--svg path]
  .venv/bin/python research/tools/struct_compare.py --all [--engine quant-19]
"""
import argparse
import os
import re
import sys

import numpy as np
from svgpathtools import parse_path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "research", "design"))
sys.path.insert(0, os.path.join(ROOT, "models", "quant-11", "src"))
import tilecmp  # noqa: E402


def _input_for(stem):
    for e in (".png", ".jpg", ".jpeg", ".webp"):
        p = os.path.join(ROOT, "data", "inputs", stem + e)
        if os.path.exists(p):
            return p


def _run_engine(engine, stem):
    import importlib.util as u
    spec = u.spec_from_file_location("eng", os.path.join(ROOT, "models", engine, "entry.py"))
    m = u.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.run(_input_for(stem))


def structural(svg):
    ds = re.findall(r'\bd="([^"]*)"', svg)
    nC = sum(len(re.findall(r"[Cc]", d)) for d in ds)
    nL = sum(len(re.findall(r"[Ll]", d)) for d in ds)
    Llen = Clen = 0.0
    Lsegs = []
    for d in ds:
        try:
            p = parse_path(d)
        except Exception:
            continue
        for seg in p:
            cn = seg.__class__.__name__
            if cn == "Line":
                L = seg.length()
                Llen += L
                Lsegs.append(L)
            elif cn == "CubicBezier":
                Clen += seg.length(error=1e-3)
    Lsegs = np.asarray(Lsegs)
    tot = Llen + Clen + 1e-9
    return {
        "paths": svg.count("<path"),
        "C": nC, "L": nL,
        "L_cmd_frac": nL / max(1, nC + nL),
        "L_len_frac": Llen / tot,
        "avg_path_len": tot / max(1, svg.count("<path")),
        "long_L_100": int((Lsegs > 100).sum()),
        "long_L_200": int((Lsegs > 200).sum()),
        "long_L_300": int((Lsegs > 300).sum()),
    }


def compare(stem, ours_svg):
    theirs = open(os.path.join(ROOT, "data", "targets", stem + ".svg")).read()
    so, st = structural(ours_svg), structural(theirs)
    inp = _input_for(stem)
    res = tilecmp.compare(ours_svg, theirs, n=20, native=2048, input_img=inp)
    from collections import Counter
    w, lab = res["weight"], res["labels"]
    modes = Counter()
    for i in range(20):
        for j in range(20):
            if w[i, j] > 0:
                modes[lab[i, j]] += w[i, j]
    tw = sum(modes.values()) + 1e-9
    return so, st, res["agg"], {k: v / tw for k, v in modes.most_common()}


def _fmt(stem, so, st, agg, modes):
    print(f"\n===== {stem} =====")
    print(f"{'metric':16s} {'OURS':>10s} {'RECRAFT':>10s} {'ratio/gap':>12s}")
    rows = [
        ("paths", so["paths"], st["paths"]),
        ("cubics (C)", so["C"], st["C"]),
        ("lines (L)", so["L"], st["L"]),
        ("long-L >100px", so["long_L_100"], st["long_L_100"]),
        ("long-L >200px", so["long_L_200"], st["long_L_200"]),
        ("long-L >300px", so["long_L_300"], st["long_L_300"]),
    ]
    for nm, o, t in rows:
        print(f"{nm:16s} {o:>10d} {t:>10d} {o/max(1,t):>11.2f}x")
    print(f"{'L-len frac':16s} {so['L_len_frac']*100:>9.1f}% {st['L_len_frac']*100:>9.1f}%")
    print(f"{'avg path len':16s} {so['avg_path_len']:>10.0f} {st['avg_path_len']:>10.0f}")
    print(f"tilecmp: overall={agg['overall']:.3f} census={agg['census']:.3f} "
          f"flow={agg['flow']:.3f} color={agg['color']:.3f}")
    print("modes: " + "  ".join(f"{k} {v*100:.0f}%" for k, v in modes.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stem", nargs="?")
    ap.add_argument("--engine", default="quant-19")
    ap.add_argument("--svg", default=None)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    if a.all:
        import glob
        stems = sorted(os.path.splitext(os.path.basename(t))[0]
                       for t in glob.glob(os.path.join(ROOT, "data", "targets", "*.svg")))
        for stem in stems:
            if _input_for(stem):
                _fmt(stem, *compare(stem, _run_engine(a.engine, stem)))
    else:
        ours = open(a.svg).read() if a.svg else _run_engine(a.engine, a.stem)
        _fmt(a.stem, *compare(a.stem, ours))


if __name__ == "__main__":
    main()
