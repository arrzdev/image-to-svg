# edge-8 — edge-7 + parsimony + line-intent emitter (Recraft primitives)

Swaps the dense per-pixel fitter for quant-11's parsimony + line-intent emitter:
sparse control points, straight runs -> L, curves -> smooth C, corners pinned,
seams sealed. Fixes jaggy zoom + wobbly straights + bloated path count.
Repro: python run_model.py -m edge-8 -i data/inputs/rabbit.jpg
