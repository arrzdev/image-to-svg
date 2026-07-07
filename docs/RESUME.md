# START HERE — resume point (paused 2026-07-07)

Mission (canonical): **docs/PROJECT_SPEC.md**. Autonomous-loop config +
vision-verdict procedure: **autoresearch.md**. Then `docs/STATE.md`
(architecture) and `docs/BACKLOG.md` (ranked work). `docs/RESEARCH_LOG.md` is
the full journal if you need history.

**Current version:** v4 + junction fixes runs 2–3 (`contour_lines`, git
`2570c63`). **Current focus target:** rabbit (`./autoresearch.focus`).
**Best-so-far:** same-component joins flush AND cross-component dash-gaps
bridged, 8/8 by eye; elephant sanity 0.8708 (above baseline), rabbit 0.713.
**Next step:** long label-map ink losses (>1.2w) on rabbit's heart outline —
source-ink-continuity extension (walk the darkness ridge in the original
raster beyond the label map). **In-flight:** autoresearch loop LIVE (run 4 next).

## Loop operating model (autoresearch plugin)

The `autoresearch` plugin drives the autonomous loop. Trigger it with
**`/autoresearch`** (this deletes `.autoresearch-off` and resumes from
`autoresearch.md` + `autoresearch.jsonl`). Pause with **`/autoresearch off`**;
inspect read-only with **`/autoresearch status`** / **`report`**.

- **Keep/discard is by EYE**, not the metric (spec §4). `./autoresearch.sh`
  emits `METRIC` numbers for the dashboard as a *regression sanity check only*.
- The Stop hook keeps the loop going until `maxRuns` (30) or `/autoresearch off`.
- **Per-iteration `/clear` is NOT automatic.** Claude Code hooks cannot invoke
  `/clear` (verified against the docs), so the loop runs in one long context with
  PreCompact snapshots + SessionStart rehydration (matcher now includes `clear`).
  All state is on disk, so a manual `/clear` — or running each iteration headless
  via `claude -p` from an external `while` loop — gives a clean context per
  iteration with zero loss. Choose the operating mode deliberately before an
  unattended run; see autoresearch.md "Context management between iterations".

## Where we are

The engine reached **Recraft's quality tier** on the elephant reference, judged
by eye at deep zoom (not just benchmarks). The winning output comes from the
**`contour_lines` pipeline** (v4, git `c463914`): width-constant centerline
strokes for the line network + Potrace-parsimony-fitted flat shading shapes.
Comparison renders vs Recraft: `models/v4/vs_recraft_fullframe.png`,
`models/v4/vs_recraft_zoom.png`. The three original user-cited defects
(wobbly lines, width thinning, shadows-over-lines) are RESOLVED.

## How to reproduce the best current output (fast, ~3s)

```bash
cd /Users/arrz/Documents/Github/image-to-svg
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -c "
import sys; sys.path.insert(0,'backend')
from pipelines import get_pipeline; from testbed import Testbed; from svgutil import fit_svg_size
tb=Testbed('elephant.jpg'); pp,_,(ow,oh),_=tb.prep()
open('out.svg','w').write(fit_svg_size(get_pipeline('contour_lines').run(pp,{}),ow,oh))"
```
(env prefix + `.venv` python are mandatory — native renderer + Rust svgcore.)

**Data layout (migrated 2026-07):** inputs live in `data/inputs/<name>.ext`,
Recraft targets in `data/targets/<name>.svg` (paired by basename;
`PLACEHOLDER`-marked = still to fetch, see `data/README.md`), engine
deliverables in `data/outputs/{name}-{gitsha}-{timestamp}.svg`. In the
testbed, `tb.target()` returns the matching Recraft SVG (or None) — use it in
`tb.crops({...})` for the eye comparison. Only `elephant` has a real target
today; more coming.

## THE NEXT WORK — user's fresh defect report on contour_lines output

The user ran the command above and confirmed the pipeline is "very good" and
fast, but flagged specific stroke-layer defects to fix next. These are the
top priority (all in `backend/contours_exp.py` + `backend/strokes.py`):

1. **Perpendicular line crossings have GAPS** — where two strokes cross at
   ~90°, they don't actually touch; a gap shows between them. Likely cause:
   the crossing wasn't detected as a shared junction node, so the two strokes
   are independent branches whose round caps stop short of the intersection.
   Fix direction: detect crossing/T junctions in the skeleton graph and
   extend/snap incident branch endpoints to the shared crossing point (like
   the junction-patch / union-find contraction already done for shallow-angle
   X's in strokes.py, but for perpendicular crossings), or emit a small
   junction patch at the crossing.

2. **Some line curvatures differ from the original** — the centerline
   smoothing (stroke_smooth) + fit alters the drawn curve shape on some
   branches. Fix direction: reduce smoothing where the source curve is
   genuinely curved (curvature-aware smoothing), or fit the centerline with
   the parsimony fitter (svgcore.fit_open_parsimony) instead of Schneider so
   it tracks the medial axis more faithfully.

3. **Lines not joining smoothly → small RECTANGULAR artifacts** — where stroke
   segments meet (branch-to-branch, or ribbon segment seams), butt caps /
   segment ends create little rectangular nubs instead of a smooth continuous
   line. Fix direction: audit `_stroke_elements` / `_ribbon` in contours_exp.py
   for cap style at internal joins (should be round join, not butt), and check
   that continuation-merged branches emit as ONE path, not abutting segments.

Suggested approach next week: use the cached testbed to render 4096 zoom crops
AT the crossing/junction spots, look at each defect in isolation, fix one at a
time, re-eye-verify. `tb.crops({...}, out='x.png', spots=[(y,x),...])` — spots
are in 4096-render pixel space.

## Also open (lower priority, see BACKLOG.md)

- **Palette idealization**: last gap to Recraft is shading COLOR choices
  (Recraft's softer blue-gray tints) + merging to fewer shading shapes. Not a
  quality-of-lines issue.
- **Line-consistency judge** (`backend/linescore.py`, not built): the
  tournament metric under-rates idealized output, so `--mode grail` won't
  auto-pick `contour_lines`. Need a metric component rewarding stroke-width
  constancy + curvature smoothness so it wins on merit.
- **Thin-region eversion** under wide smoothing (pizza residual hairlines).
- Staged experiments/prototypes not yet defaulted: `refine_shared_v3` (live in
  grail), `idealize.py` (L0, opt-in only), `preprocess.py` (bilateral/meanshift
  candidates fielded).

## Working conventions (user-mandated)

- **Judge by VISION** (testbed grid crops vs original + Recraft), not
  benchmarks — the metric rewards copying source noise; goal is idealization.
- **Update docs/ every work session**; git commit landed work; `models/vN/`
  snapshots on structural versions.
- **Use sub-agents** for parallel research lines (strict file ownership).
- `backend/testbed.py` = disk-cached stage harness for fast experiments.
- Env for every run: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` +
  `.venv/bin/python`, absolute paths, `if __name__=='__main__'` guard for any
  script using the process pool (macOS spawn).
