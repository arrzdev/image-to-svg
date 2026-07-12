# loop_candidates stash manifest
Rule: ALWAYS check this manifest + grep the tree for a diff's symbols before
re-applying anything here (2026-07-12 lesson: 3 of 5 stashed diffs were
already shipped and their labels were stale).

## Stashed, NOT shipped (riders awaiting a batch that clears MIN_GAIN 0.0015)
- it70_satdark_reanchor_+0.0002_rider.diff (2026-07-13): extends it69
  _reanchor_component_tones to SATURATED MID-DARK minted tones (lum>=60 &
  spread>45 — provably outside ink candidacy, mirrors extract_contour_strokes'
  refusal clause). Fires on exactly 2 comps corpus-wide (crystals deep-blue
  edge strip, shield strap rivet-1 surround), both eye-verified wins, 9
  targets byte-identical, stroke-coupling measured zero. +0.0002 corpus
  (crystals -0.0014, shield -0.0009). SHIP as rider on any future keep:
  apply, verify combined sweep, credit noted. Cut from HEAD 90a71fb.
- it71_darkring_carve_+0.0004_rider.diff (2026-07-13): _carve_dark_ribbons —
  thin dark ribbon sub-components minted from fill-grade parents (local
  masked-mean baseline, blend veto, ENCLOSURE gate = the must-not killer;
  it70 satdark mint mirror). Fires 5 comps (shield rivet rings x4 -0.0034,
  mountain streak -0.0006), 9 stems byte-identical, eye-verified. +0.0004
  corpus, population-exhausted (~1100 carveable px at safe thresholds; every
  loosening re-admits a measured must-not). Rider pool with it70 = +0.0006.
  Cut from HEAD 90a71fb. NOTE: overlaps it70 rider on contour_lines.py —
  apply it70 FIRST, then this (both extend _reanchor area; verify combined).
- it72_widthgrade_corners_+0.0006_rider.diff (2026-07-13): per-chain width
  grading (dev>=0.44 keeps own constant width; thin chains stop rendering as
  leech tadpoles, thick stop dipping) + drawn-corner pinning for non-band
  strokes (80deg/0.80 localization; organic stems fire zero). Eye-LOUD
  (pizza separators thin, corners sharp on shield/chopchop/rabbit) but
  tilecmp-quiet (+0.0006; 1-3px corrections dilute at 40x40 tiles). All
  channels clean, must-nots hold, REVIEW flag: chopchop goggle ring bolder
  (closer to src, heavier than Recraft). Touches contours_exp.py+strokes.py
  (DIFFERENT area than it70/it71 riders — apply after them; verify combined).
  RIDER POOL now it70+it71+it72 ~= +0.0012. Cut from HEAD 90a71fb.

## Consumed/void (kept for history only — do NOT re-apply)
- it3_localsplit, it6_rampband, it7_transmud: SHIPPED pre-quant-13 cut.
- it9_wandererase: SHIPPED run 65 (quant-14).
- it10_satink_+0.0000: void (zero measured gain).
- adjudication_run65.json: run-65 stash audit record.
