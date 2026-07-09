# v9 — sharpen prepass + 40x performance (autoresearch it22, runs 36-37)

Git: **d216bce**. Engine = `contour_lines`. **CURRENT / LIVE tree.**
Examples rendered at d216bce.

Adds over v8:
- **40x faster** (run 36, output byte-identical 18/18): chopchop 298->7.4s,
  rabbit 31->3.5s — faster than v5. 88% of the v5->v8 regression was the
  run-35 cusp descent rescanning argwhere per node x pocket; rest =
  full-frame medial_axis/EDT/dilation now on padded bboxes.
- **Sharpen prepass, default ON** (run 37, USER idea): LANCZOS up 3x ->
  unsharp 1.6 -> INTER_AREA down + anti-ringing clamp (clip to local
  erode/dilate extremes). Melts blur/AA gradient noise before it becomes
  labels: chopchop strut daubs gone, rabbit heart flat + highlight rim,
  app-asset dropped letter restored, 9 wins / 7 lateral. Known trade
  (logged): soft-gradient JPEGs can band (shield strap rim blobs, mountain
  band reshuffle); 3 auto-gate discriminators measured non-separating;
  `presharpen=0` disables per image.

Repro: `python run_model.py -m v9 -i data/inputs/<img>`
