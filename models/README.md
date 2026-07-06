# Model versions

Each `vN/` folder is a snapshot of what the engine produced at that stage —
representative SVGs + a manifest tying it to the git commit. The code history
lives in git; these folders exist so output evolution can be compared side by
side without checking out old commits.

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
