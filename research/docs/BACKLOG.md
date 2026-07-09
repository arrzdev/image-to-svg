# Backlog / idea queue

Ranked by expected visual impact (per the vision-first goal — mission in
`docs/PROJECT_SPEC.md`). **See docs/RESUME.md for the paused-session handoff and
top priorities.** This is the **single idea queue** — the autoresearch loop
draws its next experiment from here.

## ⚠⚠ USER EYE-VERDICT 2026-07-08 — TOP PRIORITY
**The ranked defect scoreboard now lives in `research/docs/GAP_LEDGER.md`** (reach
Recraft first, then surpass; culprit protocol per autoresearch.md). Items below are
the original steer + seeds; the ledger is the working queue. NEW from user: the
PIZZA "ZZ" letterform strokes are broken/warped (ledger item 3).
The user reviewed v5 output directly. These outrank everything below. chopchop is
THE benchmark ("get close to Recraft on chopchop = amazing"); compare our chopchop
vs Recraft per zoomed grid square.
- [ ] **Line OVER-ROUNDING / poor straight lines.** pizza-box straight edges waver;
  rabbit heart pendant collapses toward a CIRCLE. The fitter rounds everything.
  Likely the same fitter co-bottleneck A-darkguard exposed (it19). Candidate dirs:
  the smooth/parsimony/Schneider fit path (contours_exp.py fill + strokes.py). Needs
  a straightness/corner prior that PROTECTS long straight runs and sharp vertices.
- [ ] **OVER-JOINING lines that shouldn't connect.** Our bridge/chord/extension
  chain (runs 3,4,15,20) is too aggressive somewhere. User idea: **color-guarded
  junction joining** — refuse a join when the colour breaks across it.
- [ ] **Meaningful small details removed** — rabbit paw/hand finger lines vanish.
  Distinguish drawn-intent detail from noise (despeckle/dissolve floor too blunt?).
- [ ] **Colour matching should target the ORIGINAL, not Recraft.** Earlier models
  matched colour better; now we copy Recraft's palette, sometimes wrong vs original.
- [ ] **Palette reduction too aggressive/global.** User idea: merge LOCAL neighbourhood
  colours smartly instead of a harsh global k reduction.
- [ ] **User research ideas to test:** pre-sharpen raster before vectorize (cut
  blur/AA squariness); tiled rasterization (grid of squares, vectorize each, merge).

## contour_lines stroke defects (USER report 2026-07-07 — TOP PRIORITY)

Files: backend/contours_exp.py + backend/strokes.py. Judge by 4096 zoom crops
at the affected spots.

- [x] **Junction joins / long label-map losses** — SHIPPED run 15 (44351d0,
  candidate B): source-supported chord bridges (mutually-facing ends cos>=0.3,
  <=7.0*gw, whole-chord dark support with bright-run gate). Rabbit heart/paw/
  scallops + elephant ear/toe/belly seams close; 0 welds on chopchop.
  Measured negative result: the run-4 ridge walker NEVER reached its 4w cap
  (dies 0-2.3w: absolute dark_lum on antialiased ink, ridge test beside
  shading, |dTheta| turn budget burnt by staircase jitter in 5-9 steps).
- [x] **Rabbit heart top-left lobe** — SHIPPED run 20 (c61755e, it17
  B-arcsupport). Diagnosis CORRECTED: not a >72deg divergence — the
  counterpart ends were consumed by an earlier midpoint bridge; the long
  bridge required two FREE ends. Fix: bridge free ends to ANY endpoint via
  tangent-arc (<=2.5gw) or strict chord (turn<=40, mean<50) + ridge2>=0.5
  both-sides-light gate. Heart + tuft closed; chopchop trunk x2, 0 welds.
- [ ] **Heart lobes render flattened** (run-20 B lead; staged run-21-wait,
  `diag18_lobe.png`): rawquant preserves the two-lobe crown; _despeckle
  degrades the thin outline arc at the left-lobe apex (gray shadow-tone blob
  displaces it) and shallows the notch; the fill fitter rounds the rest.
  THIRD member of the label-chain thin-boundary-feature family (with monster
  teeth = light spikes, rabbit buttons/ring = dark annuli). A general
  boundary-subfeature guard in despeckle/smooth could close all three —
  evaluate it18 A-spikeguard's mechanism for generalization.
- [ ] **Thin dark subfeatures eroded by the label chain** (run-20 lead,
  CORRECTED by run-21-wait diagnosis `diag18_buttons.png`): rabbit's button
  ring (~(358,676)) and strap J-curve arrive at rawquant INTACT and leave
  despeckle/smooth as open "u"/")" hooks — the loss is in the LABEL CHAIN,
  not skeletonization as first logged. This is the dark-on-light DUAL of the
  monster-teeth disease (it18 A-spikeguard protects light spikes on dark
  regions): thin dark annuli/curves inside light regions need the same
  boundary-subfeature protection. If it18-A ships, extending its guard to
  the dark side is a ready follow-up candidate.
- [ ] **Ridge walker: charge NET signed turn** (run-15 B lead): swapping the
  per-step |dTheta| for net curl would restore the walker's intended 4w range
  if it's ever needed again.
- [~] **Chopchop chair-lattice junction tangles** (run-15 observation;
  run-17: LOCATED at (425,790)@1024, `diag17_nubs.png` row 1): the knot/ring
  junction renders as a tangled glyph with doubled bars; bar ends show flat
  butts. **it19-wait re-diagnosis (`diag19_lattice.png`, head19 e759194):
  the "tangle" is NOT reproduced at (425,790) — the ring now renders as a
  clean dark annulus and the lattice bars are clean vs Recraft.** The
  original observation predates the run-14 pool clamp AND the run-18 rng-pin
  (the "tangle" was likely the medial_axis tie-order nondeterminism, now
  pinned). Residual is only the flat-butt bar ends — which is the SAME
  defect as the "Rectangular nub artifacts" item below, currently owned by
  it19 candidate B-ribboncap. DO NOT stage a separate lattice-tangle
  candidate without a fresh diag showing a residual tangle; fold any
  remaining flat-butt cases into the ribbon-cap work.
- [x] **Chopchop interior-scribble nondeterminism** — CLOSED by run 18
  (da5d4b6 rng-pin): verified directly post-pin, two chopchop renders are
  BYTE-IDENTICAL (hash b4510fe016 twice). Chopchop eye comparisons are no
  longer noisy; the run-15 "k-means" attribution was the medial_axis
  tie-order all along (run-17 root cause).
- [x] **Some curvatures differ from original** — RESOLVED as measured (run 5,
  2026-07-08): mean source-skeleton→render drift 0.04px, p95=0 at current HEAD;
  the v4-era report predates runs 2–4. Negative result: parsimony centerline
  fit ≈ smooth+Schneider by eye and costs more points — don't retry without a
  new reason.
- [ ] **Rectangular nub artifacts at joins** — AUDITED run 17, mechanism
  identified: true strokes already emit `stroke-linecap="round"`; the nubs
  come from `kind in ("wedge","ribbon")` elements, which are FILLED POLYGONS
  whose ends are flat width-spanning segments (209 such elements on
  chopchop). Pictured: flat-butt lattice bar ends at (425,790)@1024 and a
  rectangular maroon slab ~(600,640) (`diag17_nubs.png`). Fix candidates:
  emit semicircular end arcs on ribbon polygons, or convert short ribbons
  to round-capped strokes at emission.

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
- [~] Harness quirk: chopchop sanity quality ≈ 0.14 — MOSTLY EXPLAINED run 14:
  the solid-black straw bar (and friends) were tanking the composite; fixing
  them took it to 0.673. Still trails other targets; eye remains the gate.

- [ ] **Rabbit coat buttons lost** (run-18 pin eye pass, pre-existing):
  the two coat-button circles render as a thin vertical line + small hook
  in ours (~(358,676)@1024); original AND Recraft draw circles. Small
  closed light-ringed circles on white ground — likely eaten at despeckle
  or absorbed into the seam stroke. Eye-loud on a gold-pair target.

## Chopchop residuals (post-v5)

- [x] **Brown flecks** — SHIPPED run 12 (4c616ce): adjacency fleck absorption
  (<250px dark fragment 8-adjacent to ≥10× larger dark component → reassigned;
  stroke-layer only). chopchop 234 flecks→line, −50KB. The run-11 union family
  was the wrong tool; adjacency is the right one.
- [x] **Trunk texture noodles** — SHIPPED run 13 (b409934, candidate A):
  `_wiggle_rate` alternating-turn-density gate >2.2 per branch + small-component
  gate + free-end trim; dropped ink carved to fill layer (soft daubs, Recraft's
  treatment). Measured separation: real lines ≤1.9, texture daubs 2.4–7.8.
- [x] **Junction blobs** — SHIPPED run 14 (3d251ad, candidate B): pools were
  blob-split FILL splats + swollen ribbons. Fix: pool components <4.0×med_w
  containing a deg≥3 skeleton node stay in the stroke mask; swell profile
  clamped within 2.5×w_body of junction nodes. Discriminator measured: pools
  ≤3.8×med_w, genuine glyph blobs 6–14×med_w.
- [x] **Black-blob flood (straw) / light accents eaten by despeckle** —
  SHIPPED run 14 (3d251ad, candidate A): `_despeckle_labels` light-accent
  guard (ring ≥0.6 ink among SURVIVING neighbors — fellow sub-floor fragments
  excluded, that's what makes sandwiched stripes work — + ≥80 lum gap).
  Rescued: chopchop straw stripes, crystals gem vein, monster scratch
  T-branches, fox eye glint, game-assets potion highlight. Also mostly
  explains the chopchop metric quirk (0.144→0.673 after the fix).
- [x] **Thin light regions bead at vectorization** — SHIPPED run 15 (44351d0,
  candidate A): diagnosis correction — the LABEL CHAIN dashes the line (6
  fragments), not the fitter alone; fix = source-traced light capsules
  (>=3-fragment gate, flux-based width 1-3px). Monster scratches continuous.
  Leads still open below (apex nub; fragments=1 slivers).
- [x] **Capsule-end nub at scratch apex** — SHIPPED run 19 (1e0adb6,
  it17 A-apexsnap): diagnosis CORRECTED — the nub was the fill fitter
  curling a corridor-carried background tentacle tip, not capsule overshoot.
  Fix: absorb corridor-overlap pixels >6px reach from the out-of-corridor
  body (grazes max 5.0 vs carried mass 8-53). Also cured the mid-segment
  double-render.
- [ ] **Fill-fitter tip-curl family** (run-19 A lead): free-ending thin
  tentacles of large fill components curl at the tip (the apex nub was one;
  chopchop strap-end curl and swoosh hooks suspected same family) — a
  general tip-straightening or tentacle-absorption rule could close several
  BACKLOG items at once.
- [ ] **Corner-aware capsule fit** (run-19 A lead): Recraft draws the
  monster apex as a sharp Lambda; our capsule fits a rounded crest. Split
  capsule centerlines at high-curvature apexes with miter joins (run-10
  serration treatment applied to capsules).
- [x] **Whole-carried thin light slivers render lumpy** — SHIPPED run 16
  (9242186, candidate A-sliver): whole-carried components stolen iff the mask
  confesses lumpiness (cv_w≥0.2 AND wmean/max(med_w,2)≤1.45, skel≥20px,
  light coverage≥0.5) + bead-pixel absorption + `_extend_into_light` end
  tucking (≤8px, dot≥0.5 cone). Monster capsules 2→5; fox 4 / crystals 1 /
  game-assets-2 6; zero regressions on the first full-coverage (§8) gate.
- [ ] **Mouth-corner hook falls between the bands** (run-16 A lead, monster
  x494-507/y240-261): cv_w 0.396 but fatness ratio 1.73 — above the steal
  band (≤1.45) yet below nothing (eye-tail rejects sit ≥1.53 by design).
  Ratio tuning is exhausted; discriminate with a donor-size or curvature
  signal instead.
- [ ] **Donor stump where a sliver is stolen** (run-16 A lead, monster x531):
  the donor fill keeps a rounded stump at the capsule take-off point —
  fill-side sharpening (carve the stump along the capsule axis) would finish
  the hand-off.
- [~] **Render nondeterminism — ROOT-CAUSED run 17 (research), fix queued**:
  NOT k-means (seeded; label chains hash byte-identical). It is
  `skimage.morphology.medial_axis(rng=None)` permuting tie-pixel order and
  consuming global RNG → capsule centerlines + dark-stroke skeletons wobble
  (wheel white-arc, counts 195–200/64–68, mountain crevasse shuffle, ~8k px
  diffpx floor). Fix = fixed `rng=` at 6 call sites (contours_exp.py
  353/441/1122/1153, strokes.py 99/123), ONE atomic commit at it17
  integration + fresh eye pass on all touched targets (tie-picks shift once,
  then freeze).
- [ ] **Strap-end curl loopier than reference** (run-14 B lead; run-21-wait
  layer-strip `diag18_curl.png`: curl reproduces in the STROKE-ONLY render —
  confirmed free-end/ribbon shaping in the stroke layer, NOT the run-19
  fill-fitter tip-curl family). Look at run-4 ridge-extension tails.
- [ ] **Residual S-wavy strokes under the wiggle gate** (run-13 A lead): a few
  wavy strokes sit at wiggle 1.5–2.2 on chopchop; lowering the cutoff welds
  real lines. Needs a SECOND signal (width variance along branch? contrast vs
  surrounding fill?) — not a lower threshold.
- [ ] **ink_extended≈102 regrows hooks off texture remnants** (run-13 A lead):
  run-4 ridge extension re-attaches small hooks where the wiggle gate dropped
  texture on chopchop. Ablate ridge extension against the gate; consider
  skipping extension for free ends created by gated components.
- [x] **Shading despeckle above the despeckle floor** — SHIPPED run 13
  (b409934, candidate B): `_dissolve_speckle` floor 300 after `_smooth_labels`,
  with THREE guards, each earned by a regression caught at eye-verification:
  ink-locked (never dissolve into dark labels), ring-dominance ≥0.6 (protects
  facet mosaics — crystals gems), darker-only luminance (light accents are
  drawn intent — mountain cloud wisp, plank highlights; noise daubs are dark
  stains). Chopchop planks flatten clean.
- [ ] **Tiny dark ink daubs policy** (run-13 open): sub-300px DARK components
  are exempt from dissolve by the ink-lock; some are genuine noise. Adjacent
  ones get stroke-layer fleck absorption (run 12); ISOLATED dark daubs still
  pass through untreated. Decide a principled rule.
- [x] **Black-blob lattice flood** — RESOLVED by reframe, run 14: the visible
  "flood" was the straw (despeckle eating its light stripes → one wide dark
  region, candidate A) plus junction pooling (candidate B). No separate
  lattice-splitting mechanism needed; don't build one without a NEW grid
  showing a residual case.
- [x] **monster-flat-line drops a thin white scratch line** — RESOLVED by the
  run-15/16 capsule work; run-17 research swept ALL thin light-on-dark
  components on monster: none fully missing (closed by eye at the 3
  lowest-presence spots, `diag17_scratch.png`). Remaining light-line defects
  are the mouth family (items below).
- [x] **Monster mouth teeth scalloped** — SHIPPED runs 21+22 (it18 A+B
  compound, c51d025 + ea329bd): B corner-pins fill fits (V-notches survive
  as hard vertices; corpus-wide sharpness win), A rescues+welds severed
  spike tips in despeckle (diag17 corrected: loss is DISCRETE tip-severing
  at quantize, not gradual erosion; gap>=210 population-measured). Teeth
  now tall AND sharp, approaching Recraft. Residual polish: mid-teeth sit
  ~1px lower than Recraft (smooth-stage nibble); mouth-left plateau step.
- [x] **Pin k-means determinism** — CLOSED by run-17 research: the run-12
  attribution was WRONG; k-means is seeded and stable (label chains hash
  byte-identical across processes). The real source is medial_axis tie-order
  (see the root-cause item above). Kept as a record so "k-means
  nondeterminism" folklore doesn't resurface in future entries.

## Judge upgrades

- [ ] **Line-consistency metric component**: the tournament objective can't
  see the drawn look, so idealized candidates (sb-contour q=0.864) lose to
  noise-copiers (sb-t10 q=0.9151) that look worse. Measurable proxy: for the
  dark line network in the OUTPUT render, compute stroke-width variance along
  medial axis + curvature-variation of centerlines; reward constancy/
  smoothness relative to the SOURCE's own line stats. Would let contour/v3
  candidates win on merit. (Design carefully: must not reward deleting lines.)
  Run-21-wait methodology check: whole-component cv_w is USELESS — elephant
  scores ours 0.295 vs Recraft 0.363 (we "win") because component-level stats
  can't see per-branch wobble, and monster's dark mask is a FILL (its lines
  are light-on-dark). A real metric must decompose junction-to-junction
  branches (strokes.py) and treat light-line layers separately.

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

- [x] **Pre-existing deep-zoom hairlines on shield / pizza box / logo_badge**
  — DOES NOT REPRODUCE at v5 HEAD (run-17 research): shield 1.000,
  logo-badge 1.000, elephant 1.000 on structcheck defaults; the recorded
  0.1–0.8 was measured on engine v2/v3 and intervening work fixed it. Only
  pizza-box retains a residual (0.875) — folded into the eversion item below.
- [ ] **Thin-region eversion under wide smoothing** (pizza residual; run-17:
  166 hairline px, down from 1030): localizes to TWO spots — worst at
  (285,170)@1024 (eyed, `diag17_pizza_gap.png`): hairline crack along the
  box-lid underside PLUS a gray everted lens floating in the blue fill at
  the same site; second cluster at (932,276). smooth_edges moves opposite
  edges of sub-window-width regions past each other → self-intersecting
  lens + cracked seam. Fix: thickness-aware smoothing clamp or post-fit
  crossing check. (Parsimony fitting sidesteps it — no smoothing.)
