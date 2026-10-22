# image → svg

A research project on raster-to-SVG **idealization**: turning an imperfect logo,
flat illustration or game asset (JPEG noise, soft shading, anti-aliasing) into
the drawing the artist *meant* — clean confident lines, solid flat regions,
noise removed rather than traced.

The quality bar is [Recraft](https://www.recraft.ai/)'s vectorizer. Its SVG for
each test image is kept as a reference, and every engine version is measured
against it. The guiding thesis (`research/docs/VISION.md`):

> Reverse-engineer the drawing, don't trace the raster.

A drawing is strokes plus bucket fills: shading flattened, ruler lines kept
straight, single-movement curves kept single, one path per shape in painter's
order.

The project ran as a ~1-week intensive (243 commits, July 2026), mostly driven
by an autonomous experiment loop. It is **paused**; this README is the map of
what was tried and what was learned.

---

## Status

- **Best engine:** `quant-hifi` (aliased as `staged`). It is the `quant-24`
  pipeline plus an adaptive-fidelity router: images with high edge density are
  processed at 2048px with a richer palette, everything else is byte-identical
  to `quant-24`.
- **Score:** tilecmp distance to Recraft 0.2246 averaged over 11 image/target
  pairs (lower is better), down from 0.2725 when the metric was introduced.
- Flat, clean inputs are roughly at Recraft parity. Detailed/soft-shaded art
  still trails, mostly because Recraft *redraws* with object knowledge (see
  [Lessons](#lessons)).

## Quickstart

Developed on macOS / Apple Silicon.

```bash
brew install cairo resvg potrace          # resvg is optional (13x faster renders)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt maturin svgpathtools
(cd svgcore && ../.venv/bin/maturin develop --release)   # Rust geometry extension

python3 run_model.py --list                                  # all runnable engines
python3 run_model.py -m staged -i data/inputs/chopchop.png   # -> data/outputs/<img>-<model>-<ts>.svg
python3 run_model.py -m quant-12 -i data/inputs/fox.jpg -o /tmp/fox.svg

./run.sh    # browser tester at http://127.0.0.1:8000
```

`run_model.py` runs every engine in its own subprocess with `.venv/bin/python`
(engine sources share module names). It sets
`DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` so cairo is found.

The browser tester (`app/`) has two tabs:

- **Version tester:** pick an input and an engine, see Original | Output |
  Recraft target.
- **Edge Lab:** the knobs of the boundary-first `edge-11` pipeline, with
  intermediate views (edges, bucket fills, fragmentation map).

Every engine follows the same contract, so they can be routed side by side:

```
engines/<family>/<name>/entry.py   # run(image_path: str, params: dict | None = None) -> str (SVG)
engines/<family>/<name>/src/       # that engine's frozen code
```

## How quality was measured

The way outputs were judged changed several times, and that turned out to be
one of the main lessons:

| period | judge | why it was replaced |
|---|---|---|
| early | composite perceptual metric (MS-SSIM, CIEDE2000, GMSD, worst-region ΔE) | rewards copying source noise — Recraft scored *lower* than noisy traces |
| Jul 7–9 | eye verdicts on zoomed comparison grids ("zoom or it didn't happen") | unreliable: approved a visibly distorted output, and once shipped a "fix" whose output was bit-identical |
| Jul 10+ | **tilecmp** — a locked, tile-based structural distance to the Recraft SVG | kept |

**tilecmp** (`eval/tilecmp.py`) splits each image into ~40×40 tiles
and compares our SVG to Recraft's per tile on three separate channels:

- **census:** paths, cubics, lines and subpaths spent.
- **flow:** straightness, curvature rate, corner rate, edge orientation.
- **color:** mean colour, distinct-colour count, ΔE to the source.

The gate (`tilecmp_gate.py`) only accepts a change that improves the corpus
mean by ≥ 0.0015 without any single channel regressing by more than 0.006. A
structural census against Recraft (`eval/struct_compare.py`) is used
alongside it. Because the channels are separate, the gate cannot be gamed the
way a single SSIM number can.

## Approaches tried

Roughly chronological. Each family lives in `engines/<family>/` and is still
runnable ([`engines/README.md`](engines/README.md) has the per-version log).

### 1. Tournament + differentiable refinement (v1, pre-git)

vtracer, potrace and k-means quantization portfolios, scored by the composite
metric with a point-count penalty, refined with DiffVG. Good numbers (elephant
≈0.93 at ~1.1k points) but structurally dirty at deep zoom: hairlines, spurs,
DiffVG "cheating" by overlapping regions.

### 2. Shared-boundary vectorization (v2)

Build a boundary graph from the label map and fit each shared edge **once**,
reused by both neighbouring regions, so gaps are impossible by construction.
Added honest shared-edge DiffVG and a structural-integrity checker. This idea
survives in every later engine.

### 3. Quantize-first `contour_lines` pipeline — `quant-3 … quant-11`

A global k-means quantization decides topology; contours and lines are then
idealized:

- **quant-3:** Potrace-style *parsimony* fitter (wobble-free curves) and
  constant-width contour strokes.
- **quant-4:** a centerline stroke network on top of flat, parsimony-fitted
  shading; line weight calibrated to Recraft.
- **quant-5 … quant-8:** loop runs 2–35. Junction anchoring and bridging,
  shadow-tone merge, sharp serrations (corner-pinned fills, spike-tip rescue),
  thin-dark-line lock, chroma-gated joins, straight-piece priors.
- **quant-9:** 40× faster with byte-identical output, plus a sharpening
  prepass.
- **quant-10 / quant-11:** flat-art guard, gradient flattening, *transition
  ownership* (anti-aliasing shrapnel absorbed into its neighbours), first
  line-intent model.

Each has a `MANIFEST.md` with eye verdicts and negative results. An audit at
this point (`research/experiments/audit24/FINDINGS.md`) found the engine had plateaued:
roughly at parity on flat art, 50–70% of the way on soft-shaded art. It also
found process failures — items closed against a relative bar, verdicts at too
little zoom, whack-a-mole fixes instead of structural ones.

### 4. Region-first: "idealize, then colour" — `region-1 … region-7`

Blueprint in `research/docs/BLUEPRINT.md`: mean-shift idealization,
Felzenszwalb local regions (no global palette), fill colour sampled from each
region's eroded interior, then the quant-11 emitter. Separate ink layers came
in region-2/3. Fills were clean, but the output was polygonal and
over-fragmented (~1900 paths). Parked.

### 5. Boundary-first — `edge-1 … edge-11`

LAB-gradient boundaries define cells, which become fills; ink ribbons are
coloured by the darker side. Highlights:

- **edge-5** matched Recraft's all-fills/zero-strokes style.
- **edge-10** is the Edge Lab recipe: bilateral filter, ΔE buckets, region
  adjacency graph merge, LCh ink ribbons, seam glue.
- **edge-11** rebuilt detected lines as synthesized strokes (centerline +
  width profile).

As a whole engine it over-fragmented ~10× and lost 10 of 11 images to quant-13
(0.338 vs 0.249, mostly on colour). It won pizza-box outright, so its stroke
layer was later **grafted** into quant-16.

### 6. Paper port — `vectorark-1`

A classical reimplementation of ideas from VectorArk and *Layered Image
Vectorization* (arXiv 2406.05404): bilateral cascade, layered containment, a
line + circular-arc fitter, visible-pixel median colours. Layering fixed
under-resolution but stacked duplicate regions (tilecmp 0.367 vs 0.268).
Parked.

### 7. Metric-gated loop on the quantize pipeline — `quant-12 … quant-24`

Back on the strongest pipeline, now with tilecmp as the gate:

| engine | change | tilecmp |
|---|---|---|
| quant-12 | retuned palette/merge/min-area + near-straight cubics → lines | — |
| quant-13 | source-anchored recolor, dark-shrapnel absorption, gradient banding; also found a regex that had silently deleted the whole stroke layer | 0.2725 → 0.2553 |
| quant-14 | quantizer "wander" erasure | 0.2457 |
| quant-15 | structured-split recalibration | 0.2442 |
| quant-16 | edge-11 stroke graft | 0.2426 |
| quant-17 | component-tone re-anchor | 0.2411 |
| quant-18 | pen width was tuned to a stroke-free image, so all ink was 15% thin | 0.2387 |
| quant-19 | 2px coverage seal (eye-gated; invisible to tilecmp) | — |
| quant-20 | adaptive straightening, gated by a Hough straight-line-dominance signal | — |
| quant-21 | speck drop: 74–77% of our paths were tiny fragments, Recraft emits ~none | 0.2334 |
| quant-22 | looser fill tolerance: −25% cubics at no cost | — |
| quant-23 | flow-aware ink split | — |
| quant-24 | adjacency-fill merge on geometric art | 0.2315 |

### 8. Adaptive fidelity — `quant-hifi` (current)

Detailed art was getting only 0.55–0.71× Recraft's point budget because the
working resolution was fixed at 1024px. Canny edge density predicts Recraft's
budget well (r ≈ 0.83). So images in a detail band (0.065 ≤ density < 0.095)
are processed at 2048px with 24 colours; everything else falls back to
quant-24 unchanged. The upper cap exists because a very busy texture blew up
to 4.7k paths. Result: corpus 0.2315 → 0.2246, with chopchop and crystals
improving and the other 9 images unchanged.

### 9. Learned and hybrid experiments (`research/experiments/hybrid/FINDINGS.md`)

None beat the classical pipeline:

- **Diffusion pre-idealization** (SD-turbo img2img, `data/inputs_idealized/`):
  worse at every strength. img2img replaces content, and the VAE round trip
  loses detail.
- **OmniSVG 1.1 4B**, run locally (`research/experiments/omnisvg/`): 2.4–3.2× worse.
  It reinterpreted the logo with losses and fell into repetition loops on dense
  line art (~2k-token cap).

  | image | OmniSVG (best) | quant-13 |
  |---|---|---|
  | logo-geometric | 0.336 | 0.104 |
  | chopchop | 0.797 | 0.331 |

- **Curve-pair mining + a small curve idealizer** (`research/experiments/curveprior/`):
  1.3k matched curves showed no cubic-count gap on matched curves; the 142k-param
  model lost to doing nothing on held-out images.
- **Placement probe:** an oracle could cut error 45%, but no image feature
  predicts it.
- **StarVector 1B/8B** on Apple Silicon (`research/experiments/starvector/`): produces real
  `<circle>` primitives on simple geometric logos, loops on illustrations.

Conclusion: the remaining gap is Recraft's generative *redraw* prior. It cannot
be learned from 11 pairs.

### Other negative results worth knowing

- Schneider curve fitting for fills: more cubics and mangled flat art
  (−0.013 to −0.021).
- Global palette/merge thresholds: every global raise wrecks some image (fox
  +0.041). Content-adaptive gates work, global knobs don't.
- No global tint re-grade needed: Recraft's palettes match the source.
- Ideas that looked better but missed the gate's minimum gain are stashed as
  "riders" in `research/loop/candidates/`.

## Lessons

**What worked**

- Fit each shared boundary once (no gaps by construction).
- Parsimony/Potrace-style fitting for wobble-free lines.
- Strokes on top, flat fills underneath.
- Transition ownership: anti-aliasing ramps belong to a neighbour, not to new
  slivers.
- Source-anchored colour.
- Dropping specks.
- **Content-adaptive gating.** Two cheap signals cleanly separate geometric
  from organic art: straight-line dominance (straightening, merging) and edge
  density (fidelity).
- A locked, multi-channel metric gate with a measured noise floor.
- Byte-determinism, so "no change" is provable.

**What didn't**

- Whole-image perceptual metrics: they reward tracing noise.
- An agent's visual judgment as the keep/discard gate.
- Rebuilding from edges-first or regions-first as whole engines.
- Learned shortcuts at this data scale.

**The real gap.** Recraft invents structure that isn't in the pixels. In
chopchop, a straw, chair and stool are one connected black blob in the source,
and Recraft separates them. A tracer, however clean, can't do that.

**Open problems** (`research/docs/GAP_LEDGER.md`): regularity of repeated
elements (teeth), parallel thin lines being absorbed, detail-vs-noise
inversion, junction pooling, remaining path excess on some images, per-image
fidelity calibration without a target, object shadows.

## The research loop

Most engine work came from an autonomous experiment loop, documented in
`research/loop/autoresearch.md`:

1. Pick several independent candidates from `research/docs/BACKLOG.md` and
   `GAP_LEDGER.md`.
2. Develop each in its own git worktree, in parallel.
3. Re-verify every claim independently, then score it through the locked
   tilecmp gate.
4. Integrate the winners, broaden them to all images, commit, and snapshot a
   new `engines/<family>/<family>-N` on structural changes.

Discards are logged in detail so they can be picked up later.

| record | where |
|---|---|
| per-run metrics (76 runs: 44 keep, 28 discard) | `research/loop/autoresearch.jsonl` |
| narrative | `research/loop/worklog.md` |
| journal up to run 63 | `research/docs/RESEARCH_LOG.md` |
| mission | `research/docs/PROJECT_SPEC.md` |

The loop is paused via `.autoresearch-off`; [`research/README.md`](research/README.md)
has the three commands to resume it.

## Repo map

```
run_model.py  run.sh       CLI + browser tester launcher
app/                       browser tester: FastAPI server + UI (version tester, Edge Lab)
engines/                   every engine, runnable side by side
  quant/                     quantize-first: quant-3 … quant-24, quant-hifi (best; alias staged)
  edge/                      boundary-first: edge-1 … edge-11
  region/                    idealize-then-colour: region-1 … region-7
  vectorark/                 paper port: vectorark-1
eval/                      tilecmp metric + gate, findings, struct_compare, scorers vs Recraft
svgcore/                   Rust (pyo3) geometry: Schneider + Potrace-parsimony fitters
data/                      18 test rasters, 11 Recraft reference SVGs
research/
  docs/                      spec, vision, blueprint, gap ledger, backlog, research log
  loop/                      the autonomous loop: manual, run history, worklog, driver, stashed candidates
  experiments/               audit24, hybrid, omnisvg, curveprior, starvector, edge11-bench, ...
```

## Test data

The images in `data/inputs/` are a small benchmark set of logos, flat
illustrations and game assets, used for research only:

- `shield.jpg` is a Vecteezy stock image (credit: mirazhossain1053825370 /
  Vecteezy).
- `files-pile.png` is AI-generated.
- `data/targets/` holds Recraft vectorizer outputs used as quality references.

If you own any of these images and want them removed, please open an issue.

## License

Code is MIT-licensed (see [LICENSE](LICENSE)). The test images and Recraft
reference SVGs in `data/` are not covered by it; see [Test data](#test-data).
