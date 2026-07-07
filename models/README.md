# Model versions

Each runnable `vN/` folder contains the version's **complete code** and a
stable entry point, so any version runs from the main branch without touching
git history:

- `entry.py` — `run(image_path, params=None) -> str` (SVG). Same contract in
  every version; the root `run_model.py` CLI and `server.py` frontend route
  through it in isolated subprocesses.
- `src/` — the engine as it was at that version's commit (frozen; the LIVE
  engine is the newest version's src, which the research loop edits).
- `examples/` — SVGs produced by exactly this folder's code (regenerate with
  `python3 run_model.py -m vN -i data/inputs/<img>`), plus historical
  comparison PNGs.
- `MANIFEST.md` — what changed, eye verdicts, negative results.

v5 also carries `data`/`outputs`/`frontend`/`autoresearch.focus` symlinks so
the research harness (`research/autoresearch.sh` → `src/ar_eval.py`,
`src/testbed.py`) finds its cache and references.

Mission & versioning rules: `research/docs/PROJECT_SPEC.md` (§5). Bump N only
on **structural** changes; update this file on every bump, narrating each
version vs the previous **and vs Recraft**.

- **v1** (pre-git, ~Jul 5): first tournament engine — vtracer/potrace/quantize
  portfolios, composite metric, DiffVG refinement. Elephant grail ≈ 0.934 @
  ~1.1k pts, but structurally dirty at deep zoom (independent tracing:
  hairlines, spurs; independent DV overlap-cheating discovered later).
- **v2** (pre-git, Jul 6 milestone): shared-boundary vectorization + honest
  shared-edge DV + structural integrity judge. Elephant 0.9312 @ 727 pts,
  integrity 1.0. Artifact: claude.ai/code/artifact/24a07afa-...
- **v3** (git `d7804f5`, 2026-07-07 01:58; code in `v3/src`): + Potrace-parsimony fitter (wobble-free by
  construction), width-constant contour strokes (the drawn look), junction
  ink pooling, 3.7x faster grail (~80s), cached testbed, vision-first
  process per user direction.
- **v4** (git `c463914`, 2026-07-07 03:03; code in `v4/src`): line/fill idealization —
  vision-first pass. `contour_lines` pipeline: width-constant centerline
  strokes for the line network + parsimony-fitted flat SHADING shapes,
  line-weight calibrated to Recraft (`width_scale=0.85`), strokes as the top
  layer. **vs v3:** the three user-cited defects (wobbly lines, width thinning,
  shadows-over-lines) resolved; lines read as confident digital strokes.
  **vs Recraft:** line + fill quality now in Recraft's tier on the elephant by
  eye (`v4/vs_recraft_fullframe.png`, `v4/vs_recraft_zoom.png`); residual gap is
  subtle palette/shading-color, not structural. Elephant `contour_lines`
  ≈ 918 pts / 39 paths / 13KB. Open defects → docs/BACKLOG.md.
- **v5** (git `3d251ad`, 2026-07-07 23:29; code in `v5/src`): the autoresearch arc, runs 2–14 —
  line-network integrity + measured idealization. **vs v4:** the v4 defect
  report is cleared — junction nubs/pinches fixed, cross-component dash-gaps
  bridged, despeckle-lost ink re-traced from the source raster, curvature
  drift measured resolved (0.04px), shadow tones merged, serrated outlines
  redrawn as corner-sharp constant-width strokes (miter joins). **vs Recraft:**
  junction/join cleanliness and shadow palette now match on the elephant by
  eye; chopchop serrations moved decisively toward Recraft's crisp zigzag;
  rabbit's dashed outlines are near-continuous (long label-map losses remain
  the visible gap). Runs 11–14 added (worktree-parallel iterations): adjacency
  fleck absorption, wiggle-gate texture→soft daubs, guarded plank-speckle
  dissolve, the despeckle light-accent guard (striped straw / gem vein / fox
  eye glint / monster scratch rescued), and the junction pool clamp (frond
  centers + chair crossings cross clean). Each keep eye-verified on all
  targets; negative results in v5/MANIFEST.md and research/docs/RESEARCH_LOG.md.
  _(Current best — the loop continues from here; next structural bump = v6.)_
