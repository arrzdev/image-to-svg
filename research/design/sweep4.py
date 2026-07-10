import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import metrics_vs_recraft as M

entry = M.load_entry("quant-12")
base = {"num_colors": 16, "min_area": 150, "merge_de": 12.0}
# straighten fine sweep: (eps, min_len) — lower min_len converts short straights
STR = [(0.8, 20), (0.8, 14), (0.8, 10), (0.9, 12), (0.9, 10),
       (1.0, 12), (1.0, 9), (0.85, 11), (0.7, 10)]
print(f"{'eps/mlen':10s} {'ovr':>5s} {'P':>4s} {'C':>4s} {'L':>4s} "
      f"{'ss':>4s} {'gm':>4s} {'col':>4s}  P C L  minaxis")
best = (None, -1, None)
for eps, mlen in STR:
    params = {**base, "straight_eps": eps, "straight_min_len": mlen}
    r = M.score("quant-12", params=params, verbose=False, entry=entry)
    t = r["totals"]
    axes = {"P": r["paths"], "C": r["C"], "L": r["L"], "ss": r["ssim"],
            "gm": r["gmsd"], "col": r["colour"]}
    mn = min(axes.items(), key=lambda x: x[1])
    print(f"{eps}/{mlen:<6d} {r['overall']:.3f} {r['paths']:.2f} {r['C']:.2f} "
          f"{r['L']:.2f} {r['ssim']:.2f} {r['gmsd']:.2f} {r['colour']:.2f}  "
          f"{t['paths_o']} {t['C_o']} {t['L_o']}  {mn[0]}={mn[1]:.2f}")
    sys.stdout.flush()
    # rank by the MIN axis (goal = all axes >= 0.90), tiebreak overall
    key = (round(mn[1], 3), r["overall"])
    if key > (round(best[1][0], 3) if best[1] != -1 else -1,
              best[1][1] if best[1] != -1 else -1):
        best = (f"{eps}/{mlen}", (mn[1], r["overall"]), params)
print(f"\nBEST(min-axis): {best[0]} minaxis={best[1][0]:.3f} "
      f"overall={best[1][1]:.3f} {best[2]}")
