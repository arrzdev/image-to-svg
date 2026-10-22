# edge-2 — boundary-first, real vectors

Faithful vectorization of edge-1's frozen look. Cells → filled vector paths;
boundaries → STROKED smoothed centerlines (build_edges), colored by darkest
original pixel along each edge (ink stays black). Stroked not filled, so thin
lines stay solid. Repro: python run_model.py -m edge-2 -i data/inputs/rabbit.jpg
