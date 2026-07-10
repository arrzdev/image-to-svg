"""Autonomous param sweep toward the Recraft goal. Prints composite closeness
per config so the loop can pick the best. Usage: python sweep_goal.py <version>"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import metrics_vs_recraft as M

version = sys.argv[1] if len(sys.argv) > 1 else "quant-11"
entry = M.load_entry(version)

CONFIGS = [
    ("baseline", {}),
    ("min_area300", {"min_area": 300}),
    ("min_area600", {"min_area": 600}),
    ("merge18", {"merge_de": 18.0}),
    ("merge24", {"merge_de": 24.0}),
    ("k12", {"num_colors": 12}),
    ("k12_m18_a300", {"num_colors": 12, "merge_de": 18.0, "min_area": 300}),
    ("k10_m20_a500", {"num_colors": 10, "merge_de": 20.0, "min_area": 500}),
    ("k12_m16_a250", {"num_colors": 12, "merge_de": 16.0, "min_area": 250}),
]

print(f"{'config':16s} {'overall':>7s} {'paths':>6s} {'C':>5s} {'L':>5s} "
      f"{'ssim':>5s} {'gmsd':>5s} {'col':>5s}  P_o/r  C_o/r")
best = (None, -1)
for name, params in CONFIGS:
    r = M.score(version, params=params, verbose=False, entry=entry)
    t = r["totals"]
    print(f"{name:16s} {r['overall']:.3f}   {r['paths']:.2f}  {r['C']:.2f}  "
          f"{r['L']:.2f}  {r['ssim']:.2f}  {r['gmsd']:.2f}  {r['colour']:.2f}  "
          f"{t['paths_o']}/{t['paths_r']}  {t['C_o']}/{t['C_r']}")
    sys.stdout.flush()
    if r["overall"] > best[1]:
        best = (name, r["overall"], params)
print(f"\nBEST: {best[0]} overall={best[1]:.3f} params={best[2]}")
