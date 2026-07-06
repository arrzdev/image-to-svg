# Research log

One entry per loop iteration, newest first. Format: what happened / what was
learned / what's next. `docs/STATE.md` holds the current consolidated state;
`docs/BACKLOG.md` holds the idea queue.

---

## 2026-07-07 · Loop N+1 — course correction: vision-first

**User verdict on the milestone:** benchmarks say we beat Recraft; eyes say
"<70% of their quality". Wobbly lines, width thinning, shadows painted over
line art. New goal set: research + improve continuously, judge by grid-crop
vision (ours vs Recraft vs ORIGINAL), idealize instead of copying source
noise.

**Done this loop:**
- Memory + docs infrastructure created (this file, STATE.md, BACKLOG.md) —
  updated every loop from now on.
- `backend/testbed.py` started: disk-memoized stage cache (image+params hash →
  labels/graph/fit results) so single-variable experiments run in seconds
  instead of 2-7 min.
- Vision diagnostic protocol: `testbed.crops()` renders ours/Recraft/original
  grid crops for eye judgment.
- Agents running: grail wall-clock (owns engine.py), stroke junction
  ink-pooling (owns strokes.py).

**Learned:** (from earlier tonight, context for the record)
- Independent-point DiffVG cheats via region overlap (2.5px divergence) —
  fixed with shared-edge parameterization; integrity judge catches the rest.
- Post-DV quality is coarseness-insensitive on clean partitions → coarse fits
  + DV = compact wins; but coarse fits can carry unheva unhealable slivers on
  detail-rich images — judge damage post-refinement.
- Both library "regressions" (wordmark, shield) were cheat-DV cleanup.

**Done (continued):**
- `backend/testbed.py` shipped and smoke-tested: stage cache works (fit 8.2s
  first run → 0.00s cached); `tb.crops()` produces original|variants vision
  grids (aspect-alignment bug found and fixed same loop).
- First vision diagnostic (outputs/diag_grid.png) confirms the user's
  defects precisely: three-way junctions wobble and thin, toe outlines
  angular, line width visibly varies vs Recraft's uniform strokes.
- Agents spawned: (a) literature/web research on clean-line vectorization
  (centerline methods, curve fairing/clothoids, sketch simplification,
  commercial tools' mechanisms); (b) width-constant contour experiment —
  full line network as constant-width strokes painted on top, judged by eye
  via testbed grids (owns backend/contours_exp.py).
- Still running from previous wave: grail wall-clock (owns engine.py),
  stroke junction ink-pooling (owns strokes.py).

**Landed later this loop:**
- **Grail wall-clock 289.6s → 79-84s (3.7x, verified)**: the three shared-DV
  refines now run concurrently in the process pool (spawn-safe worker
  rebuilds ctx in the child), structcheck threaded, torch threads governed
  per worker. Board identical to reference. engine.py has phase timing in
  the result dict now.
- **Clean-line research survey (agent, full citations in transcript /
  BACKLOG)**. Core diagnosis: clean-output systems (Potrace, Vectorizer.AI,
  Image Trace) fit the SIMPLEST curve within a tolerance band of the
  evidence; our refiner minimizes L2 to the raster and converges TOWARD
  noise. Ranked prototypes:
  1. **Deadband fidelity + curvature-variation (MVC) regularizer** in the
     shared-edge refiner; corners detected first and exempted (PolyVector
     lesson). ψ(r)=max(0,|r|−τ)², τ≈0.5px; κ(t) closed-form on cubics.
  2. **Potrace-style parsimony refit** in svgcore: minimal-segment DP
     (±0.5px straightness band), sub-pixel vertex adjust, tangent-to-polygon
     fitting (automatic G1), area-preserving Bézier merge.
  3. **L0 gradient-minimization pre-pass** (literally demonstrated on
     clip-art JPEG cleanup) + refine against the IDEALIZED raster.
  Later: centerline+width-profile strokes (Bao & Fu near-constant width),
  primitive/symmetry snapping (Vectorizer.AI's "designed" look).

**Landed (later still):**
- **Junction ink pooling** (strokes.py): filled discs at deg≥3 skeleton
  nodes (radius from local EDT max, gate 1.25× half-width; disc beat convex
  hull), + union-find contraction of sub-threshold junction-junction
  connector branches — root cause of the X-crossing pinch was medial_axis
  splitting shallow X's into two 3-way nodes whose connector got filtered.
  Elephant hybrid q 0.9094→0.9107 (+2σ), worst-region improved; visual: the
  smile/trunk crossing now meets at a single knot like the source. Width
  flare-blend near junctions REJECTED (EDT measures pooled union → paints
  outside ink, −0.0018 q). Emitter has ±0.0008 q run-to-run nondeterminism
  (threading in fill fit) — validate stroke changes on pickled contexts.

**All three line-quality agents landed (eye-verified):**
- **Width-constant contours = the breakthrough** (`contours_exp.py`, wired as
  `contour_lines` pipeline + `sb-contour`/`grail-contour` candidates): full
  dark network as constant-BASELINE centerline strokes (global width from
  ink-area calibration ≈5.95px; genuine swells + free-end tapers kept as
  symmetric ribbons; shape gate p90/med≥1.5 keeps eye glyphs as fills).
  MY eye check of the 4-way grid: uniform confident weight, clean junctions,
  round toes — clearly Recraft-class line work. 703 pts / 39 paths / 10KB /
  2.6s (q=0.864 — metric punishes idealization as expected). Remaining gap
  is fills/palette, not lines.
- **Deadband+MVC v3 refiner** (`refine_shared_v3.py`, NOT yet default):
  τ=1/255, λ=15, κ clamped at 2px⁻¹ (naive MVC too stiff for Adam), corners
  masked r=4. Long curves visibly calmer; known regression: thin-sliver tips
  blob. Needs multi-image validation + sliver gate before swapping in.
- **L0 idealization** (`idealize.py`, NOT a default): hurts clean flat inputs
  (plateaus→extra clusters→wobbly iso-contours, 825→2500 pts) but WINS on
  noisy detail-rich (fox: integrity 0.481→1.0, −27% size, watermark erased).
  Wire later as opt-in gated on a noisiness heuristic. lam=0.02.
- Junction ink-pooling landed earlier (see above).

**Cross-image QA of contour_lines (agent, eye-verified) + hardening:**
- Wins on genuine line art: rabbit (melted cheek-fluff → drawn lines),
  fox (75 vs 637 paths, q +0.012), chopchop (smile/sunglasses/leaf veins all
  cleaner, 297 vs 743 paths). Failure mode found: thick uniform dark BANDS
  (shield rim 36px, badge ring 40px) pass the shape gate and get
  stroke-ified at network width → silhouette erosion (q −0.28).
- FIXED: wide-band gate in contours_exp (med_w > max(12, 1.4% of max dim) →
  stays a fill) + dark_lum exposed as pipeline Param. Verified: shield
  0.553→0.847 (beats its 0.832 baseline), badge 0.799→0.900 (beats 0.876),
  elephant network kept (0.861@39 paths). contour_lines now safe standalone.
- Minor open nits: small closed rings become broken arcs (shield rivets),
  occasional gap/spur at dense junctions (rabbit charm).
- E2E after everything: grail 77s / fast 7.4s, boards stable; sb-contour
  loses on the metric (expected — metric can't see the drawn look) →
  BACKLOG: line-consistency metric component.

**Potrace-parsimony fitter LANDED (svgcore + wired):** full §2.2-2.4 port in
Rust — constraint-cone straightness (real potrace semantics, not the naive
0.5px test which over-segments 10x), lexicographic DP, sub-pixel vertex
adjust, α-family tangent-constrained cubics, area-preserving opticurve
merge. On RAW lattice polylines (no pre-smoothing): opttol 0.2 beats
smooth+Schneider on ALL axes (0.9164/1247pts/17.3KB vs 0.9151/1337/18.6KB);
0.5→1023pts@0.9157, 1.0→937@0.9134 — marching into Recraft's corner above
Recraft's quality. Eye-verified at 8192 zoom: no S-kinks, no notches, crisp
tapers. 32ms/120 edges. Wired: boundary.loops_to_svg_curves(parsimony=),
shared_boundary Param, candidates sb-pars02 (fast) + grail-pars05/10.
Caveats: alphamax 4/3 flips a fill (avoid); closed islands fitted as
pinned-open (cyclic DP would save more).

**User suggestion → preprocessing sweep agent running:** unsharp mask,
bilateral, mean-shift, combos + ADAPTIVE-k coupling (L0's missing piece).

**Next:**
- Grail e2e with parsimony candidates (running); v3 validation + preprocess
  agents out; integrate on GO.
- Line-consistency judge component; artifact refresh.

---

## 2026-07-06 → 07 (pre-docs, summarized)

Shared-boundary vectorization built and shipped (exact reconstruction,
boundary graph, per-edge Schneider fitting, smoothing, dissolve, split
paths). Shared-edge DV v1→v2 (honest, 3x faster, color opt). structcheck
integrity judge. Centerline strokes prototype (clean tips). Pareto frontier
mapped (tol5/w13 = 679 pts). Elephant: 0.9317@727 / 0.9246@679 / 0.9390@1337,
integrity 1.0. SVG-Bench still leading all splits. Library 16/16 grail,
17/17 fast. Milestone artifact:
https://claude.ai/code/artifact/24a07afa-9af5-48a3-8d42-87ad5fd12e52
