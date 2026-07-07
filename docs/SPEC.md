# Project spec — image → SVG engine

## 1. The problem

Turn a raster image (logos, flat illustrations, character/game assets — often
imperfect: JPEG noise, soft shading, artifacts) into a **high-quality,
editable SVG**. Not a pixel-faithful trace — an **idealized** vector
reconstruction: clean confident lines, solid flat regions, the drawing the
artist *meant*, with the input's noise removed rather than reproduced.

## 2. The mission — open-ended improvement toward (and past) the holy grail

The real goal is **making the engine as good as possible** — an open-ended
climb, not a fixed finish line.

**Recraft's vectorizer is the north-star.** For each input we feed to Recraft
we keep its SVG as the target (`data/targets/`, 8 pairs today spanning outlined
characters, gradients, a flat-line style, and a geometric logo). Recraft's role
is to **set direction and show headroom** — every comparison keeps it in frame
so we always see how far we are and where the remaining gap is. We aim to match
it, then surpass it, in quality *and* speed.

But **Recraft is not a per-iteration gate.** We do NOT hold an iteration until
it reaches Recraft — that risks never shipping a version at all. The unit of
progress is smaller and always achievable (§5).

**Quality first.** Don't optimize speed until quality is at holy-grail level;
then shift to making the algorithms fast. (Speed can still ship as its own
improvement if it doesn't cost quality.)

## 3. The unit of iteration — "beat our own last version"

Each iteration's job is to produce output that is **better than our previous
version**, judged by eye (§4), with Recraft in the comparison as the reference.
"Better" = clearly improved on some visual axis (wobble, width consistency,
junctions, curves, color idealization, structural cleanliness, or speed) with
**no regression** on the others.

When an iteration achieves that, it **ships immediately**:
1. **Commit** the change (concise message).
2. **Document what changed** — `docs/RESEARCH_LOG.md` entry.
3. **Update memory / docs** with: what was tested, what was researched, the
   conclusions (including negative results), and what to try next.
4. Bump the version snapshot when the change is structural (§5).

An iteration is **not** required to reach Recraft to count. Aiming at the holy
grail steers *which* improvements we chase; beating our last version is what we
actually commit. Enough of these increments, in that direction, is how we reach
and then pass Recraft.

## 4. How "better" is judged — VISION, not benchmarks

The perceptual metric (`metrics.py`) is a guide, **not the objective** — it
rewards matching the source raster, so it rewards copying noise and *penalizes*
idealization (Recraft scores lower on our own metric than our noisier outputs,
yet looks better). So:

- **Primary judgment = the agent visually analyzing the output.** Render the
  new version, the previous version, and Recraft's target (plus the original),
  **crop into a grid of small zoomed squares**, and compare detail-by-detail.
  The eye verdict decides whether a change is an improvement.
- Benchmarks (SVG-Bench MSE/SSIM) are a **regression sanity-check only**, run
  when an approach already looks right — never the steering signal.

Tooling: `backend/testbed.py` — `tb.crops({'new': svg, 'prev': old, 'recraft':
tb.target()}, out='x.png', spots=[(y,x),...])` renders the comparison grid; the
agent reads the PNG and forms the verdict. Stage results are disk-cached so
single-knob experiments re-run in seconds, not minutes.

## 5. Versioning — a ladder of "better than last"

- **Git repo**, one commit per accepted improvement.
- **`models/vN/`** snapshots representative outputs + a manifest per *version*;
  bump N on structural changes, not every tweak. `models/README.md` narrates
  the history so the trajectory (each version vs the previous, and vs Recraft)
  is visible.
- The acceptance test for shipping is **"beats the previous version by eye,
  Recraft in frame, no regression"** — not "reaches Recraft."
- Deliverables land in `data/outputs/{name}-{gitsha}-{timestamp}.svg`, so any
  SVG traces back to the exact engine that made it.

## 6. Testing progression (target-first, then broaden)

A full pipeline run is minutes, so keep the inner loop tight:

1. **Focus on ONE target first** — the image the current defect shows on. Fix
   and eye-verify against that single target until the new version beats the
   old there.
2. **Broaden to the other targets** — confirm the change generalizes across the
   style spread (characters, gradients, flat-line, logo) without regressing any
   before shipping.
3. **Benchmarks last**, only when it makes sense, to catch external regressions.

## 7. Data layout

```
data/
  inputs/   <name>.jpg|png        source rasters
  targets/  <name>.svg            Recraft north-star, paired by basename
  outputs/  <name>-<sha>-<ts>.svg our deliverables (gitignored)
  _archive/                        stray files kept for safety
```
`tb.target()` returns the matching Recraft SVG (or None). Add a pair by dropping
`inputs/foo.png` + `targets/foo.svg`.

## 8. How the agent works — autonomous research + validation loop

Standing mode of operation (broad autonomy granted; keep the user informed via
docs):

1. **Pick the highest-value open item** from `docs/BACKLOG.md` (ranked by
   visual impact) on the focus target.
2. **Research** it — web for proven techniques (papers, commercial-tool
   behavior) *and* the agent's own experiments — before coding.
3. **Prototype in parallel sub-agents** with strict file ownership; each uses
   the cached testbed and judges its own result by eye. "Many hands."
4. **Verify claims independently** — the orchestrator re-runs the key result and
   looks at the grid itself before trusting a sub-agent's report.
5. **If it beats the last version → ship it** (§3): integrate, re-verify on the
   focus target, broaden to the others, commit, document, update memory.
   **If it doesn't → keep the negative result** (memory + log) and move on.
6. Repeat, always climbing from the current best. Speed work leads once quality
   is at holy-grail level (or any time it's free).

Non-negotiables: judge by eye first; keep Recraft in every comparison; ship
every genuine improvement over the last version rather than waiting for
perfection; record negative results too; keep docs current so any session
resumes cold from `docs/RESUME.md`.

## 9. Direction of travel (not a stopping gate)

- **Near-term:** each version visibly cleaner than the last — closing the gap
  to Recraft on lines, then shapes/color, verified by zoomed comparison.
- **Match:** on every target, our zoomed grid sits at or above Recraft's
  line/shape/color quality with no worse deep-zoom defects.
- **Surpass:** measurably cleaner idealization and/or faster than Recraft on the
  same inputs — and keep going; there is no fixed finish line.

## 10. Current status (see docs/RESUME.md for the live handoff)

At v4: `contour_lines` pipeline reached Recraft's tier on the elephant by eye;
open stroke defects remain (perpendicular-crossing gaps, curvature drift,
rectangular join nubs), then palette idealization. Next: iterate these on the
elephant, then generalize across the 8-target set — shipping each version that
beats the last.
