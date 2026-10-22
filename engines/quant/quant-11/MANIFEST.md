# v11 — transition ownership + line-intent stage 1 (autoresearch it24, runs 54-55)

Git: **8315d66**. Engine = `contour_lines`. **CURRENT / LIVE tree.**
Examples rendered at the cut. First milestone of the audit-24 campaign
(research/docs/VISION.md, research/experiments/audit24/FINDINGS.md).

Adds over v10:
- **Transition ownership** (run 54, E1): thin non-ink components whose color
  lies on the Lab segment between their two dominant ring labels absorb into
  the nearer bound (all gates population-measured; stroke-components never
  count as bounds). app-asset bezel shrapnel + invented white blob GONE
  (integrity .412→.988); mountain stain fragments absorbed (.488→1.000,
  ledger 0l closed); fox in-ink debris gone; 10/18 byte-identical.
- **Line-intent stage 1** (run 55, E4/E5): drawing-intent anchors (25° turn
  + two-scale localization) partition boundary pieces; anchor-to-anchor
  spans emit exact chords under tiered population-measured caps; raster-
  gated G1 repair kills fitter-minted kinks; same intent on capsule
  centerlines. Monster hand hairlines straight + sharp kinks ≈ recraft
  (ledger 0k hand closed), teeth crisp zigzag (residual = label lattice,
  E5), crystals facets + mountain ridges straighter; logo circle stays
  round (arc landmine cleared).

Known residuals (it25 queue): 0h AA seams (underpaint/E8 emission — PoC in
run 45), E2 object shadows (gates measured run 43), teeth lattice (E5),
E1 high-contrast subclass (geometry signal or E8; see BACKLOG).

Repro: `python run_model.py -m v11 -i data/inputs/<img>`
