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

1. **chopchop junction tangles — LARGELY CURED run 27** (culprit CORRECTED:
   the tangles were mid-dark BROWN TEXTURE LABELS (lum 64-81, spread 60-82)
   being stroke-ified into squiggle loops, not junction geometry; the chroma
   gate sends them to fills). Residual: verify remaining tangle scope at the
   crown/lattice before staging more junction work; worst tiles now
   (2,3),(1,3),(1,1) at rSSIM .873.
2. **Straight-line waver residual (fitter share)** — pizza-box edges improved by
   run 25 (label-chain share fixed) but the fitter still has no straightness
   prior; long straights need line fits, not bezier chains. Culprit: fill/stroke
   fit (contours_exp.py smooth+Schneider / parsimony path). [it20 A-linefit]
3. ~~**PIZZA "ZZ" letterforms mangled**~~ — CLOSED run 27: letters (lum~76,
   spread 151) passed dark_lum<96 and were stroke-ified; the two-tier chroma
   gate (lum<60 OR spread<=45) keeps them as fills — ZZA now crisp, ~original.
   (Checker-grid line bows remain = item 2, fitter.)
4. **Heart notch depth** — notch restored (run 25) but shallower than
   original/Recraft; concave-cusp handling in the fitter rounds it. Culprit:
   fill fit (concave cusps unpinned — it18 corner-pin is convex-only in
   effect). [it20 A-linefit]
5. **Over-joining lines that shouldn't connect** — bridge/chord/extension chain
   (runs 3,4,15,20) joins across color/region breaks. USER fix idea:
   color-guarded joining (refuse a join when color breaks across the chord).
   Culprit: bridging gates lack a color-consistency test. [queued it21]
6. **Small drawn details wiped** — paw fingers back (run 25); rabbit buttons
   ring still opens into hooks (fitter renders solid dark dots as 'u' — it19
   A-darkguard finding); audit remaining sub-3px casualties per target.
   Culprit: split between label cleanup (fixed) and small-blob fitting.
7. **Color accuracy to ORIGINAL** — we should match the source's colors, not
   Recraft's palette; rabbit rΔE 4.18 is the worst color gap. Culprit:
   quantize centroid drift + shadow-tone merges. [it20 B-localcolor, re-scoped]

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
