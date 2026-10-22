import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "eval"))
import metrics_vs_recraft as M

entry = M.load_entry("quant-12")
base = {"num_colors": 16, "min_area": 150, "merge_de": 12.0}
CONFIGS = [
    ("ft2.5/0.8-20", {"fill_tol": 2.5, "straight_eps": 0.8, "straight_min_len": 20}),
    ("ft1.5/0.8-20", {"fill_tol": 1.5, "straight_eps": 0.8, "straight_min_len": 20}),
    ("ft1.5/1.0-14", {"fill_tol": 1.5, "straight_eps": 1.0, "straight_min_len": 14}),
    ("ft2.0/0.9-16", {"fill_tol": 2.0, "straight_eps": 0.9, "straight_min_len": 16}),
    ("ft1.2/0.9-16", {"fill_tol": 1.2, "straight_eps": 0.9, "straight_min_len": 16}),
    ("ft1.5/0.9-14", {"fill_tol": 1.5, "straight_eps": 0.9, "straight_min_len": 14}),
    ("ft1.8/1.0-12", {"fill_tol": 1.8, "straight_eps": 1.0, "straight_min_len": 12}),
]
print(f"{'config':16s} {'ovr':>5s} {'P':>4s} {'C':>4s} {'L':>4s} "
      f"{'ss':>4s} {'gm':>4s} {'col':>4s}  P C L")
best = (None, -1, None)
for name, extra in CONFIGS:
    params = {**base, **extra}
    r = M.score("quant-12", params=params, verbose=False, entry=entry)
    t = r["totals"]
    print(f"{name:16s} {r['overall']:.3f} {r['paths']:.2f} {r['C']:.2f} "
          f"{r['L']:.2f} {r['ssim']:.2f} {r['gmsd']:.2f} {r['colour']:.2f}  "
          f"{t['paths_o']} {t['C_o']} {t['L_o']}")
    sys.stdout.flush()
    if r["overall"] > best[1]:
        best = (name, r["overall"], params)
print(f"\nBEST: {best[0]} overall={best[1]:.3f} {best[2]}")
