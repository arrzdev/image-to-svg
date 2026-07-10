# ideal-6 — ideal-5 + guarded shape-smoothing (clean polygon sides)

USER direction (2026-07-10): lines are filled polygons whose SIDES should be
clean (straight / smoothly divergent-convergent), not lumpy. ideal-6 adds a
guarded mask-smoothing pass over ideal-5's regions so shape sides come out
clean, while protecting thin dark outlines from being eroded. Fills-only, no
strokes. Knobs: smooth_passes, smooth_ksize (+ all ideal-5 knobs).
Repro: python run_model.py -m ideal-6 -i data/inputs/rabbit.jpg
