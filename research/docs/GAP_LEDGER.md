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

## OPEN (ranked by user priority + eye-loudness)

0a. **REOPENED — heart/string OVER-MERGE (user re-verdict 2026-07-09):** at
   1024 viewing scale the heart still reads blob-ish: the run-35 cusp descent
   deepened the notch only at extreme zoom, and the STRING + heart-top
   outlines still weld into one thick mass. User's diagnosis stands: two
   near-parallel line edges at a stiff angle are being merged/smoothed when
   they must stay separate. The run-34 color guard can't help (same ink
   color) — this is GEOMETRIC over-merge in the stroke network (junction
   pooling / absorb / smoothing at the strap-heart meeting). Evidence:
   models/v5/outputs/user_heart_check.png.
0b. **Thin PARALLEL lines merged or dropped (user 2026-07-09):** chopchop
   chair strut has a red-brown pinstripe running parallel to the black edge
   with clear spacing — OURS DROPS IT ENTIRELY; Recraft keeps it. Same
   family: closely-spaced parallel thin lines get absorbed into one stroke
   or routed to fill and dissolved. Culprit suspects: label chain merging
   the thin colored stripe into the neighboring label (palette merge dE-12?
   despeckle?), or stroke extractor absorbing it. Staged strip needed.
   Evidence: models/v5/outputs/user_parallel_chop.png.
0c. **Detail-vs-noise INVERSION (user 2026-07-09):** meaningful details
   (pinstripe, hole ring) get deleted while BLUR-NOISE SHADES from the
   source (gray daubs on the strut, jagged halo fringes at body edges) get
   rendered. The despeckle/dissolve floor is size-based, not intent-based —
   drawn details are often SMALLER than noise patches. Needs an
   intent-vs-noise discriminator (contrast? edge sharpness? hue distance?).
0d. **PERFORMANCE regression v5→v8 (user 2026-07-09):** rabbit 10.2→31.4s
   (3.1×), chopchop 27.3→298.5s (10.9×!). Suspects: run-35 straight-chain
   lock / cusp descent (per-branch SVD + skeleton passes), run-34 join gate
   bookkeeping, run-25 lock (distance transforms). Profile per stage; the
   visual output must stay byte-identical (or eye-verified neutral) while
   the time comes down to ~v5 levels.
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
