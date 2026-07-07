# image → svg playground

> **External benchmark ([SVG-Bench](https://arxiv.org/abs/2312.11556), CPU, 1.6s/image):**
> - **SVG-Emoji** (full 668-sample test set): **MSE 0.00201 / SSIM 0.9642** —
>   best SSIM and tied-best MSE vs every method in the StarVector paper's
>   table (LIVE: 0.002/0.958 at ~10 min/image; StarVector-8B 0.052/0.829).
> - **SVG-Icons** (500 samples): MSE 0.0049 / SSIM 0.9695 — top tier
>   (Potrace/LIVE 0.004/0.973, StarVector-8B 0.012/0.975) at 375× LIVE's speed.
> - **SVG-Fonts** (300 samples): MSE 0.0040 / SSIM 0.9748 — top tier
>   (Potrace 0.002/0.988, LIVE 0.001/0.977, AutoTrace 0.006/0.968).
>
> Protocol: ground-truth SVGs rasterized at 256px over white, converted via
> `tournament(mode="balanced")`, outputs re-rendered at 256px and compared —
> matching StarVector's own harness (cairosvg, white bg, square 224/256px,
> skimage SSIM) except for the rasterizer (resvg vs cairosvg, measured drift
> ≤0.0003).

A local playground for testing hypotheses on turning raster images (especially
**logos / flat illustrations**) into high-quality, editable SVGs. Drop in an
image, run it through several vectorization pipelines at once, and compare the
results **side-by-side with hard metrics** (fidelity + complexity).

![montage](outputs/montage.png)

## Why

Eyeballing one tracer's output tells you little. This harness renders every
pipeline's SVG back to a raster and scores it against the source, so you can
actually *measure* which approach + parameters win for a given image:

- **SSIM / PSNR** — how faithfully the SVG reproduces the image
- **paths / points** — how simple/editable the result is
- **gzip size** — real transfer weight
- **time** — cost per pipeline

## The grail stack (Recraft-class output)

`shared-boundary vectorization → per-edge curve fitting → DiffVG refinement`
reaches the professional fidelity/simplicity corner. On `samples/elephant.jpg`
vs Recraft's own conversion (`data/targets/elephant.svg`):

| | ours (grail winner) | ours (most compact) | ours `--mode fast` (~6s) | Recraft (~3-4s) |
|---|---|---|---|---|
| quality (our metric) | **0.9312** | 0.9246 | 0.9151 | 0.9103 |
| local fidelity | **0.657** | 0.629 | 0.610 | 0.596 |
| points | 727 | **679** | 1,337 | 690 |
| per-element paths | yes (split emission) | yes | yes (62) | yes (67) |
| gaps/overlaps/spurs at deep zoom | **zero, by construction** (integrity 1.0) | **zero** | **zero** | zero |

Both grail columns beat Recraft on every fidelity axis — the compact one with
*fewer* points than Recraft's own output. Refinement runs in the shared-edge
parameterization (`refine_shared_v2.py`): one tensor per boundary edge + one
per junction, region paths rebuilt by differentiable concatenation, so the
optimizer *cannot* express the region-overlap cheat that plain per-path DiffVG
uses to fake quality while opening deep-zoom hairlines. A structural-integrity
judge (`structcheck.py`, alpha-plane analysis of a 4096px render) scores every
grail finalist, so structurally damaged candidates lose on merit. Thin line
art can additionally be modeled as true centerline strokes (`stroke_hybrid`
pipeline) — clean tapered tips instead of notched outline blobs.

The structural key is **shared-boundary vectorization** (`backend/boundary.py`):
instead of tracing each region independently (which fits every boundary twice —
the two fits never coincide, so every boundary is a potential hairline gap and
every junction grows spurs), the label map's boundary GRAPH is extracted
(junction nodes + edges between region pairs), each edge polyline is smoothed
(staircase-noise removal, junctions pinned) and Schneider-fitted **once** in
Rust, and every region is rebuilt from the shared cubics — a cubic Bézier
reverses exactly, so both neighbors reuse the identical curve chain.
Coincidence is guaranteed by construction, and exact reconstruction was
verified at 100.000% pixel agreement. Upstream, the **flat-partition label
cleanup** in `quantize_contours` (halo absorption, despeckle, mode-smoothing)
still produces the solid one-region-per-element partition.

Powered by **`svgcore`** — a Rust extension (`svgcore/`, build with
`maturin develop --release`) housing the hot geometry: path parsing, DP,
Schneider least-squares cubic fitting. Matches the Python reference quality at
23 % fewer points and **345×** the speed (22ms vs 7.6s), which un-rejected
Schneider and made it the default simplify method and the `schneider`
smoothing mode in `quantize_contours`.

## Quick start: convert an image

```bash
python backend/convert.py input.png                       # balanced mode
python backend/convert.py input.png --mode grail          # Recraft-class: solid
                                                          # containers, ~1k pts, DV-refined
python backend/convert.py input.png --mode fast           # grail structure in ~6s
                                                          # (no DV; gap-free guarantee intact)
python backend/convert.py input.png -o out.svg --mode fidelity --dv
python backend/convert.py samples/*.jpg --mode editable   # batch
```

`--mode grail` fields two families — shared-boundary curves (several smoothing
windows) and flat-partition + Schneider (multiple deterministic k-means draws)
— plus a non-posterize safety net, DV-refines the champion of EACH family, and
ranks with λ=0.07. `--mode fast` is the shared-boundary family without DV:
~6s per image, and on gradient/texture content it degrades honestly to a
fidelity trace (every flat-color candidate collapses together on such content,
so the safety net must be a different species). Definitive library results (16/16,
min 0.847, mean 0.926, fully deterministic and seed-robust):

| content class | result |
|---|---|
| logos (4) | q 0.982–0.993 @ **46–90 pts / ≤1KB** |
| flat / line-art (8) | q 0.847–0.935 @ **793–3.2k pts / 13–53KB**, solid containers (elephant 1,060 pts/19KB beats Recraft's 0.910; pizza box 793 pts) |
| gradient / texture (4) | honest fidelity fallback, q 0.913–0.953 |

One command per image: analyze → tournament → optional DiffVG refinement →
lossless optimization → winner written next to the input (or `-o`).

## The tournament engine (recommended entry point)

`backend/engine.py` — one call, many candidates, best SVG wins:

1. **Analyze** the image (palette size, edge density, line-pixel fraction → flat / lineart / detailed)
2. **Generate** an adaptive candidate portfolio (pipelines × posterize/simplify/resolution variants)
3. **Score** every candidate in parallel with the composite metric
4. optionally **Refine** the winner via short coordinate ascent (`--refine`)
5. Emit winner + leaderboard + a labeled **contact sheet** PNG for visual review

```bash
python backend/engine.py elephant.jpg --mode editable      # ~15-20s
python backend/engine.py mountain.jpg --mode fidelity --refine
```

Also in the UI: **🏆 Tournament** button (`POST /api/tournament`) — renders the
ranked leaderboard as cards. Measured: badge logo (flat) → 905 pts / 5KB @
q=0.955 in 4s; mountain (fidelity) → q=0.9687 with posterize variants correctly
rejected for deleting sky detail. The metric guides, the contact sheet lets
eyes verify.

**Baseline (all 16 samples, balanced mode):** 16/16 pass — flat logos
0.974–0.983 (~1.6s each), line-art/cartoons 0.909–0.969 (8–37s), all winners
coherence ≥ 0.97. Winners are *diverse* per image (simplify variants,
posterize, potrace, raw fidelity) — no single config dominates, which is the
point of the tournament. `outputs/batch_tournament.json` + per-image
`batch_*.png` contact sheets hold the full record.

## Scoring & the optimization loop

The headline number is **`quality`** ∈ [0,1] — a weighted **geometric** mean of
three perceptual components, each catching a different failure mode
(`backend/metrics.py`):

| component | metric | catches |
|-----------|--------|---------|
| **structure** | MS-SSIM (multi-scale) | blur, gross shape/layout error |
| **color** | CIEDE2000 ΔE in Lab | wrong/over-quantized hues |
| **edges** | GMSD (gradient similarity) | lost fine detail, faceting |
| **local** | worst-region ΔE (box-filtered p99.5) | **deleted objects** — a missing cloud is ~1% of pixels (invisible to global means) but a whole 32px window of pure error |
| **coherence** | **excess** edge-length loss under median filter vs the source's own (1536px) | **added raggedness** — a line drawn as many little overlapping patches instead of one clean curve. Source-relative so intrinsically detailed content (texture, text) isn't falsely punished |

`local` exists because global averages hide local catastrophes: vtracer at
`color_precision=6` silently merged white clouds/snow into the sky on
`mountain.jpg` and still scored 0.928; with the local component it scores 0.736,
and at `color_precision=8` (now the default — close colors no longer merge) the
content survives and it scores 0.965.

Geometric mean means no component can be hidden: destroy the edges and `quality`
drops even if color is perfect. Every component is exposed individually so the
search can target one. All fidelity metrics are scored against the **original**
(downscaled to `EVAL_DIM`), so lower "Trace at" is honestly penalized.

Because "better" is now a reliable scalar, finding the best method + settings is
just search — `backend/sweep.py`:

```bash
python backend/sweep.py <image-or-sample> --dims 1024,2048 --top 12
python backend/sweep.py beaver.png --lambda 0.02      # penalize complexity
```

It runs pipeline × parameter-grid × resolution, ranks by `quality` (or
`quality − λ·log₁₀(points)` with `--lambda`), prints the leaderboard with the
component breakdown, and writes a full ranked JSON report. Extend the search by
editing `SEARCH_SPACES` in `sweep.py`.

**Per-image auto-optimizer** — parallel coordinate ascent over the FULL knob
space (tracer params + `process_dim` + `simplify_eps`), converging in a few
dozen evaluations where the equivalent grid is thousands of cells:

```bash
python backend/optimize.py fox.jpg                # pure fidelity
python backend/optimize.py fox.jpg --lambda 0.06  # favor editable/compact
```

Also available in the web UI: **Auto-optimize** (section 4) with
fidelity / balanced / editable modes (`POST /api/optimize`). Example: editable
mode on `logo_transparent_lineart.png` auto-found a config producing **301
points / 3.4KB at quality 0.94** — settings no global default would pick.

Each coordinate is line-searched in parallel on the process pool. Measured on
fox.jpg (grid equivalent: 4000 cells): fidelity mode converged in 35 evals
(60s) to q=0.9362; `--lambda 0.06` found a different optimum — q=0.9153 at
**5× fewer points** (36k vs 142k) and 281KB vs 1.3MB. λ is the
fidelity ⇄ editability dial; ~0.06 is a good "editable" setting (0.02 is too
weak to matter).

**Aggregate across a whole folder** — find the config that generalizes best:

```bash
python backend/sweep_all.py --dim 1024 --workers 12 --top 12
```

Ranks every config by *mean* quality over all sample images (plus an
efficiency view that rewards compact SVGs), and reports the per-image winner.

**Rendering speed.** Metric scoring renders every SVG back to pixels. That
renderer is **resvg** (Rust/tiny-skia, `brew install resvg`) when installed —
**12.8× faster than cairosvg** on multi-MB traced SVGs with near-identical
pixels (Δquality ≤ 0.0003) — with automatic cairosvg fallback
(`backend/render.py`). Path counting uses split-based parsing (~5× faster on
big path data). Together: `all_metrics` 2000ms → 822ms on a 4MB SVG.

**Parallelism (queue-workers).** Both sweeps run on a process pool
(`backend/parallel.py`): an internal task queue with N worker processes, each
pulling the next job as it finishes. `--workers N` sets the pool size (default
cores−2). It uses *processes*, not threads, on purpose — profiling showed the
heavy calls (vtracer's Rust binding, cairo, skimage) all hold the GIL, so a
thread pool gave ~1.0× while the process pool gives ~7× on a 14-core machine.
Native libs (OpenCV/BLAS) are pinned to one thread each so the pool owns the
parallelism instead of oversubscribing cores.

## Pipelines (v1, no API needed)

| id | what it does | good for |
|----|--------------|----------|
| `vtracer` | Rust color spline tracer. Clusters color, traces smooth béziers. | strong all-round default |
| `quantize_contours` | K-means color layers → OpenCV contours → Douglas–Peucker → **corner-aware** bézier smoothing. Fully in-process, every knob exposed. | hacking on custom hypotheses |
| `potrace_layers` | Posterize to k colors, trace each layer with Potrace's optimized curves, stack largest-first. | cleanest curves, smallest files |

Each pipeline declares a typed parameter schema; the UI renders sliders/selects
for it automatically. Add a new pipeline by dropping a `Pipeline` subclass in
`backend/pipelines/` and registering it in `backend/pipelines/__init__.py`.

## Processing resolution ("Trace at")

Because SVG is resolution-independent, we **trace a downscaled raster and stamp
the original size back onto the output**. Downscaling with area averaging
anti-aliases away noise/JPEG artifacts (denser pixels = cleaner edges) *and*
makes tracing much faster and simpler — e.g. tracing a 4000px logo at 512px
roughly halves the control-point count versus 1024px.

- The **Trace at** control (Input panel) sets the tracing long-side in px
  (512 … 4096 / original, default **2048**). Applies to **all** pipelines.
- **Small sources are auto-UPSCALED** (Lanczos, capped at 2×) up to the trace
  resolution — **except flat/crisp art**: Lanczos ringing around hard edges
  gets traced as junk (logo_geometric: 145 pts native vs 3,367 pts upscaled),
  so `_prepare` gates upscaling on the image classifier (`imgstats.analyze`).
  For anti-aliased art it clearly helps (fox 0.870 → 0.925); with simplify
  eps=2 the combo beats the native trace on both quality AND size. The eval
  target is never upscaled.
- Each result SVG's root `width`/`height` is set to the **original** dimensions
  while its `viewBox` stays in processing-pixel space, so it renders at full
  resolution and stays infinitely scalable (`backend/svgutil.py`).
- **Metrics are scored against the original** (downscaled to `EVAL_DIM`=1536),
  *not* the trace input. So a low "Trace at" is honestly penalized — the SVG is
  rendered at the eval resolution and compared to the original, revealing the
  faceting/detail loss that a proc-resolution score would hide. Watch SSIM climb
  as you raise "Trace at" and stop when it plateaus.

### The detail ⇄ smoothness tradeoff

Downscaling too far is the main cause of **lost small details** (thin lines,
text, texture) and **faceted rounded curves** — a feature that ends up ~70px in
the trace gets fit with too few control points, and upscaling magnifies every
facet. vtracer's spline fitting is smooth *when given enough resolution*, so for
busy, detailed art (e.g. an 8533px illustration) prefer **2048–4096**. Use lower
values only to deliberately smooth noise or simplify. vtracer defaults were also
loosened for detail (`filter_speckle` 4→2, `length_threshold` 4→2).

## Trace-then-simplify (fidelity → editability)

Instead of asking the tracer to balance fidelity vs editability internally, we
trace at high fidelity and simplify as an explicit post stage
(`backend/postprocess.py`): each path's cubics are sampled, Douglas-Peucker'd
(**Simplify** control, px tolerance), and refit with corner-aware beziers.
Measured on `fox.jpg` (vtracer cp=8 raw = 20.5k pts / 244KB gz):

| eps | quality Δ | points | gzip |
|-----|-----------|--------|------|
| 0.5 | ±0.0000 | −7% | **−34%** |
| 1.0 | −0.0015 | −24% | −50% |
| 2.0 | −0.0074 | −51% | −69% |
| 4.0 | −0.033 | −78% | −85% |

Quality is re-scored *after* simplification, so the cost of each level is
always visible. Default in the UI: 1px.

An alternative Schneider least-squares refit exists
(`simplify_svg(..., method="schneider")`, `backend/schneider.py`): ~23% fewer
points at the same tolerance but slightly lower quality and **12× slower**
(pure-Python recursive fitting) — measured and rejected as default; use only
for point-count-critical exports. A Rust/numba port would be needed to make it
tournament-viable.

## Output optimization (lossless)

Every returned SVG passes through `backend/svgopt.py`: it builds two lossless
variants — (A) translate transforms baked into coordinates + consecutive
same-style paths merged, (B) transforms kept, coordinates rounded — and keeps
whichever **gzips smaller** (surprise finding: vtracer's translate layout with
`M0 0` starts is more gzip-friendly than baked coordinates on path-heavy
files). Measured: raw −23…36 %, gzip −17…37 %, quality drift ≤ 0.004.
Applied in `/api/vectorize` results and tournament winners.

## Handling complex / transparent images

Real cartoon-style art (transparent PNGs, black outlines, many colors) hits two
classic failure modes, both handled:

- **Transparent → black background.** A naive `RGBA→RGB` drops alpha and leaves
  transparent pixels black, which quantizers trace as a giant black shape. The
  backend composites every input over **white** before processing (`_flatten`
  in `backend/app.py`), matching the preview and the metric renderer.
- **White seams between color regions.** Layered tracers trace each color
  independently; adjacent outlines don't quite meet, so white shows through.
  Two knobs fix this on `quantize_contours` and `potrace_layers`:
  - **Gap fill (px)** — dilates each layer so neighbors overlap.
  - **Dark lines on top** — paints dark (outline) colors last, so gap-fill can
    thicken/close seams *without* eroding the line art.
- **Oversized inputs** are capped to 2048px on the long side (`MAX_INPUT_DIM`)
  so per-layer tracing and metric-rendering stay fast; pipelines downscale
  further via their own `max_dim`.

For line-art like this, `vtracer` tends to win on faithfulness; the layered
tracers are best with **gap fill ≥ 1** and **dark lines on top** enabled.
(Dark line layers are never dilated — they're painted last, so gap-fill
dilation would visibly fatten every stroke.)

### Clean single strokes vs noisy patches (line-art)

vtracer clusters colors on the anti-aliased image, so an outline's AA halo
fragments into several thin ragged patches — a line becomes "many little
blocks". The **Posterize first** vtracer param (k-means flatten before tracing,
try 12–20) collapses the halo so each stroke traces as ONE region: on
`elephant.jpg` it cut paths 11,149 → 3,946 and points 133k → 55k with visibly
cleaner strokes. Tradeoff: subtle gradients flatten (the `quality` metric drops
accordingly) — it's the right mode for line-art/cartoons, not photos.

## AI preprocessing (optional — "nano banana")

An optional stage runs the image through **Gemini 2.5 Flash Image**
(`gemini-2.5-flash-image`, ~$0.039/image — the cheap "nano banana", *not* the
pricier "nano banana pro" = `gemini-3-pro-image`) to denoise / flatten /
posterize *before* vectorizing. This tests research approaches #2 and #6
(AI preprocessing + classical vectorization). It's **off unless a key is set**:

```bash
export GEMINI_API_KEY=...            # enables the AI dropdown in the UI
export GEMINI_IMAGE_MODEL=gemini-2.5-flash-image   # default (cheap)
```

Prompt presets live in `backend/ai/gemini.py` (`clean_flatten`, `denoise`,
`posterize`). Because the app measures SSIM against the (AI-modified) input, you
can A/B whether preprocessing actually helps or just hallucinates detail.

## Run

```bash
./run.sh                 # http://127.0.0.1:8000   (PORT=xxxx to change)
```

Requirements are already installed in `.venv`. To rebuild from scratch:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
brew install potrace cairo         # potrace tracer + cairo (SVG→raster for metrics)
.venv/bin/python samples/gen_samples.py   # regenerate sample logos
```

> **macOS/cairo note:** `cairosvg` loads `libcairo` at runtime from
> `/opt/homebrew/lib`. `backend/render.py` adds that to the dyld search path
> automatically, and `run.sh` also exports it — so no manual setup needed.

## Layout

```
backend/
  app.py                 FastAPI: /api/pipelines, /api/vectorize, /api/samples
  metrics.py             SSIM/PSNR + path/point/size counting
  render.py              SVG → RGB (cairosvg) for fidelity scoring
  pipelines/
    base.py              Pipeline + typed Param schema
    vtracer_pipe.py
    quantize_contours.py
    potrace_layers.py
  ai/gemini.py           nano banana preprocessing stage (opt-in)
frontend/                vanilla HTML/CSS/JS single-page UI (no build step)
samples/                 synthetic test logos + generator
outputs/                 scratch (gitignored)
```

## DiffVG differentiable refinement (experimental — working)

`backend/refine_diffvg.py` — research-notes approaches #5/#6, live: the traced
SVG is the initialization; gradient descent moves its bezier control points to
minimize pixel loss against the raster (**colors frozen** — RGB-MSE drifts hues
otherwise). Measured on `logo_geometric.png` (40 iters, 384px, 20s CPU):
quality 0.9848 → **0.9929**, ΔE halved, **same 145 points** — the only stage in
the engine that buys fidelity at zero complexity cost.

Setup (one-time): `pip install torch --index-url .../cpu`, then build
[diffvg](https://github.com/BachiLi/diffvg) with
`CMAKE_POLICY_VERSION_MINIMUM=3.5 python setup.py install`, plus
`pip install cssutils svgpathtools matplotlib`.

```bash
python backend/refine_diffvg.py logo_geometric.png --iters 40 --size 384 --freeze-colors
```

The learning rate must scale with scene density: lr=0.5 diverges on dense
scenes, but lr∝2000/points (clamped 0.02–0.5) converges — measured +0.023 @
15k pts (lr .05) and +0.011 @ 52k pts (lr .02, 27s). The tournament gates
refinement at ≤60k points (`engine.py --dv`, or the "DiffVG-refine winner"
checkbox in the UI); iteration count backs off with density. Measured wins at
zero added points: geometric +0.008, wordmark +0.016, badge **+0.076**
(0.905→0.981), transparent-lineart +0.062, fox +0.011..+0.023 depending on
winner complexity. Full-pipeline example: `python backend/engine.py
logo_badge.png --dv` → winner `potrace-k12+dv`, q=0.9819, 120 pts, 2KB.

Note: `pydiffvg.save_svg` destroys multi-subpath paths (holes) — we serialize
the refined scene ourselves (`_scene_to_svg`), preserving subpath grouping and
fill rules.

## Ideas to explore next (from the research notes)

- **LIVE / DiffVG differentiable refinement** (#5, #6): use a pipeline's output
  as initialization, then optimize control points to minimize pixel loss.
  Heavier install; slot in as a `diffvg_refine` pipeline that post-processes any
  other pipeline's SVG.
- **Segmentation-based** (#3): SAM/U²-Net masks → per-region vectorize, for
  cleaner semantic layers.
- **Adaptive complexity** (#10): vary simplify/corner thresholds per region by
  local detail instead of one global setting.
- **Multi-pass** (#11): rough → refine corners → reduce points → merge paths.
