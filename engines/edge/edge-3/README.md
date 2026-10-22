# edge-3 — boundary-first, all containers as filled paths

No strokes. Every region (light cells + the ink network) is a filled container,
emitted as one clean vector path. Ink colored darker-side (black), cells by
interior median. Repro: python run_model.py -m edge-3 -i data/inputs/rabbit.jpg
