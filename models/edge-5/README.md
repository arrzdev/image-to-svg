# edge-5 — option 1: faithful filled ribbons (Recraft-style)

Recraft target verified = ALL fills, 0 strokes; outline is one filled path of
smooth cubics. edge-5 = edge-4 (dark-ink-only, ink frozen thin) but with a
GENTLE cubic fit (smooth_win 11→3) so the thin ink ribbon stays thin+smooth
instead of fattening. Repro: python run_model.py -m edge-5 -i data/inputs/rabbit.jpg
