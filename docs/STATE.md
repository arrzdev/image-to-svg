# Engine state

_Last updated: 2026-07-07, loop after user's visual critique._

## What the engine is

Tournament architecture: analyze image → generate candidate portfolio
(pipelines × configs) → score all in parallel (composite perceptual metric +
λ·log10(points) complexity penalty) → refine finalists → integrity-check →
best SVG wins. Modes: `fidelity / balanced / editable / grail / fast`
(`backend/convert.py --mode …`).

## Core technology (newest first)

- **Shared-boundary vectorization** (`backend/boundary.py`,
  `pipelines/shared_boundary.py`): label-map boundary graph; every edge
  smoothed + Schneider-fitted ONCE (Rust `svgcore.fit_open`); both adjacent
  regions reuse the identical cubics (cubic reversal is exact) → gaps/spurs
  impossible by construction. Pre-fit moving-average smoothing (`smooth_win`),
  edge-support dissolve (`dissolve`), per-element path emission
  (`boundary_split.py`, default on).
- **Shared-edge differentiable refinement** (`refine_shared_v2.py`): DiffVG
  reparameterized as one tensor per edge + one per junction; region paths
  rebuilt by differentiable concat each iteration → region-overlap cheating
  inexpressible. Staged 256@2x2 → 512@1x1 + Polyak tail averaging (~3x
  speedup); fill-color optimization in a final full-res 2x2 stage (low-res
  color gradients are dishonest — fills absorb AA error).
- **Structural integrity judge** (`structcheck.py`): alpha-plane analysis of
  a 4096px transparent render; hairlines/gaps score ~0.06, clean coincident
  boundaries ~1.0. Grail objective subtracts `0.08·(1−score)` for top-6.
- **Centerline strokes** (`strokes.py`, `pipelines/stroke_hybrid.py`):
  medial-axis skeleton → true SVG strokes / variable-width ribbons for thin
  dark line art; clean tapered tips. Fielded as `sb-strokes`/`grail-strokes`.
- **Quality metric** (`metrics.py`): geometric mean of MS-SSIM, CIEDE2000,
  GMSD, worst-region ΔE p99.5, × coherence^0.10. **Known blind spots:** can't
  see subpixel boundary damage (fixed via structcheck) and REWARDS copying
  source noise (see "The visual gap" below — the current research focus).

## Benchmark state (for reference, NOT the objective)

- Elephant vs Recraft reference: winner 0.9317 @ 727 pts; compact 0.9246 @
  679 pts (< Recraft's 690 @ 0.9103); max-fidelity 0.9390 @ 1,337. All
  integrity 1.0. Grail ~2-5 min, fast ~6-15 s.
- SVG-Bench: best published SSIM all 3 splits (emoji 0.9642, icons 0.9858,
  fonts 0.9907).
- Library: grail 16/16 mean q 0.9442 @ 97s/img; fast 17/17 mean 14.7s.

## The visual gap (USER VERDICT — current focus)

Despite the numbers, the user judges our output "<70% of Recraft quality"
visually. Defects to fix, in their words:

1. **Wobbly, inconsistent lines** — the character's contours are clean
   digital lines; ours wobble.
2. **Line width thins where it shouldn't.**
3. **Source shadows render on top of drawing lines** — an artifact of
   quantize partitioning; never present in the original style.
4. Fast mode shows all of this worst.

Root cause: the metric optimizes similarity to the SOURCE RASTER, which
contains noise/JPEG artifacts/soft shading. Recraft **idealizes** — output is
a cleaned, digital-looking interpretation. Similarity ≠ quality.

**Judging protocol from now on: grid-crop vision comparisons (ours vs Recraft
vs ORIGINAL) at multiple zooms. Benchmarks are sanity checks only.**

## Key files

| File | Role |
|---|---|
| `backend/engine.py` | tournament, portfolios, DV targeting, integrity pass |
| `backend/boundary.py` | boundary graph, smoothing, dissolve, curve emission |
| `backend/boundary_split.py` | per-element path emission |
| `backend/refine_shared_v2.py` | shared-edge DV (fast, colors) |
| `backend/structcheck.py` | deep-zoom integrity score |
| `backend/strokes.py` | centerline stroke extraction |
| `backend/metrics.py` | perceptual quality metric |
| `backend/testbed.py` | disk-cached experiment harness (see RESEARCH_LOG) |
| `docs/RESEARCH_LOG.md` | loop-by-loop journal |
| `docs/BACKLOG.md` | idea queue |
