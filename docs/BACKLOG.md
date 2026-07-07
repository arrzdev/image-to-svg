# Backlog / idea queue

Ranked by expected visual impact (per the vision-first goal — mission in
`docs/PROJECT_SPEC.md`). **See docs/RESUME.md for the paused-session handoff and
top priorities.** This is the **single idea queue** — the autoresearch loop
draws its next experiment from here.

## contour_lines stroke defects (USER report 2026-07-07 — TOP PRIORITY)

Files: backend/contours_exp.py + backend/strokes.py. Judge by 4096 zoom crops
at the affected spots.

- [~] **Junction joins:** run 2 (c0adad6) fixed same-component T/Y nubs via
  nearest-centerline anchoring (0.8w); run 3 (2570c63) bridged cross-component
  dash-gaps (1.2w, fwd<60°, midpoint end-to-end). REMAINING: **long label-map
  losses (>1.2w)** — rabbit's heart-left outline still breaks where the label
  map lost a long ink run. Candidate: source-ink-continuity extension — walk
  the darkness ridge in the ORIGINAL raster beyond the label map and extend
  the stroke along it. Negative results: contour_lines drops zero
  junction-junction connectors at defaults; missing-ink clusters ≈ deliberate
  width_scale undershoot, not gaps.
- [x] **Some curvatures differ from original** — RESOLVED as measured (run 5,
  2026-07-08): mean source-skeleton→render drift 0.04px, p95=0 at current HEAD;
  the v4-era report predates runs 2–4. Negative result: parsimony centerline
  fit ≈ smooth+Schneider by eye and costs more points — don't retry without a
  new reason.
- [ ] **Rectangular nub artifacts at joins** — butt caps / segment seams at
  branch joins render little rectangles. Audit `_stroke_elements`/`_ribbon`
  cap+join style (want round joins); ensure continuation-merged branches emit
  as ONE path, not abutting segments. (Cap poke-through variant fixed in run 2;
  check remaining seam/butt cases on chopchop.)

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

## Shape & palette idealization (run-6 diagnosis, 2026-07-08)

- [x] **Serration/notch shape idealization** — SHIPPED run 10 (50c0a03) (run-7
  research): heavy outlines are the FILL layer; Recraft-style fix = centerline
  network with CORNERS AS HARD NODES + constant width + `stroke-linejoin:
  miter` (miterlimit 6-10) so every V-notch re-sharpens geometrically (the
  renderer extends edge tangents to intersection). Notch-pool detection: local
  width max (>1.3·w_med) COINCIDENT with high turning angle (θ>~40° over a
  ~2w chord) → split centerline there, fit branches ignoring pooled pixels,
  miter joins them. Prior art: Puhachov 2021 keypoint-driven PolyVector
  (github.com/ivanpuhachov/line-drawing-vectorization-polyvector-flow),
  PolyFit Dominici 2020 (corner-plausible polygon first), Favreau 2016
  fidelity-vs-simplicity energy, Potrace alphamax. First experiment: on the
  serration bands only — corner breakpoints (drop corner_deg to detect V's)
  + miter joins in `_stroke_elements` for those paths + constant width.
  Negative result kept: swell cap + relaxed gate WITHOUT corner/miter = lateral.
- [x] **Palette re-grading — REFUTED by measurement** (run 8,
  `experiments/measure_ramp.py`): across all 8 gold pairs, chromatic-midtone
  deltas ours→Recraft center on ZERO (dL +0.001±0.044, dC +0.002±0.032; fox/
  chopchop/mountain/logo/monster match to ~0.005). Recraft does NOT re-grade
  tints — do not build a re-grader. The elephant's apparent tint gap is
  structural: our TWO mid shadow tones (aeb4c8 3.1% + 98bee3 2.5%) map onto
  Recraft's ONE (a6b8d0) — they MERGE shading tones.
- [x] **Merge near-duplicate shadow tones** — SHIPPED run 9 (a3ccbd3):
  `_merge_shadow_tones` (C<0.08, |dL|<0.03, dE<0.06 + hue-opposition guard
  cos dh>0.3). Elephant shadow = Recraft's tone (a4b8d1 vs a6b8d0). Lesson:
  never merge across warm/cool even at low chroma (mountain snowband).
- [ ] Harness quirk: chopchop sanity quality ≈ 0.14 (alpha/background
  handling in metric?) — numbers meaningless for this target, eye only.
  Investigate as a deliberate re-baseline step if it starts mattering.

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

## Bugs to chase

- [ ] **Pre-existing deep-zoom hairlines on shield / pizza box / logo_badge**
  shared-boundary emissions (structcheck 0.1-0.8 BEFORE any refinement, v2
  and v3 alike; elephant/rabbit are 1.0). Contradicts coincidence-by-
  construction — suspects: split_paths grouping on these images, closed-loop
  border cases, or non-square viewBox handling in emission. Reproduce with
  testbed + structcheck diagnostics per image.
- [ ] **Thin-region eversion under wide smoothing** (pizza residual 1030px):
  smooth_edges moves opposite edges of sub-window-width regions past each
  other → unfilled lens. Fix: thickness-aware smoothing clamp or post-fit
  crossing check. (Parsimony fitting sidesteps it — no smoothing.)
