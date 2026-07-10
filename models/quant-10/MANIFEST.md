# v10 — glyph rescue + gradient flatten + flat-art guard (autoresearch it23, runs 38-40)

Git: **01e80e0** (cut at 2287515). Engine = `contour_lines`. **CURRENT / LIVE tree.**
Examples rendered at the cut.

Adds over v9:
- **Flat-art skip for the sharpen prepass** (run 38, hotfix): imgstats
  kind==flat bypasses sharpening — the run-37 monster-mouth regression
  restored, byte-verified both directions.
- **Chromatic-mark rescue** (run 39, it23 B-icongeom): despeckle+dissolve
  exempt chromatic marks (ab-shift>=20, own-C>=27 for dark) — app-asset
  "Share" r + envelope glyph creases survive the label floors; ledger 0g
  closed; measured discriminator for 0c (intent-vs-noise).
- **Gradient-region flatten, recraft-style** (run 40, it23 A-gradientflat):
  large quiet smooth-ramp regions (area>=4%, sat>=40, hue<=8) flatten to ONE
  solid before quantize + hue purge. app-asset bg ragged rings ALL gone;
  ledger 0f closed. Leads: sub-4% drop-shadows, mountain fragmentation,
  faint flatten seam on shield.

Repro: `python run_model.py -m v10 -i data/inputs/<img>`
