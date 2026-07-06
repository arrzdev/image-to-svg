# Backlog / idea queue

Ranked by expected visual impact (per the vision-first goal).

## Line quality (the user's three defects — TOP PRIORITY)

- [ ] **Width-constancy for contours**: the character outline is a
  constant-width digital stroke; our two-sided fills waver. Extend
  `strokes.py` centerline modeling to ALL dark contour networks (not just
  thin ones) with per-branch constant width; vision-judge vs Recraft.
- [ ] **Curvature-smoothness prior in fitting**: Schneider chases pixels;
  add a smoothing objective (penalize curvature variation / prefer long arcs)
  so fits look drawn, not traced. Recraft's lines read as single confident
  curves.
- [ ] **Line-art-on-top layering**: shading regions must never eat or overlap
  the line network. Partition-level: assign line pixels first, forbid
  shading regions from crossing a line's medial axis; or composite strokes
  as the final layer (stroke_hybrid already does — generalize).
- [ ] **Shadow/noise idealization**: detect soft-shadow / JPEG-noise regions
  in the source and simplify or drop them (the output should be CLEANER than
  the input). Possibly: bilateral/edge-preserving pre-filter strength tied to
  a noise estimate; or dissolve shading regions whose boundary contrast is
  low relative to the line network.

## Preprocessing (user suggestion 2026-07-07)

- [~] **Sharpen + edge-aware color aggregation before quantize** (agent
  running): unsharp mask (steeper AA → cleaner labels), bilateral/mean-shift
  flattening (limited effective palette), and ADAPTIVE-k coupling so the
  quantizer exploits the reduced palette. Prior art: L0 tested — hurts clean
  flat art, helps noisy inputs (opt-in, idealize.py).

## Judge upgrades

- [ ] **Line-consistency metric component**: the tournament objective can't
  see the drawn look, so idealized candidates (sb-contour q=0.864) lose to
  noise-copiers (sb-t10 q=0.9151) that look worse. Measurable proxy: for the
  dark line network in the OUTPUT render, compute stroke-width variance along
  medial axis + curvature-variation of centerlines; reward constancy/
  smoothness relative to the SOURCE's own line stats. Would let contour/v3
  candidates win on merit. (Design carefully: must not reward deleting lines.)

## Infrastructure

- [x] Disk-cached testbed (`backend/testbed.py`) — stage memoization.
- [ ] Vision judging harness: scripted grid-crop generator (ours / Recraft /
  original at 2-3 zooms, junction/tip/contour sampling) + a saved gallery per
  experiment for quick eyeballing.
- [ ] Auto-generated per-experiment HTML contact sheet.

## Speed

- [ ] Grail wall-clock (agent running: parallelize the 3 sequential
  refine_shared_v2 calls; trim redundant targets; cheaper safety nets).
- [ ] GPU diffvg (long-horizon; CPU renderer is the bottleneck).

## Quality research (online)

- [ ] How Vectorizer.AI / Recraft Vectorize achieve clean digital lines
  (classical CV + learned cleanup — dig for specifics: stroke modeling?
  curve regularization? learned line extraction?).
- [ ] Academic: line drawing vectorization literature (e.g., PolyVector,
  Noris et al. centerline methods, deep line normalization) — proven
  techniques for wobble-free contours from raster.

## Parked

- [ ] Gemini preprocessing arm (needs user's API key; cost-confirm first).
- [ ] Junction ink pooling (agent running on strokes.py).
- [ ] chopchop sample deep-dive (new sample dropped in samples/).
- [ ] Semantic containers (grouping regions into meaningful objects).
