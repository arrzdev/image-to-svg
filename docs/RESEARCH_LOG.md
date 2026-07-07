# Research log

Append-only, newest first. **Iterations are worktree-parallel** (autoresearch.md
"Worktree-parallel iterations"): log an entry for **every candidate worktree** —
whether it ships alone, ships in a combination, or is discarded — not just the
shipped result. Each entry:
- **What was tried** — the specific change + which module/domain/worktree.
- **What the `tb.crops` grid showed** — including anything unrelated or
  disproportionate to the change (unexpectedly clean regions, odd side effects).
- **Verdict + the real reason** (orchestrator's own re-verified eye verdict, not
  the sub-agent's self-report). Benchmark delta if the sanity harness was run.
- **If discarded — a lead-grade note:** which target, which spot, which
  parameter, what it looked like — pickable-up later, never just "investigate."
- **If discarded when combined:** name the combination, so that interaction is
  not retried blind.
- **commit sha** for anything that shipped.

When picking the next iteration's candidates, skim recent discard entries here
for unfollowed threads worth promoting into docs/BACKLOG.md items. Mission:
`docs/PROJECT_SPEC.md`; `docs/STATE.md` = consolidated state; `docs/BACKLOG.md` =
idea queue. Machine-readable results → `autoresearch.jsonl`; running narrative →
`experiments/worklog.md`; in-flight worktree state → `autoresearch.iteration.json`.

---

## 2026-07-08 · Run 13 (iteration 13) — 2 candidates, BOTH ship combined (A+B, commit b409934)

Two independent candidates in worktrees off best `4c616ce`… (`e0a1c45` local
best snapshot); both orchestrator-verified, combined one-at-a-time in an
`_integrate` worktree with re-verification after each apply. Integration
surfaced two regressions in B; both fixed by orchestrator-authored guards
inside the integration worktree, re-verified, shipped.

**Candidate A-noodles — VERIFIED, SHIPPED in combination.** Change
(`backend/contours_exp.py`): three-part texture gate on the stroke network —
`_wiggle_rate` = alternating-turn density (total |turning| − |net turning|) /
arclength per branch; real drawn lines measure ≤1.9, texture daubs 2.4–7.8
(measured, not guessed); gate at >2.2 before `_merge_continuations`, plus a
small-component gate and free-end trimming; ink dropped from the stroke layer
is carved into the FILL layer so texture reads as soft daubs, not vanishing.
Grid (orchestrator's own render): chopchop trunk's squiggly stroke "noodles"
become soft fill daubs matching Recraft's treatment; knot daub soft; real
lines (serrations, outline, eye) untouched. Residual lead: a few S-wavy
strokes sit just UNDER the gate (wiggle 1.5–2.2) — a lower threshold welds
real lines, so any further cleanup needs a second signal (width variance?
fill-contrast?), not a lower cutoff. Second lead: `ink_extended≈102` on
chopchop — run-4 ridge extension regrows small hooks off texture remnants;
worth an ablation pass.

**Candidate B-speckle2 — VERIFIED after 2 debug guards, SHIPPED in
combination.** Change (`quantize_contours.py` + `contour_lines.py` call):
`_dissolve_speckle(labels, centers, 300)` after `_smooth_labels` — exactly the
run-12 lead (floor ABOVE despeckle's 120). Guard saga, all caught by
eye-verification, all fixed in `_integrate` by the orchestrator:
1. **Ink-locked** (from dispatch): counts zero'd for dark labels — dissolve
   never feeds the line network.
2. **Ring-dominance ≥0.6** (debug 1): unguarded B1 ate the orange gem's facet
   mosaic on crystals (a facet's neighbors are many labels; a noise daub sits
   in a single-label ring). Guard restored facets; chopchop win held.
3. **Darker-only luminance** (debug 2, found in broadening): combined AB
   deleted a drawn cloud wisp beside the mountain peak — isolated to B (A
   never touches fills). Noise daubs are DARK stains; LIGHT accents are drawn
   intent (cloud wisp, plank-top highlight — Recraft keeps both). Dissolve
   only when source is darker than target. Cloud eye-confirmed restored at
   the actual wisp coordinates (located via label-map analysis, not assumed).
Effect: chopchop plank speckle flattens to clean planks.

**Combined verdict (orchestrator eye, all 8 targets under final guards):**
chopchop planks flat + noodles gone + serrations sharp; crystals facets intact
AND the pink shoulder-fleck that prev painted on the orange gem is GONE in new
(original has no pink there — prev artifact removed, a small bonus); mountain
cloud restored; elephant/rabbit/fox clean (checked pre-darker-guard; guard
only makes B dissolve LESS, and their B-fire sites were re-eyed);
logo-geometric + monster-flat-line re-rendered fresh under final AB2 —
diffpx 0 AND eye-identical. Non-regression lead spotted on monster: BOTH new
and prev drop a thin white scratch line inside the dark shape that Recraft
keeps — pre-existing hairline-detail loss, → BACKLOG. Sanity: chopchop
quality 0.144 (known-meaningless for this target), elephant 0.8574 /
ssim 0.9624 / 2645 pts — series-consistent.

**Interaction note:** A+B combined cleanly (A = stroke layer, B = fill labels;
disjoint domains). The two B regressions were B-alone effects exposed at
integration time, not A×B interactions. No bisect needed.

---

## 2026-07-08 · Run 12 (iteration 12) — FIRST worktree-parallel iteration: 2 candidates, A ships, B discarded

Architecture test + real iteration. Two independent candidates dispatched to
parallel git worktrees off best `32da8eb`; orchestrator independently
re-rendered both (did NOT trust sub-agent self-reports) and reached a different
verdict than one sub-agent.

**Candidate A-fleck — SHIPPED (commit 4c616ce).** Change: adjacency-based fleck
absorption in `backend/contours_exp.py` `extract_contour_strokes` — a small
(<250px) dark-label component 8-adjacent to a ≥10× larger component of a
*different* dark label is reassigned to the big neighbor (stroke-layer copy
only; fill `labels` untouched). This is the run-11 "next design" (union family
was refuted there). `tb.crops` (orchestrator's own render, cols
original|A|prev|recraft): the medium-brown fleck-wedges nested in chopchop
serration notches are absorbed into the black line they hug; serration teeth
stay sharp; no shading welded (large bands never hit the 10× ratio). Broaden (all
EYE-CHECKED, not inferred): rabbit absorbs a stray blue dab (collar) + a gray
belly-line fleck — small genuine cleanup; **elephant** grid A-vs-preA visually
identical (true no-op, `flecks_absorbed=0`, single dark label); **fox** grid
A-vs-preA equivalent by eye — eyes/ear-lines/whiskers/fur intact, nothing
welded or broken — but **81 flecks DID fire on fox** (it is NOT a no-op; the
low diffpx only meant each reassigned fragment is tiny). logo/monster
bit-identical.

Correction on record: I initially labeled elephant AND fox "no-op within noise"
from `flecks_absorbed`/diffpx alone. That was wrong for fox (81 flecks fired) —
vision-first means render and look, never infer "probably fine" from a number,
including a noise-floor number. Both grids were then rendered and eye-checked
(outputs/it12_eyecheck_{elephant,fox}.png); both clean, verdict holds. **Disproportionate side effect (noted):** chopchop
SVG ~50KB smaller (259KB→209KB) and 234 flecks absorbed — each fleck had been
emitting its own brown micro-stroke, so the fix cleans the outline AND cuts
file size. quality (elephant sanity) 0.849, points 2604.

**Candidate B-speckle — DISCARDED (orchestrator overruled the sub-agent).**
Change (in its worktree, never merged): `_dissolve_speckle` in
`quantize_contours.py` dissolving sub-`min_area` NON-dark components into their
majority neighbor, called after `_smooth_labels`. Sub-agent self-reported
"beats prev (mild)". **Orchestrator's own eye verdict: LATERAL — not clearly
better, discard.** Lead-grade note for later: on chopchop the tan trunk/plank
speckle is *barely* changed at spots (2600,1500)/(3000,1400)/(1800,1200)
because `_despeckle_labels` already runs first at floor `max(min_area,16)=120`
and clears most <120px fill components before `_dissolve_speckle` sees them —
so the pass is nearly redundant. **To make it real, it must dissolve at a floor
ABOVE what despeckle already applies** (e.g. 200–400px) and/or target the
components `_smooth_labels` *re-creates* afterward; retry only with that
change, on the trunk-plank speckle specifically. One observed non-speckle side
effect: a thin white seam between a dark blob and its outline got filled solid
(a blob's tiny component handed to its dark surround) — a fill change slightly
outside the "speckle" framing, worth watching if retried.

**Methodology finding (affects all diffpx gating, not just this run):** the
pipeline is **non-deterministic across renders** — same code, two renders →
~8.3k-pixel self-diff on the elephant (cv2 k-means is not fully seed-stable
across processes). So "diffpx" spot-finding carries a per-image noise floor
(~8k elephant). A number below it does NOT imply "no change": fox diffpx 8379 ≈
floor yet 81 flecks fired — the reassignments were just individually tiny, and
only the eye-check confirmed them harmless. The EYE verdict — the actual gate —
is what settles it; treat diffpx as a spot-finder, never a verdict, and never
infer a candidate is fine from it. New
BACKLOG item: consider pinning k-means determinism for cleaner ablations.

**Architecture test result:** 2 parallel worktrees ✓; orchestrator
independently re-verified both, overruling B's self-report ✓; `/clear`
mid-cycle resume surfaced the live state (both single-winner and simulated
multi-winner mid-merge) ✓; both worktrees removed regardless of outcome ✓.

---

## 2026-07-07 · Run 4 — source-ink ridge extension (commit 5eb37ad)

**What changed:** bridging (run 3) spans gaps ≤1.2w; longer ink runs lost by
despeckle/label-smoothing still broke lines (rabbit heart, elephant ear). A
still-free end now walks the SOURCE raster's dark ridge (probe fan, darkest
sub-`dark_lum` pixel per step, ≤4 widths), snapping to another stroke if
reached, else keeping the traced tail with a taper at the true ink end. Two
guards proved essential (debug attempt 2): a **perpendicular ridge test**
(light ground within ~1.1w on both sides each step — never roam filled
regions) and a **~120° cumulative turn cap** (kills blob-boundary curls).

**Eye verdict:** rabbit heart arcs + coat edge near-continuous, sleeve and
carrot-vein joins closed; elephant's lost ear line completes to the silhouette;
chopchop's long-detached handle outline finally attached (fixed a pre-existing
defect); fox/crystals equal-plus; mountain/logo/monster unchanged. 8/8.

**Benchmark (sanity):** rabbit 0.713 → 0.7272. Elephant composite 0.8708 →
0.8599 with FLAT sub-metrics (ssim −0.0015) — dip sits in the composite's
noisy coherence/local terms while the eye is clearly better; logged as a flag,
not a gate. Unguarded version (roaming walker) was caught by eye on chopchop
and never shipped — negative result kept.

**Next:** true source gaps (light-pixel jumps where tangents agree) — riskier;
curvature drift; chopchop junction ink pooling.

---

## 2026-07-07 · Run 3 — bridge free ends across label components (commit 2570c63)

**What changed:** the label map breaks a drawn line wherever a lighter region
crosses it (straps, highlights, AA fuzz); the pieces land in different
components, share no skeleton node, and every break rendered as a dash-gap —
rabbit's outlines were dashes. In `extract_contour_strokes`, a free end now
snaps onto another stroke within 1.2 widths when the target lies <60° off its
outward tangent (never sideways onto a parallel neighbor); mutually-facing free
ends meet at the midpoint; snapped ends lose free status (no taper, no
stub-drop — which also rescues tiny bridge dashes).

**Eye verdict:** rabbit heart/cheek/paw dash-gaps closed; elephant ear
junctions now fully joined (they were cross-component too); chopchop safe (60°
gate rejected all parallel-line snaps); crystals/fox/mountain equal-or-better;
logo-geometric/monster-flat-line bit-identical. 8/8 no regression.

**Benchmark delta (sanity):** elephant 0.8669 → 0.8708 (above the 0.8682
baseline — bridging restores real ink, so even the noise-loving metric agrees).
Rabbit first reference: 0.713 @ 4339 pts. Focus target moved elephant → rabbit
this run (defect showed there; `./autoresearch.focus`).

**Remaining (logged in BACKLOG):** long label-map losses (>1.2w) still break
rabbit's heart-left outline — needs source-ink-continuity extension (walk the
darkness ridge in the ORIGINAL raster beyond the label map).

---

## 2026-07-07 · Run 2 — junction anchor: flush joins, no more nubs (commit c0adad6)

**What changed:** `extract_contour_strokes` (contours_exp.py) anchored branch
ends at the junction node-cluster *centroid*; ink pooling elongates that
cluster, so the centroid sits off the through-line's centerline and the round
cap pokes a nub through it — visible on the silhouette (elephant ear T) as a
bump into the sky. Now ends anchor to the nearest pixel of another kept
branch's centerline within a 0.8-width radius (fallback: centroid), so caps
land flush under the through stroke by construction.

**Why 0.8w:** the first attempt (1.5w) snapped ends onto *parallel neighboring*
strokes in dense-line art — chopchop grew detached ends and white slivers.
Through-lines pass ≤0.5w from the centroid; parallel neighbors sit ≥1w away.

**Eye verdict (8k grids, new vs prev vs Recraft):** elephant T-nub gone and
Y-join flush (both now match Recraft's cleanliness); chopchop joins continuous;
crystals facet-edge breaks now connect; rabbit/fox/mountain unchanged;
logo-geometric/monster-flat-line bit-identical. 8/8 no regression.

**Benchmark delta (sanity only):** quality 0.8682 → 0.8669 (−0.15%), ssim
0.9643 → 0.9630 — expected: the nub covered source ink, and the metric rewards
copying it (PROJECT_SPEC §4). Eye verdict rules.

**Negative results kept:** (a) "dropped junction-junction connector" hypothesis
refuted on the elephant — contour_lines drops zero such connectors at defaults;
(b) missing-ink clusters are mostly the deliberate width_scale=0.85 undershoot,
not gaps — don't chase them as defects.

**Next:** rabbit's ear line stops short of the outline in both versions — a
*cross-component* junction (different label components ⇒ no shared skeleton
node ⇒ anchoring can't reach). That's the remaining true "crossing gap" class.

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

## 2026-07-07 · Preprocessing sweep landed (user suggestion)

Bilateral (d9,σc50,σs9) = safe win: parity on clean flat, rescues soft-shaded
AI art (rabbit coat seams solid again, q .669→.757 pre-DV; fast-tier verify:
sb-bilat 0.8327@2225 = top compact candidate). Mean-shift (sp12,sr30) = noisy
detail winner (fox −37% pts, most "designed" look) but eats small details —
candidate only. UNSHARP REJECTED with data: overshoot mints new colors,
+30-60% unique colors, MORE halo clusters (inverted hypothesis). Adaptive-k
unnecessary — merge_de consolidation already adapts downstream. Wired:
preproc param in shared_boundary + candidates sb-bilat / grail-bilat /
grail-ms (meanshift+parsimony). backend/preprocess.py has the recipes.
Also this loop: git repo initialized (v3 = first commit), models/vN
snapshot convention, parsimony e2e (pars05+dv q=0.9394@1023 board 2nd).

## 2026-07-07 · v3 refiner swapped in (GO) + hairline hunt

v3 (deadband τ=1/255 + MVC λ=15, sliver-gated) validated across 5 images:
eye equal-or-better everywhere, no new artifact class; the sliver-tip blob
was killed by a DYNAMIC thin-zone gate (tips extrude during optimization —
init-time masks miss them). Swapped into engine DV worker. e2e: 76s, winner
0.9250@727 (metric −0.6pt = designed noise-divorce); MY grid check: v3
strokes evener than v2, toes rounder, closing on Recraft.
NEW BUG surfaced by validation: shield/pizza/badge emissions have deep-zoom
hairlines BEFORE refinement (integrity 0.1-0.8; elephant/rabbit 1.0) —
contradicts coincidence-by-construction; agent hunting root cause
(suspects: split_paths grouping, dropped directed edges in region_loops,
non-square viewBox).

## 2026-07-07 · Canvas-frame hairline bug FIXED (agent root-cause + patch)

The shared-boundary guarantee only covers INTERIOR edges — canvas-frame
edges (vs outside label -1) are single-coverage, and smoothing rounds canvas
corners / fit_open bows ~tol across 90° corners → real hairlines at the
frame. FIX: border edges bypass smoothing/fitting entirely, emitted as exact
line-cubics (one per straight run). SECOND bug: structcheck itself had an
aspect-rounding measurement artifact (root width/height vs viewBox → 0.4px
global shift = fake hairline row); fixed by rewriting dims to the raster.
Verified: shield 0.832→1.000, elephant/rabbit 0.727→1.000 (they had it too,
just less), badge 0.127→0.832 (residual = near-threshold AA noise), pizza
0.216→0.526 (residual = THIRD bug: thin regions evert under win-9 smoothing
— opposite edges cross; 1.000 at smooth_win=0; backlogged). Also noted:
resnap_refined has the same latent frame exposure if ever reused.

## 2026-07-07 · v4 — vision-first line/fill idealization (goal-directed)

Direct attack on the user's "<70% of Recraft" verdict, judged by eye at zoom:
- Parsimony-fitted SHADING boundaries (fill_parsimony=1.0, fill_smooth=0 in
  contour_lines): shading regions now read as flat idealized shapes with
  wobble-free edges — the fill/shading gap, not just lines. Beat Schneider
  fills by eye (fill_grid.png) at 918 pts.
- Line weight width_scale=0.85 default: tracks Recraft's line weight (Recraft's
  lines are boldish; ws1.0 was a touch heavy, 0.72 too thin).
- Exposed width_scale + fill_parsimony as contour_lines Params.
VERDICT (final_full.png full-frame, final_zoom.png deep-zoom, vs recraft):
lines uniform+confident, fills clean flat shapes — now in Recraft's quality
tier. Three cited defects (wobble / width-thinning / shadows-over-lines) all
resolved. Residual gap = subtle palette/shading-color choices (Recraft's
softer blue-gray tints) + occasional shading-shape simplification, NOT
structural line/fill quality. models/v4 snapshot committed.
Remaining backlog for parity: palette idealization (match Recraft's shading
tints / merge to fewer cleaner shading shapes); line-consistency judge so the
tournament PICKS these idealized candidates (metric still underrates them,
so contour_lines must be run directly rather than auto-selected).

## 2026-07-07 · PAUSED — handoff (see docs/RESUME.md)

User paused the work to resume next week. Confirmed the contour_lines output
(the direct command) is "very good" and fast. Fresh defect report to attack
next (now top of BACKLOG + detailed in RESUME.md):
1. Perpendicular stroke crossings leave GAPS (caps stop short of intersection).
2. Some line curvatures differ from the original (centerline smoothing/fit).
3. Rectangular nub artifacts where strokes join (butt caps / segment seams).
All three are stroke-layer issues in contours_exp.py / strokes.py. After them:
palette idealization (Recraft's softer shading tints) is the last quality gap.
State snapshot: v4 (git c463914), docs/RESUME.md is the single start-here doc.
