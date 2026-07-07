# Model versions

Each `vN/` folder is a snapshot of what the engine produced at that stage —
representative SVGs + a manifest tying it to the git commit. The code history
lives in git; these folders exist so output evolution can be compared side by
side without checking out old commits. Mission & versioning rules:
`docs/PROJECT_SPEC.md` (§5). Bump N only on **structural** changes; update this
file on every bump, narrating each version vs the previous **and vs Recraft**.

- **v1** (pre-git, ~Jul 5): first tournament engine — vtracer/potrace/quantize
  portfolios, composite metric, DiffVG refinement. Elephant grail ≈ 0.934 @
  ~1.1k pts, but structurally dirty at deep zoom (independent tracing:
  hairlines, spurs; independent DV overlap-cheating discovered later).
- **v2** (pre-git, Jul 6 milestone): shared-boundary vectorization + honest
  shared-edge DV + structural integrity judge. Elephant 0.9312 @ 727 pts,
  integrity 1.0. Artifact: claude.ai/code/artifact/24a07afa-...
- **v3** (first git commit): + Potrace-parsimony fitter (wobble-free by
  construction), width-constant contour strokes (the drawn look), junction
  ink pooling, 3.7x faster grail (~80s), cached testbed, vision-first
  process per user direction.
- **v4** (git `c463914`; snapshot in `v4/`): line/fill idealization —
  vision-first pass. `contour_lines` pipeline: width-constant centerline
  strokes for the line network + parsimony-fitted flat SHADING shapes,
  line-weight calibrated to Recraft (`width_scale=0.85`), strokes as the top
  layer. **vs v3:** the three user-cited defects (wobbly lines, width thinning,
  shadows-over-lines) resolved; lines read as confident digital strokes.
  **vs Recraft:** line + fill quality now in Recraft's tier on the elephant by
  eye (`v4/vs_recraft_fullframe.png`, `v4/vs_recraft_zoom.png`); residual gap is
  subtle palette/shading-color, not structural. Elephant `contour_lines`
  ≈ 918 pts / 39 paths / 13KB. Open defects → docs/BACKLOG.md.
- **v5** (git `50c0a03`; snapshot in `v5/`): the autoresearch arc, runs 2–10 —
  line-network integrity + measured idealization. **vs v4:** the v4 defect
  report is cleared — junction nubs/pinches fixed, cross-component dash-gaps
  bridged, despeckle-lost ink re-traced from the source raster, curvature
  drift measured resolved (0.04px), shadow tones merged, serrated outlines
  redrawn as corner-sharp constant-width strokes (miter joins). **vs Recraft:**
  junction/join cleanliness and shadow palette now match on the elephant by
  eye; chopchop serrations moved decisively toward Recraft's crisp zigzag;
  rabbit's dashed outlines are near-continuous (long label-map losses remain
  the visible gap). Each keep eye-verified on all 8 targets; negative results
  in v5/MANIFEST.md. _(Current best — the loop continues from here.)_
