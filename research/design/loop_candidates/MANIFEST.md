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

## Consumed/void (kept for history only — do NOT re-apply)
- it3_localsplit, it6_rampband, it7_transmud: SHIPPED pre-quant-13 cut.
- it9_wandererase: SHIPPED run 65 (quant-14).
- it10_satink_+0.0000: void (zero measured gain).
- adjudication_run65.json: run-65 stash audit record.
