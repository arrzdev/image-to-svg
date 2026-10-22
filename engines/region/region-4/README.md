# ideal-4 — SIMPLE debug baseline (no optimizations)

USER (2026-07-10): strip color-merging + size/path "optimizations" so defects
are traceable to one stage. Phase 2 (smooth edges, average colors, optimize
paths) comes AFTER the representation itself is right.

Pipeline, nothing else: resize → idealize (mean-shift) → Felzenszwalb regions
(no merge) → color-last from original interior → fills (quant-11 backend) →
ink = ALL original-dark pixels as ONE black filled layer on top (near-faithful
contours). Deliberately omits: merge_similar, speckle/elongation filtering,
heavy approxPolyDP, stroke floor.

~1900 paths — expected; not a defect to fix yet. Use it to find WHAT is wrong
in the representation, discuss causes, test fixes one at a time.

Repro: `python run_model.py -m ideal-4 -i data/inputs/rabbit.jpg`
