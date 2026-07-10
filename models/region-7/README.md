# ideal-7 — ideal-6 + smoother high-DPI boundaries (contour smoothing bumped)

USER: borders still too pixelated, want smooth high-DPI boundaries. Bumps
CONTOUR smoothing (smooth_win 11→21, fit_tol 2→4) while keeping MASK smoothing
moderate (p2/k5) — mask smoothing distorts structure (see ideal-6 note), contour
smoothing only smooths the fitted boundary. Chosen by score: boundary jaggedness
0.131→0.119 (toward Recraft 0.060) at ~1% MS-SSIM cost (boundary drift, not
distortion). Verify with research/design/score_vs_recraft.py.
Repro: python run_model.py -m ideal-7 -i data/inputs/rabbit.jpg
