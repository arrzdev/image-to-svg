import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "eval"))
import metrics_vs_recraft as M

entry = M.load_entry("quant-12")
CONFIGS = [
    ("cur k12/a300/1.0-14", {}),
    ("k16/a200/1.0-16", {"num_colors": 16, "min_area": 200,
                         "straight_eps": 1.0, "straight_min_len": 16}),
    ("k16/a150/0.8-20", {"num_colors": 16, "min_area": 150,
                         "straight_eps": 0.8, "straight_min_len": 20}),
    ("k14/a250/1.0-14", {"num_colors": 14, "min_area": 250,
                         "straight_eps": 1.0, "straight_min_len": 14}),
    ("k16/a300/0.9-18", {"num_colors": 16, "min_area": 300,
                         "straight_eps": 0.9, "straight_min_len": 18}),
    ("k16/a250/1.0-12", {"num_colors": 16, "min_area": 250,
                         "straight_eps": 1.0, "straight_min_len": 12}),
    ("k14/a200/0.9-16", {"num_colors": 14, "min_area": 200,
                         "straight_eps": 0.9, "straight_min_len": 16}),
]
print(f"{'config':22s} {'ovr':>5s} {'P':>4s} {'C':>4s} {'L':>4s} "
      f"{'ss':>4s} {'gm':>4s} {'col':>4s}  P_o C_o L_o")
best = (None, -1, None)
for name, params in CONFIGS:
    r = M.score("quant-12", params=params, verbose=False, entry=entry)
    t = r["totals"]
    print(f"{name:22s} {r['overall']:.3f} {r['paths']:.2f} {r['C']:.2f} "
          f"{r['L']:.2f} {r['ssim']:.2f} {r['gmsd']:.2f} {r['colour']:.2f}  "
          f"{t['paths_o']} {t['C_o']} {t['L_o']}")
    sys.stdout.flush()
    if r["overall"] > best[1]:
        best = (name, r["overall"], params)
print(f"\nBEST: {best[0]} overall={best[1]:.3f} {best[2]}")
