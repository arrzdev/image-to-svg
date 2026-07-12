# GAP LEDGER — the road to Recraft (then past it)

> **Framing (USER, 2026-07-08): we must first REACH Recraft's state before we can
> go past it.** This ledger is the scoreboard: every named, eye-visible way our
> output is WORSE than Recraft, with its suspected culprit stage. An iteration's
> job is to close ledger items with before/after grid evidence. New defects found
> during verification get ADDED here (with the culprit-pause analysis, see
> autoresearch.md "Culprit protocol"). Item closed = grid shows ours ≈/≥ recraft
> at that spot, entry moves to CLOSED with the run number.
>
> Numeric direction gauge: `research/tools/recraft_gap.py [target] --spots`
> (rSSIM / rΔE / worst tiles → mandatory eye-spots). Numbers never close an item
> — the grid does.

> **AUDIT 24 REFRAME (2026-07-09, USER-triggered):** full-set eye audit at HEAD
> found the plateau's causes: items were closed at *better-than-before*, not
> *≈Recraft* (monster teeth "closed" runs 21-22 are still blunt/uneven at zoom);
> verdicts happened at too-low zoom; and 40 runs of local gates patched symptoms
> of 8 recurring ROOT causes (E1-E8). Authority docs now:
> `research/docs/VISION.md` (the blueprint + absolute bar) and
> `research/audit24/FINDINGS.md` (root causes E1-E8, process failures P1-P4,
> campaign skeleton). New items below get filed against E-numbers; closing any
> item requires the zoomed grid to show ≈Recraft, and flat-art targets get the
> DEEPEST zoom.

## OPEN (ranked by user priority + eye-loudness)

0k. **monster teeth + straight-line intent — HAND+KINK CLOSED run 55, TEETH
   residual reattributed:** it24 B-lineintent (anchor-span ruler pinning +
   raster-gated G1 repair, capsule + fill layers): hand/body hairlines now
   straight with sharp kinks ≈ recraft (orchestrator-verified,
   verifyB2_hand.png); fitter-minted head kink killed; teeth now crisp
   zigzag vs scallops BUT residual unevenness is the LABEL LATTICE (E5/
   quantize — staged-strip evidence in B's REPORT), not geometry; mouth-seam
   white curls = capsule rescue gates on lip AA → 0h family. Remaining for
   full close: teeth lattice regularity (E5) + mouth seam (0h/it25).
   Original entry (USER 2026-07-09, audit 24):** HEAD teeth blunt/uneven/wavy-baseline vs Recraft's crisp
   regular zigzag (runs 21-22 closed on a relative bar — postmortem P1); the
   straight hand/body separation lines are rendered as wavy S-curves; head
   silhouette has a flat-cut kink; mouth/head hairline seam (0h family).
   2-color 5-path flat input = zero quantize confound → pure geometry-stage
   damage (smoothing + fit can't see line intent). Root cause E4/E5.
   Evidence: research/audit24/grids/monster_{mouth,hand}_zoom.png,
   monster_mouth_regression.png (it15 vs HEAD vs recraft).

0h. **ANTI-ALIAS SEAMS / thin white pixel borders between colors (USER
   2026-07-09):** boundaries between adjacent fills show hairline light
   borders at all zooms — adjacent paths share an edge but each AA-blends
   against the (white) background instead of each other → sub-pixel seam.
   Matches the old "deep-zoom hairlines on shield/pizza/logo_badge
   shared-boundary emissions" bug (BACKLOG "Bugs to chase") — now USER-visible
   generally. Fix directions: slight overlap of lower layers under upper
   (paint-order-aware dilation of underpaint), or seam-covering boundary
   strokes. Needs a dedicated diagnosis pass on the emission layer. [it24]
   **DIAGNOSED run 45:** structcheck census — ours has coincident seams on
   ALL 18 targets (30-87 px/kboundary); RECRAFT is overlap-sealed on 7/10
   (seam=0; monster uses holes; their chopchop even tolerates deep-zoom
   gaps — the bar is normal-zoom). Same-color seal-stroke PoC kills the
   seam class (84→0.7) and fixes the monster eye smudge by eye
   (audit24/grids/seam_poc_monster.png), but shifts thin-feature widths →
   ship-grade fix = underpaint dilation in paint order, i.e. E8 layered
   emission. 0h and E8 are ONE candidate. [it25]
   **CLOSED run 63 (it25 C-layeremit):** per-shape single-subpath paths in
   painter's order (holes dropped = nested seams sealed by repaint) +
   sibling-seam underpaint strokes. Seams 28-87→0 on ALL 18 targets;
   width landmines byte-identical; degsuite improves. Residual culprit
   notes: monster right-eye gray AA label escapes _own_transitions (E1
   residual, quantize); shield rivet red ball renders tan (0g family).
0l. ~~**Open GAPS = E1 shrapnel slivers**~~ — CLOSED run 54 (it24 A-transown
   transition-ownership: app-asset integrity .412→.988, mountain .488→1.000,
   both eye-verified incl the mountain surprise win). Residual: A's honest
   negative — the HIGH-CONTRAST shrapnel subclass (pizza gray dashes, fox
   in-ink pale debris, shield boss flecks = accent-guard false rescues) is
   NOT color-separable (populations overlap rabbit cheek fluff); needs a
   geometry signal (inside-ribbon vs along-ribbon) or E8 layering. → BACKLOG.
   Original entry: (culprit CORRECTED run 47):** app-asset
   integrity 0.412, mountain 0.488 — TRUE open gaps, but the flatten
   hypothesis was REFUTED by toggle (gradflat=0: app-asset only .412→.484,
   mountain byte-identical — flatten never fired there). Gap pixels
   localize to 2-3 interior clusters (app-asset (0.46,0.80) = the phone-edge
   shrapnel zone; mountain (0.48,0.23) = peak fragment patches): torn
   micro-labels don't tile the plane, leaving exposed-background slivers.
   0l is E1's geometric fingerprint → folds into A-transown's acceptance:
   A's fix should drive app-asset/mountain integrity → ~1.0 (verify on
   integration). Evidence: z_0l_appasset_gap.png, z_0l_mountain_gap.png.
0i. ~~**Monster mouth mangled**~~ — REGRESSION (run 37) FIXED run 38.
   POSTMORTEM (process): the sharpen deformed flat art; the candidate agent
   called monster "lateral" (false), and orchestrator verification only
   re-eyed hero + claimed-regression spots — the focus target was never
   re-eyed. USER caught it from the output. Protocol hardened ("Iteration
   lifecycle" step 3): focus target + all user-flagged targets get
   orchestrator full-grid re-eyes on EVERY integration. Fix itself:
   imgstats flat-art skip, byte-verified both directions.
0j. **Boundary separation losses (USER 2026-07-09, rabbit evidence):** lines
   that exist in the original are dropped or merged with neighbors so object
   boundaries vanish — e.g. the bunny's hand not separated from the
   vegetables it holds (left side); outline lines simply not rendered. Same
   family as 0a (heart/string weld) + 0b (parallel pinstripe drop): the
   engine destroys drawn boundaries between adjacent same-ink or similar-color
   objects. Needs the staged-diagnosis pass that 0a/0b are queued for —
   treat 0a/0b/0j as ONE it24 diagnosis campaign on "boundary integrity".


0f. ~~**GRADIENT BACKGROUNDS must FLATTEN to solid**~~ — CLOSED run 40 (see commit; residual leads: sub-4%-area drop-shadows, mountain hillside fragmentation, faint flatten-seam on shield). Original entry: (USER evidence 2026-07-09,
   app-asset ours-vs-recraft pair):** our engine quantizes smooth radial/linear
   gradients into 2-3 labels whose boundaries render as RAGGED BLOB RINGS
   (app-asset bg ring around the phone — v9-confirmed; same root as the
   mountain/shield banding trade and much of ledger 0c noise). Recraft
   AVERAGES the gradient region into ONE flat solid — correct for SVG
   (gradients are anti-vector unless thousands of paths). Fix direction:
   detect large smooth-gradient REGIONS (region-wise — the failed run-37
   per-image gate stats DO separate regions) and pre-flatten to mean color
   before quantize. Papers: LIVE's layer thinking; Diffusion Curves/Gradient
   Meshes exist for true gradient fills but are out of scope vs flat-solid.
   Evidence: it23_appasset_full.png. [it23-A]
0g. ~~**Small-shape geometric fidelity**~~ — CLOSED run 39 (chromatic-mark rescue; over-rounding exonerated — was glyph loss + 0f raggedness; leads: straight-run pinning needs circle-fit gate; 'e'-shadow weld pre-existing). Original entry: (USER 2026-07-09):** app icons (rounded
   squares) get OVER-ROUNDED into distorted blobs; the mail icon loses its
   envelope glyph; "Share" still renders "Sha e" in v9 (run-37 restore claim
   only partial — honest correction). Straight edges of small shapes must
   stay straight (recraft does); glyph parts must survive. Culprit suspects:
   parsimony fit on short edges (straight-piece prior has len>=20px floor —
   icon edges are shorter), despeckle floors eating glyph parts, corner
   detector k=6 too coarse at icon scale. [it23-B]


0a. **REOPENED — heart/string OVER-MERGE (user re-verdict 2026-07-09):** at
   1024 viewing scale the heart still reads blob-ish: the run-35 cusp descent
   deepened the notch only at extreme zoom, and the STRING + heart-top
   outlines still weld into one thick mass. User's diagnosis stands: two
   near-parallel line edges at a stiff angle are being merged/smoothed when
   they must stay separate. The run-34 color guard can't help (same ink
   color) — this is GEOMETRIC over-merge in the stroke network (junction
   pooling / absorb / smoothing at the strap-heart meeting). Evidence:
   models/v5/outputs/user_heart_check.png.
0b. **Thin PARALLEL lines merged or dropped — LABEL CHAIN EXONERATED
   (staged probe run 58):** chopchop's maroon strut pinstripe keeps its own
   dark-maroon label (centroid 51,33,16) at 100% share through the ENTIRE
   chain (quantize→consolidate→own_transitions→despeckle→smooth→dissolve;
   research/audit24/stripe_probe.py). Culprit narrowed to STROKE
   ROUTING/EXTRACTION: centroid lum≈36 < 60 → ink-class (two-tier gate) →
   stroke-ified, then absorbed by the parallel heavy black edge in the
   stroke network (skeleton/junction pooling or ribbon overlap — the run-34
   color-guard only guards JOIN sites; RGB dist maroon↔black ≈60 would
   refuse a weld, so absorption happens earlier: skeleton or coverage).
   it26 first step: stroke-layer-only strip at the strut to see whether a
   maroon stroke exists pre-network-merge. Original evidence:
   models/v5/outputs/user_parallel_chop.png (recraft keeps the stripe).
0c. **Detail-vs-noise INVERSION (user 2026-07-09):** meaningful details
   (pinstripe, hole ring) get deleted while BLUR-NOISE SHADES from the
   source (gray daubs on the strut, jagged halo fringes at body edges) get
   rendered. The despeckle/dissolve floor is size-based, not intent-based —
   drawn details are often SMALLER than noise patches. Needs an
   intent-vs-noise discriminator (contrast? edge sharpness? hue distance?).
0d. ~~**PERFORMANCE regression v5→v8**~~ — CLOSED run 36 (same day): 88% was
   r35 cusp-descent's argwhere rescan (275s of 311s), NOT the listed
   suspects (join scans measured <1s). Caching + padded-bbox locality;
   output byte-identical 18/18. chopchop 298→7.4s, rabbit 31→3.5s — v8 now
   FASTER than v5. Residual lead: files-pile 18.3s (different cost shape).
0e. **VALIDATED LEAD — sharpen prepass (user idea, tested 2026-07-09):**
   upscale 3× → unsharp (amount 1.6, r≈3) → downscale, then vectorize.
   Kills the strut noise daubs + flattens the heart fill (highlight rim
   appears, matching original). Does NOT restore dropped details. Needs:
   productionize as a pipeline pre-stage, tune (amount/radius/up), broaden
   across all 16 targets for regressions (thin details could sharpen into
   stroke-ified artifacts). Evidence: user_sharpen_{heart,chop}.png.


1. **chopchop junction tangles — LARGELY CURED run 27** (culprit CORRECTED:
   the tangles were mid-dark BROWN TEXTURE LABELS (lum 64-81, spread 60-82)
   being stroke-ified into squiggle loops, not junction geometry; the chroma
   gate sends them to fills). Residual: verify remaining tangle scope at the
   crown/lattice before staging more junction work; worst tiles now
   (2,3),(1,3),(1,1) at rSSIM .873.
2. ~~**Straight-line waver**~~ — CLOSED runs 25+28+29+35. Final piece (run
   35 straight-chain lock): verticals ruler-straight through crossings; the
   fit's -2.75px tol-band S-bow measured and killed (sagitta bow<=0.4 lock,
   grid lines <=0.26 vs true curves >=0.52). NOTE: run-29's "grid is 100%
   fill-layer" was a flawed probe (missed direct _ribbon import) — the grid
   is 45 ribbon STROKES; run-35 attribution stands. Residual (new item):
   small crossing nubs + one unlocked short horizontal + upper-band cell
   separators lost (label chain, pre-existing).
3. ~~**PIZZA "ZZ" letterforms mangled**~~ — CLOSED run 27: letters (lum~76,
   spread 151) passed dark_lum<96 and were stroke-ified; the two-tier chroma
   gate (lum<60 OR spread<=45) keeps them as fills — ZZA now crisp, ~original.
   (Checker-grid line bows remain = item 2, fitter.)
4. ~~**Heart notch depth**~~ — CLOSED run 35 (junction cusp descent).
   Culprit CORRECTED: not the fill fitter — absorb_mask folds the notch ink
   into the fill (raw fill edge is FLAT); the visible notch is 100%
   stroke-layer and its medial-axis junction sat at the wedge TOP with no
   descending branch. One tangent-aligned extension into the ink pocket
   (gates measured: true cusp .64w vs false pockets >=1.21w) renders the
   deep V ~= original/Recraft.
5. ~~**Over-joining lines**~~ — CLOSED run 34 (it21 B-colorguard, the USER's
   color-guard idea verbatim): RGB dist<=30 gate at all 4 join sites; good
   joins label-identical (0) vs over-joins 51-125. chopchop knot-hole weld,
   leaf detours, fox chin worm, rabbit spur/sleeve welds all gone; protected
   closures intact. New culprit notes: chopchop smile barb = skeleton-fork
   family (not a weld); fox haunch dash chain -> #6.
6. **Small drawn details wiped** — paw fingers back (run 25); rabbit buttons
   ring still opens into hooks (fitter renders solid dark dots as 'u' — it19
   A-darkguard finding); audit remaining sub-3px casualties per target.
   Culprit: split between label cleanup (fixed) and small-blob fitting.
7. **Color accuracy to ORIGINAL** — MEASURED run 32 (vs ORIGINAL, the user's
   rule): rabbit dE 1.90 = FINE (its gauge rdE 4.16 is Recraft deviating from
   the original — do NOT chase it); CRYSTALS dE 3.82 = the real offender,
   centroids drift blue/pink (pink facets R-9/B+14, teal B+12 — the magenta
   shift eyed run 31). Culprit suspect: k-means centroid pull across facet
   shades / shadow merge. Fix idea: anchor final region colors to the
   ORIGINAL region mean (post-assignment re-tint). [next segment]

- **[it66-leads, 2026-07-12] Leech-blob strokes + low-contrast facet residual**
  (from run-66 crystals UNDER-RESOLVE candidate, orchestrator-verified):
  (a) LEECH: thin dark sub-labels that enter the stroke layer render as lumpy
  tapered blobs with wandering width (pizza-box lid crease, new sub-label
  rgb(84,40,23) 67px — orchestrator eye-confirmed worse than prev locally;
  net pizza still −0.0043). Culprit stage: stroke synthesis/width profile on
  short thin fills. Fix shape: width-profile floor or route sub-N-px thin
  labels to constant-width stroke emit.
  (b) crystals red-face interior waves (lbl 35) + blue-face streaks: sub-9ΔE
  tonal families, ONE-CLUSTER at local merge scale — unreachable by the
  structured split (its dE regime starts ~12); needs a _band_split_ramps-style
  local band treatment. [leads for a next iteration]

- **[it69-leads, 2026-07-12] Apex outline warp + stroke-grade mis-toned comps**
  (run-69, orchestrator-verified): (a) crystals apex OUTLINE is warped/locally
  fat where Recraft has a clean uniform bend — fitter/stroke-geometry family,
  dominates the region's residual dE (24.1 vs Recraft 7.5); untouchable by
  color. (b) STROKE-GRADE mis-toned components (tone lum<96) deliberately
  excluded from it69's re-anchor: crystals deep-blue edge strip (L12 comp,
  2454px, dE 18.4, lum 73), shield strap piece — recovering these AS STROKES
  is the direct UNDER-RESOLVE-share lever (adds arc; flips ink<0.35 tiles)
  and pairs naturally with the shipped re-anchor. = run-70 candidate.

- **[it70-leads, 2026-07-13] Thin dark rings quantize INTO their dark parent**
  (run-70 probe, shield rivet-2): the ring's px belong to the maroon BACKGROUND
  label L3 (86k-px dominant comp) + sub-30px L10 fragments — unreachable by the
  re-anchor family (parent gate + area both correctly locked). Recraft draws a
  clean maroon ring/shadow. Culprit stage: quantize/label-chain ownership of
  thin dark-on-dark boundaries. Named fix shape: extend _resnap_fill_boundaries
  to dark/dark boundaries, or a ring-aware carve (thin annulus whose source
  tone differs from parent interior). TRUE arc-adder (UR lever). = run-71
  candidate. Also: strap texture streaks (label-chain shrapnel family) persist.

- **[it71-leads, 2026-07-13] Partial-streak completion + ring-closure prior**
  (run-71, mechanism verified, stashed as rider): (a) thin details whose OTHER
  HALF is already drawn (mountain long streak, fox whisker (360,397), fox
  corner shadow (372,203), rabbit crescent (761,657)) — missing fragments are
  blend-adjacent or hug big comps; right shape = label EXTENSION (grow an
  existing thin label into its off-tone continuation), not minting. (b) all 4
  shield rivets now have arcs; Recraft draws FULL circles — a fit-stage
  closed-ring completion for annular fills would close the class. (c) probe
  process rule: label attributions in ledger entries must name label id AND
  center rgb+lum (run-70's "L3 maroon background" misread cost a probe cycle).

- **[it72-leads, 2026-07-13] FITTER diagnosis: 3 leads = 2 stages + 1 routing**
  (stage-strip verified, research/it72/candidates/fitter-bends/):
  (a) **SHAPE-GATE ROUTING = the bar-scale lead (run-73)**: line NETWORKS
  fill-routed because band exemption needs p25r>=0.8 — crystals apex outline
  (label 8, rgb(26,64,82), 4803px, elong 134, p25r 0.71) AND rabbit's whole
  2.83px ink network (elong 840) render as independently-fitted glyph fills:
  label-map wobble faithfully reproduced, width idealization unreachable.
  Flip criterion must exclude fox 115k-px body silhouette (elong 870, cov
  1.33 OVERLAPS the class) + monster 200k silhouette + mountain ridge chunks
  (p25r .75-.78). Population table in it72 artifacts README.
  (b) bend-radius INFLATION: pizza box corners are drawn small-radius ARCS
  (k6-turn 11-62deg, localization fails) — corner pinning can't reach; win-11
  pre-fit smoothing + ribbon re-smooth + fit tolerance inflate the radius;
  needs curvature-adaptive smoothing. (c) elephant has ZERO stroke chains
  (purple ink lum 68 spread 84 fails near-neutral rule; renders via fills —
  scores fine, note only). (d) METRIC FLOOR pattern: it70 +0.0002 / it71
  +0.0004 / it72 +0.0006 all verified-safe eye-loud wins 2.5-7x under
  MIN_GAIN — tilecmp@40 dilutes 1-3px quality; riders accumulate (pool
  +0.0012); if run-73 (bar-scale) also lands sub-bar, surface the regime
  question to USER.

- **[it73-leads, 2026-07-13] Junction emission for stroked networks + metric-floor CASE 4**
  (run-73): (a) junction-pool emission is the remaining defect of stroke-routed
  networks (apex-shoulder S-curl + pinhole: pools <1.9x med_w evade blob split;
  _prune_and_merge merges pool spurs into fake through-branches; probes
  rejected plain-stroke semantics + blob_factor 1.5 with data). (b) rabbit ink
  network is ALREADY stroke-routed at this HEAD — it72's table was read at a
  different stage; always re-verify routing AT HEAD. (c) METRIC-FLOOR CASE 4:
  eye-better/metric-negative (−0.0001) — tilecmp junction tiles penalize the
  new stroke topology the eye prefers. Regime question formally OPEN for USER.

- **[it75-leads, 2026-07-13] Post-pen-calibration families**: (a) RIBBON
  DOUBLE-SCALE BUG (found, not fixed): ribbon baselines emit at width_scale^2
  (w_body carries width_scale, then prof*width_scale/2 re-applies) — varying-
  width chains are extra-thin at 0.72x gw. A real bug; fixing changes unfired
  stems -> its own gated candidate = run-76. (b) far-missing dark lines
  (chopchop slat dividers quantized into wood fills, 4.8% of source ink,
  oracle 0.1618): label-chain ownership family, sibling of it67/it71.
  (c) pizza pinch sites: separator pairs converge near corners — FITTER
  geometry that thin pens were masking; width can't idealize until the fit
  is fixed. (d) shield lost yellow highlight circle + panel sawtooth
  (batch eye grid row 4): lost-detail + boundary families, untargeted.

## CLOSED

- ~~Monster teeth scalloped/half-height~~ — runs 21+22 compound (tall AND sharp).
- ~~Ribbon-end rectangular nubs~~ — run 23 round caps.
- ~~Heart outline erased → circle~~ — run 25 thin-dark-line lock (notch depth
  residual tracked as item 4).
- ~~Paw finger lines wiped~~ — run 25 (same lock).
- ~~Pizza straight edges fragmented (label-chain share)~~ — run 25 (fitter
  share tracked as item 2).
- ~~Monster scratch beading, apex nubs, sliver lumps~~ — runs 15/16/19.
- ~~Rabbit heart outline gaps~~ — runs 15/20 bridges.

## Per-target recraft_gap baseline (run 24, HEAD a8d728d)

chopchop .868/2.82 · crystals .890/3.80 · fox .915/3.24 · rabbit .947/4.18 ·
mountain .963/1.99 · elephant .970/1.12 · logo-geometric .988/0.56 ·
monster .989/0.29 — re-measure per keep; falling rSSIM on an untouched target
is a spot-finder alarm.
