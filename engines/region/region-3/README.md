# ideal-3 — ideal-1 fills + ink layer painted ON TOP (colour-from-underneath)

Third in the `ideal-` lineage. Direct response to USER feedback (2026-07-10)
that ideal-1 was "almost perfect" except black outlines took neighbour
colours, and ideal-2 went the wrong way by using quant-11's STROKE machinery.

## The approach (USER's own recipe)

Keep ideal-1's clean flat bucket-fills, and fix ONLY the outlines:

1. **idealize** → **local fills** (Felzenszwalb, no global palette) →
   **colour last** from the ORIGINAL eroded interior. Fills span the WHOLE
   area (ink is NOT carved through them), so each fill stays one clean piece.
2. **gentle same-colour merge** — join adjacent near-identical fills (LAB ΔE ≤
   `merge_de`, default 8); not aggressive, real colour breaks survive. Also
   cuts fragmentation.
3. **ink layer ON TOP** (`ink_overlay_svg`) — the ORIGINAL-dark line network
   (`detect_ink`, thin 1px lines preserved) emitted as BLACK FILLED shapes
   painted last, over the fills. Colour grabbed from the pixels underneath
   (median dark tone), so outlines are their true dark, not a neighbour's
   colour. FILLED, not stroked — keeps the drawn line's real thickness and
   needs no quant machinery.

Why fills-under-ink (not ink-carved-into-fills): carving thin ink through a
fill shatters it into disconnected pieces (measured: 95 regions → 2133 paths).
Painting ink on top leaves fills whole → **202 paths / 163 KB** (lighter than
Recraft ~700 / quant-11 476).

## Status (rabbit — research/experiments/design-studies/figures/ideal3_compare.png)

**Win:** confident black outlines back (ink-lost 36%→17%, mostly harmless AA
margins), over ideal-1's clean flat fills, very light. Reads much closer to
Recraft than ideal-1; USER-approved direction.

**Open:** ink is polygonal (`approxPolyDP`) — curves slightly faceted vs
Recraft's smooth line; single ink colour (fine for mono outlines, revisit for
coloured line art); residual ~17% AA-edge margins show fill colour; only
rabbit tested — tune `dark_lum`/`merge_de`/speckle across all 18 at display +
deep zoom.

Repro: `python run_model.py -m ideal-3 -i data/inputs/rabbit.jpg`
