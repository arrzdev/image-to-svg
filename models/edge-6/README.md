# edge-6 — edge-5 + seam sealing (approach 2)

edge-5 had 1px anti-alias seams between adjacent bucket fills. edge-6 seals them
by giving each LIGHT fill a thin same-color stroke (~0.5px grow) so neighbors
tuck under — no background bleed. DARK ink paths get no stroke (stay thin).
Repro: python run_model.py -m edge-6 -i data/inputs/rabbit.jpg
