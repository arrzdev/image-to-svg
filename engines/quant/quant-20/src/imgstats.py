"""Cheap image statistics shared by the tournament engine and the preparer.

`analyze` classifies an image as flat / lineart / detailed from a 256px probe.
Used to adapt the candidate portfolio AND to gate pre-trace upscaling: 2x
Lanczos measurably helps anti-aliased art (fox 0.870 -> 0.925) but WRECKS crisp
flat logos — Lanczos ringing around hard edges gets traced as thousands of
junk points (logo_geometric: 145 pts/coherence 1.0 native vs 3367 pts/0.54
upscaled).
"""
from __future__ import annotations

import numpy as np


def analyze(rgb: np.ndarray) -> dict:
    import cv2
    small = cv2.resize(rgb, (256, 256), interpolation=cv2.INTER_AREA)
    q = (small // 16)
    n_colors = len(np.unique(q.reshape(-1, 3), axis=0))
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    edge_density = float((cv2.Canny(gray, 50, 150) > 0).mean())
    lum = small @ np.array([0.299, 0.587, 0.114])
    # Outlines aren't always near-black (e.g. purple cartoon strokes, lum ~77):
    # use a permissive threshold for "line pixels".
    dark_frac = float((lum < 96).mean())
    kind = "flat" if n_colors <= 60 else ("lineart" if dark_frac > 0.015 else "detailed")
    return {"n_colors": int(n_colors), "edge_density": round(edge_density, 4),
            "dark_frac": round(dark_frac, 4), "kind": kind}
