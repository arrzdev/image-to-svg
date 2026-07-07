# Project spec — image → SVG engine

## 1. The problem

Turn a raster image (logos, flat illustrations, character/game assets — often
imperfect: JPEG noise, soft shading, artifacts) into a **high-quality,
editable SVG**. Not a pixel-faithful trace — an **idealized** vector
reconstruction: clean confident lines, solid flat regions, the drawing the
artist *meant*, with the input's noise removed rather than reproduced.

## 2. The target — the "holy grail"

**Recraft's vectorizer is the reference.** For each input we feed to Recraft we
keep its SVG output as the target to match. We currently have 8 target pairs in
`data/targets/` spanning outlined characters, gradients, a flat-line style, and
a geometric logo.

- **Goal 1: reach Recraft's quality** (judged by eye at deep zoom).
- **Goal 2: then surpass it** — in both quality *and* speed.
- **Ordering: quality first.** Do not optimize speed until the output quality
  is at holy-grail level. Once there, shift to making the algorithms fast.

## 3. How quality is judged — VISION, not benchmarks

The perceptual metric (`metrics.py`) is a guide, **not the objective** — it
rewards matching the source raster, which means it rewards copying noise and
*penalizes* idealization (Recraft scores lower on our own metric than our
noisy outputs, yet looks better). So:

- **Primary judgment = the agent visually analyzing the output.** Render ours,
  Recraft's target, and the original, **crop into a grid of small zoomed
  squares**, and compare detail-by-detail. Wobble, width consistency, junction
  cleanliness, curve fidelity, color choices — all judged by looking.
- Benchmarks (SVG-Bench MSE/SSIM) are a **final sanity check** for regressions,
  run only when an approach already looks right — never the steering signal.

Tooling: `backend/testbed.py` — `tb.crops({'mine': svg, 'recraft': tb.target()},
out='x.png', spots=[(y,x),...])` renders the comparison grid; the agent reads
the PNG and forms an eye verdict. Stage results are disk-cached so single-knob
experiments re-run in seconds instead of minutes.

## 4. Testing progression (target-first, then broaden)

To keep iteration fast (a full pipeline run is minutes):

1. **Focus on ONE target first** (the elephant, or whichever image the current
   defect shows on). Fix and eye-verify against that single target until it
   meets the bar. This is the fast inner loop.
2. **Broaden to the other targets** once the single image is good — confirm the
   change generalizes across the style spread (characters, gradients,
   flat-line, logo) without regressing any.
3. **Run benchmarks last**, only when it makes sense, to catch regressions on
   the external set.

## 5. Versioning — every iteration beats the last

- **Git repo**, commit each landed improvement (concise message).
- **`models/vN/`** snapshots representative outputs + a manifest per engine
  *version*; bump N on structural changes, not every tweak. `models/README.md`
  narrates the version history.
- Each version is expected to be **strictly better than the previous** on the
  vision comparison (or better on one axis with no regression on others). If a
  change loses on the eye test, it doesn't ship, regardless of the metric.
- Generated deliverables land in `data/outputs/{name}-{gitsha}-{timestamp}.svg`
  so any SVG traces back to the exact engine that made it.

## 6. Data layout

```
data/
  inputs/   <name>.jpg|png        source rasters
  targets/  <name>.svg            Recraft "holy grail", paired by basename
  outputs/  <name>-<sha>-<ts>.svg our deliverables (gitignored)
  _archive/                        stray files kept for safety
```
`tb.target()` returns the matching Recraft SVG (or None). Add a new pair by
dropping `inputs/foo.png` + `targets/foo.svg`.

## 7. How the agent works — autonomous research + validation loop

Standing mode of operation (the user grants broad autonomy; asks only to be
kept informed via docs):

1. **Pick the highest-value open defect** (from `docs/BACKLOG.md`, ranked by
   visual impact) on the focus target.
2. **Research** it — web for proven techniques (papers, commercial-tool
   behavior) *and* the agent's own experiments — before coding.
3. **Prototype in parallel sub-agents** with strict file ownership (each agent
   owns specific files, uses the cached testbed, judges its own result by eye).
   "Many hands": several independent research lines at once.
4. **Verify claims independently** — the orchestrator re-runs the key result
   and looks at the grid itself before trusting a sub-agent's report.
5. **Integrate winners** into the engine (pipelines/candidates), **re-verify**
   on the focus target, then **broaden** to the other targets.
6. **Document every iteration** — `docs/RESEARCH_LOG.md` (what/learned/next),
   `docs/STATE.md` (current architecture), `docs/BACKLOG.md` (ranked queue),
   plus memory. This survives context compaction and keeps the user in the
   loop. **Commit.**
7. Repeat. Speed work begins only after quality parity.

Non-negotiables: judge by eye first; never claim parity without a zoomed
visual comparison that shows it; report failures honestly; keep the docs
current so any session can resume cold from `docs/RESUME.md`.

## 8. Definition of done

- **Parity (Goal 1):** on every target, the agent's zoomed grid comparison
  shows our output at or above Recraft's line/shape/color quality, with no
  worse deep-zoom structural defects — confirmed by an explicit eye verdict per
  target, not just a metric.
- **Surpass (Goal 2):** measurably cleaner idealization and/or faster than
  Recraft on the same inputs.

## 9. Current status (see docs/RESUME.md for the live handoff)

At v4: `contour_lines` pipeline reached Recraft's tier on the elephant by eye;
three open stroke defects remain (perpendicular-crossing gaps, curvature drift,
rectangular join nubs), then palette idealization. Now generalizing across the
8-target set.
