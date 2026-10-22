import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "eval"))
import metrics_vs_recraft as M

entry = M.load_entry("quant-12")
base = {"num_colors": 16, "merge_de": 12.0,
        "straight_eps": 0.8, "straight_min_len": 14}
CONFIGS = [
    ("a150", {"min_area": 150}),
    ("a120", {"min_area": 120}),
    ("a100", {"min_area": 100}),
    ("a80", {"min_area": 80}),
    ("a100/m10", {"min_area": 100, "merge_de": 10.0}),
    ("a120/mlen12", {"min_area": 120, "straight_min_len": 12}),
]
print(f"{'config':14s} {'ovr':>5s} {'P':>4s} {'C':>4s} {'L':>4s} "
      f"{'ss':>4s} {'gm':>4s} {'col':>4s}  P C L  minaxis")
best = (None, -1, None)
for name, extra in CONFIGS:
    params = {**base, **extra}
    r = M.score("quant-12", params=params, verbose=False, entry=entry)
    t = r["totals"]
    axes = {"P": r["paths"], "C": r["C"], "L": r["L"], "ss": r["ssim"],
            "gm": r["gmsd"], "col": r["colour"]}
    mn = min(axes.items(), key=lambda x: x[1])
    print(f"{name:14s} {r['overall']:.3f} {r['paths']:.2f} {r['C']:.2f} "
          f"{r['L']:.2f} {r['ssim']:.2f} {r['gmsd']:.2f} {r['colour']:.2f}  "
          f"{t['paths_o']} {t['C_o']} {t['L_o']}  {mn[0]}={mn[1]:.2f}")
    sys.stdout.flush()
    if mn[1] > best[1]:
        best = (name, mn[1], params)
print(f"\nBEST(min-axis): {best[0]} minaxis={best[1]:.3f} {best[2]}")
