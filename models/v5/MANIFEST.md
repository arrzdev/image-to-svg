# v5 — line-network integrity + measured idealization (autoresearch runs 2–10)

Git: 50c0a03 (arc c0adad6..50c0a03, 6 keeps / 2 discards / 2 research passes).
Focus: the v4 defect report, now CLEARED — each item eye-verified vs prev +
Recraft on all 8 targets:

- Junction joins flush (run 2): ends anchor to the nearest other-branch
  centerline (0.8w), no cap poke-through nubs.
- Cross-component dash-gaps bridged (run 3): label-map line breaks reconnect
  (1.2w, forward <60°, midpoint end-to-end).
- Lost ink re-traced (run 4): free ends walk the source raster's dark ridge
  (perpendicular ridge test + 120° turn cap — never roam fills).
- Curvature drift: measured RESOLVED (run 5: 0.04px mean, p95=0).
- Shadow tones merged like Recraft (runs 8–9): measured, not taste — merged
  elephant tone lands 2/255 from Recraft's (hue-opposition guard).
- Serrated outlines redrawn (run 10): corner-aware constant-width strokes with
  miter joins — chopchop Vs sharp, rabbit line weights normalized.

Negative results kept: no global tint re-grade (Recraft's palettes match ours
to ~0.005 on 6/8); parsimony centerlines lateral; emission knobs can't fix
serration heaviness without corners+miter.

Repro: get_pipeline('contour_lines').run(proc_png, {}) — see docs/RESUME.md.
