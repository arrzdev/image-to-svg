"""ideal-4 — SIMPLE debug baseline, from ideal-1 (PURE FILLS, no ink layer).

USER (2026-07-10): restart from ideal-1 and make it as simple as possible — no
ink overlay, no colour merge, no size/path optimizations. The ink overlay
(ideal-3/earlier ideal-4) was a workaround that created its own problems
(covered eye highlights, heavy lines, "blue eyes" handling). We want the
cleanest representation to debug the ONE real defect — outlines taking
neighbour colours — at its source, in the fills themselves.

The entire pipeline, nothing else:
  resize → idealize (mean-shift) → Felzenszwalb regions → colour each region
  from the ORIGINAL eroded interior → emit fills (quant-11 layered backend).

No ink layer, no merge_similar, no carve, no speckle/approxPolyDP, no floor.
Phase 2 (smoothing, colour averaging, path optimization, stylizing eyes to
black, etc.) only after the representation is right.
"""
from __future__ import annotations

import os
import sys
from typing import Dict

import cv2
import numpy as np

_BACKEND = os.path.join(os.path.dirname(__file__), "..", "..", "quant-11", "src")
if _BACKEND not in sys.path:
    sys.path.insert(0, os.path.abspath(_BACKEND))


def measure_scale(img: np.ndarray) -> float:
    return float(np.clip(max(img.shape[:2]) / 256.0, 2.0, 24.0))


def idealize(img: np.ndarray, scale: float) -> np.ndarray:
    """Edge-preserving flatten so Felzenszwalb sees clean regions, not JPEG
    noise. The one and only colour-touching step."""
    a = cv2.bilateralFilter(img, d=0, sigmaColor=18,
                            sigmaSpace=max(2.0, scale * 0.6))
    sp = float(np.clip(scale * 1.2, 6, 40))
    return cv2.pyrMeanShiftFiltering(a, sp=sp, sr=24.0, maxLevel=2)


def segment(simp: np.ndarray, min_area: int) -> np.ndarray:
    from skimage.segmentation import felzenszwalb
    lab = cv2.cvtColor(simp, cv2.COLOR_RGB2LAB)
    fz = felzenszwalb(lab, scale=100.0, sigma=0.5, min_size=int(min_area))
    _, labels = np.unique(fz, return_inverse=True)
    return labels.reshape(simp.shape[:2]).astype(np.int32)


def raw_fills_svg(labels: np.ndarray, centres: np.ndarray) -> str:
    """RAW emission: each region's actual boundary as a filled polygon —
    pixel staircase and all. NO curve fitting, NO corner detection, NO
    line-intent, NO parsimony, NO seam sealing. Painter's order = big regions
    first so smaller ones stack on top. This is the true representation with
    nothing hiding."""
    H, W = labels.shape
    areas = np.bincount(labels.ravel(), minlength=len(centres))
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" '
           f'viewBox="0 0 {W} {H}">']
    for r in np.argsort(areas)[::-1]:
        if areas[r] == 0:
            continue
        mask = (labels == r).astype(np.uint8)
        cnts, _ = cv2.findContours(mask, cv2.RETR_CCOMP,
                                   cv2.CHAIN_APPROX_SIMPLE)
        subs = []
        for c in cnts:
            pts = c.reshape(-1, 2)
            if len(pts) < 3:
                continue
            subs.append("M " + " L ".join(f"{x} {y}" for x, y in pts) + " Z")
        if subs:
            cx = centres[r]
            hexc = "#%02x%02x%02x" % (int(cx[0]), int(cx[1]), int(cx[2]))
            out.append(f'<path d="{" ".join(subs)}" fill="{hexc}" '
                       f'fill-rule="evenodd"/>')
    out.append("</svg>")
    return "\n".join(out)


def recolor_from_interior(orig: np.ndarray, labels: np.ndarray,
                          erode: int) -> np.ndarray:
    """Each region's colour = median of the ORIGINAL over its eroded interior
    (boundary AA excluded). Thin regions fall back to their own pixels."""
    from scipy import ndimage
    n = int(labels.max()) + 1
    centres = np.zeros((n, 3), np.uint8)
    of = orig.reshape(-1, 3)
    lb = labels.ravel()
    bnd = np.zeros(labels.shape, bool)
    bnd[:, 1:] |= labels[:, 1:] != labels[:, :-1]
    bnd[1:, :] |= labels[1:, :] != labels[:-1, :]
    dist = ndimage.distance_transform_edt(~bnd)
    interior = (dist >= erode).ravel()
    order = np.argsort(lb, kind="stable")
    starts = np.searchsorted(lb[order], np.arange(n))
    ends = np.searchsorted(lb[order], np.arange(n) + 1)
    for r in range(n):
        idx = order[starts[r]:ends[r]]
        sel = idx[interior[idx]]
        px = of[sel] if sel.size else of[idx]
        centres[r] = np.median(px, axis=0)
    return centres


def run_pipeline(image_path: str, params: dict,
                 dump: Dict[str, np.ndarray] = None) -> str:
    # ABSOLUTE MINIMUM. NO resize (native in → native out), NO mean-shift, NO
    # colour averaging. Only: segment at native res with a tiny min_size (so
    # small light details — eye highlights — survive as their own regions),
    # colour each region from the ORIGINAL, emit shared-boundary raw polygons.
    # Working resolution: CAP the longest side at work_dim (area-downscale
    # smooths JPEG noise + drops felzenszwalb from ~44s to ~5s). Images already
    # <= work_dim are left at NATIVE — never upscale: bicubic upscaling only
    # softens edges and rings on crisp art, adding no information.
    # STEP 1 = DENOISE: felzenszwalb dissolves sub-`min_size` scribble into its
    # region. min_size is a FRACTION of the working frame (not an absolute px
    # count) so the denoise is consistent at any input size. Level B
    # (~3.8e-5 of frame ≈ 90px @1536) = noise gone, shading kept; ~2x that ≈ C
    # (flatter, lighter).
    p = {"work_dim": 1536, "fz_scale": 400.0, "min_area_frac": 3.8e-5}
    p.update(params or {})

    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"cannot read {image_path}")
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    wd = int(p["work_dim"])
    s = wd / max(img.shape[:2])
    if s < 1.0:                                    # downscale only
        work = cv2.resize(img, (max(1, round(img.shape[1] * s)),
                                max(1, round(img.shape[0] * s))),
                          interpolation=cv2.INTER_AREA)
    else:                                          # already small → native
        work = img
    Hh, Ww = work.shape[:2]

    from skimage.segmentation import felzenszwalb
    lab = cv2.cvtColor(work, cv2.COLOR_RGB2LAB)
    min_size = max(8, int(round(p["min_area_frac"] * Hh * Ww)))
    fz = felzenszwalb(lab, scale=float(p["fz_scale"]), sigma=0.6,
                      min_size=min_size)
    _, labels = np.unique(fz, return_inverse=True)
    labels = labels.reshape(work.shape[:2]).astype(np.int32)

    centres = recolor_from_interior(work, labels, 1)   # colour from original
    if dump is not None:
        dump["fills"] = centres[labels]

    import boundary
    from boundary_split import emit_regions_layered
    edges, _ = boundary.build_edges(labels)
    loops = boundary.region_loops(edges, len(centres))
    fitted = {i: boundary._line_cubics(e["pts"]) for i, e in enumerate(edges)}
    return emit_regions_layered(labels, centres, loops, fitted, edges)
