# edge-1 — boundary-first vectorizer

USER idea (2026-07-10): the drawing IS its color boundaries. Detect boundaries
(LAB gradient > threshold) → thin line network; the cells they enclose are the
bucket-fills; the boundary lines are strokes colored by the DARKER side (ink
stays black). First SVG of the "edge" lineage. Knobs: threshold, close,
k_colors. Repro: python run_model.py -m edge-1 -i data/inputs/rabbit.jpg
