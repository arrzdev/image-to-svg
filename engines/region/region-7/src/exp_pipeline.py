"""ideal-5 — AGGREGATION approach (USER direction, 2026-07-10).

The pivot away from denoise-by-merging. ideal-4 removed noise by merging small
regions (felzenszwalb scale=400), which ate thin dark OUTLINES into the light
neighbour beside them → grey outlines. USER's fix: don't remove regions to kill
noise — keep segmentation GENTLE so every region (incl. the dark outline)
survives, and clean the *appearance* by AGGREGATING the rough fragmented
geometry into smooth shapes (a rough 9-segment circle → one smooth closed
curve). Noise goes away because the shapes get clean, not because pixels merged.

Pipeline:
  1. resize  — cap longest side at work_dim (downscale only, never upscale);
     images already smaller stay native.
  2. colour group — a SMALL edge-preserving average (bilateral) so near-
     identical pixels read as one piece, kept gentle so coloured shadows
     survive (no big mean-shift).
  3. segment — Felzenszwalb GENTLE (low scale): outlines survive as their own
     dark regions instead of being merged/greyed. min_size only drops sub-px
     specks (relative to frame).
  4. colour last — each region = median of the ORIGINAL eroded interior.
  5. aggregate — emit with the FILL boundary fitter (smooth curves + corners):
     rough pixel-staircase boundaries become clean smooth paths, many
     fragments of one form become one path. This is the fill fitter, NOT the
     stroke machinery.
"""
from __future__ import annotations

import os
import sys
from typing import Dict

import cv2
import numpy as np

_BACKEND = os.path.join(os.path.dirname(__file__), "..", "..", "..", "quant", "quant-11", "src")
if _BACKEND not in sys.path:
    sys.path.insert(0, os.path.abspath(_BACKEND))


def merge_similar(labels: np.ndarray, work: np.ndarray, de: float) -> np.ndarray:
    """AGGREGATE BY COLOUR (USER's key idea): union adjacent regions whose mean
    colours are within `de` (LAB). Same-colour fragments (the JPEG/AA noise)
    join into one piece; the dark OUTLINE is a different colour so it never
    merges — outlines stay dark AND the noise-seams vanish. Not aggressive:
    coloured shadows sit far above `de` and survive."""
    n = int(labels.max()) + 1
    of = work.reshape(-1, 3).astype(np.float64)
    lb = labels.ravel()
    cnt = np.maximum(np.bincount(lb, minlength=n), 1)
    means = np.stack([np.bincount(lb, weights=of[:, c], minlength=n) / cnt
                      for c in range(3)], 1)
    meansL = cv2.cvtColor(means.reshape(1, -1, 3).astype(np.uint8),
                          cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float64)
    a = labels
    pr = np.vstack([np.stack([a[:, :-1].ravel(), a[:, 1:].ravel()], 1),
                    np.stack([a[:-1, :].ravel(), a[1:, :].ravel()], 1)])
    pr = np.unique(np.sort(pr[pr[:, 0] != pr[:, 1]], 1), axis=0)
    parent = np.arange(n)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    d2 = de * de
    for r, q in pr:
        if ((meansL[r] - meansL[q]) ** 2).sum() <= d2:
            ra, rb = find(int(r)), find(int(q))
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    roots = np.array([find(i) for i in range(n)])
    _, new = np.unique(roots, return_inverse=True)
    return new[labels].astype(np.int32)


def absorb_transitions(labels: np.ndarray, work: np.ndarray,
                       perp_max: float = 15.0, t_lo: float = 0.12,
                       t_hi: float = 0.88,
                       max_area_frac: float = 0.004) -> np.ndarray:
    """Remove anti-aliasing RAMP fragments (the halo bands beside outlines, the
    rim around the eye). A thin region whose colour lies BETWEEN its two main
    neighbours (on the segment A–B in LAB, param t in (t_lo,t_hi), small
    perpendicular distance) is a soft edge, not a drawn shape — dissolve it into
    the nearer neighbour. Colour-merge can't touch these (they're ΔE 20–150
    from both sides); this is the idealisation that erases pixel-noise the
    artist never drew. Absorb only into a STRICTLY larger neighbour (acyclic)."""
    from collections import defaultdict
    for _ in range(5):
        n = int(labels.max()) + 1
        lb = labels.ravel()
        of = work.reshape(-1, 3).astype(np.float64)
        cnt = np.maximum(np.bincount(lb, minlength=n), 1)
        rgb = np.stack([np.bincount(lb, weights=of[:, c], minlength=n) / cnt
                        for c in range(3)], 1)
        LAB = cv2.cvtColor(rgb.reshape(1, -1, 3).astype(np.uint8),
                           cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float64)
        area = np.bincount(lb, minlength=n)
        a = labels
        hl, hr = a[:, :-1].ravel(), a[:, 1:].ravel()
        vt, vb = a[:-1, :].ravel(), a[1:, :].ravel()
        mh, mv = hl != hr, vt != vb
        pl = np.concatenate([np.minimum(hl[mh], hr[mh]),
                             np.minimum(vt[mv], vb[mv])])
        pq = np.concatenate([np.maximum(hl[mh], hr[mh]),
                             np.maximum(vt[mv], vb[mv])])
        key = pl.astype(np.int64) * n + pq
        uk, uc = np.unique(key, return_counts=True)
        nbr = defaultdict(list)
        for k, cc in zip(uk.tolist(), uc.tolist()):
            r, q = divmod(k, n)
            nbr[r].append((q, cc)); nbr[q].append((r, cc))
        total = labels.size
        lut = np.arange(n)
        changed = False
        for r in np.argsort(area):
            if area[r] > max_area_frac * total or area[r] < 8:
                continue
            ns = sorted(nbr[r], key=lambda x: -x[1])
            if len(ns) < 2:
                continue
            A, B = ns[0][0], ns[1][0]
            P, U = LAB[r], LAB[B] - LAB[A]
            uu = float(U @ U)
            if uu < 1e-6:
                continue
            t = float((P - LAB[A]) @ U / uu)
            perp = float(np.linalg.norm(P - (LAB[A] + np.clip(t, 0, 1) * U)))
            if t_lo < t < t_hi and perp < perp_max:
                tgt = A if (np.linalg.norm(P - LAB[A])
                            < np.linalg.norm(P - LAB[B])) else B
                if area[tgt] > area[r]:            # strictly larger = acyclic
                    lut[r] = tgt; changed = True
        if not changed:
            break
        for i in range(n):
            while lut[i] != lut[lut[i]]:
                lut[i] = lut[lut[i]]
        labels = lut[labels]
        _, labels = np.unique(labels, return_inverse=True)
        labels = labels.reshape(a.shape).astype(np.int32)
    return labels


def cleanup_slivers(labels: np.ndarray, work: np.ndarray,
                    max_area_frac: float = 0.0007,
                    de_max: float = 24.0) -> np.ndarray:
    """Dissolve small LOW-CONTRAST regions into their dominant neighbour — the
    soft-shading fragments / ghost slivers sitting inside one colour (a blob in
    the white) that transition-absorb misses (it needs a ramp between TWO
    neighbours). Only absorbs when the colour is CLOSE (ΔE<de_max) so distinct
    small features (the eye highlight, ΔE~100) survive, and into a strictly
    larger neighbour (acyclic)."""
    from collections import defaultdict
    for _ in range(4):
        n = int(labels.max()) + 1
        lb = labels.ravel()
        of = work.reshape(-1, 3).astype(np.float64)
        cnt = np.maximum(np.bincount(lb, minlength=n), 1)
        rgb = np.stack([np.bincount(lb, weights=of[:, c], minlength=n) / cnt
                        for c in range(3)], 1)
        LAB = cv2.cvtColor(rgb.reshape(1, -1, 3).astype(np.uint8),
                           cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float64)
        area = np.bincount(lb, minlength=n)
        a = labels
        hl, hr = a[:, :-1].ravel(), a[:, 1:].ravel()
        vt, vb = a[:-1, :].ravel(), a[1:, :].ravel()
        mh, mv = hl != hr, vt != vb
        pl = np.concatenate([np.minimum(hl[mh], hr[mh]),
                             np.minimum(vt[mv], vb[mv])])
        pq = np.concatenate([np.maximum(hl[mh], hr[mh]),
                             np.maximum(vt[mv], vb[mv])])
        key = pl.astype(np.int64) * n + pq
        uk, uc = np.unique(key, return_counts=True)
        nbr = defaultdict(list)
        for k, cc in zip(uk.tolist(), uc.tolist()):
            r, q = divmod(k, n)
            nbr[r].append((q, cc)); nbr[q].append((r, cc))
        total = labels.size
        lut = np.arange(n)
        changed = False
        for r in np.argsort(area):
            if area[r] > max_area_frac * total or area[r] < 6:
                continue
            ns = sorted(nbr[r], key=lambda x: -x[1])
            if not ns:
                continue
            tgt = ns[0][0]
            if (float(np.linalg.norm(LAB[r] - LAB[tgt])) < de_max
                    and area[tgt] > area[r]):
                lut[r] = tgt; changed = True
        if not changed:
            break
        for i in range(n):
            while lut[i] != lut[lut[i]]:
                lut[i] = lut[lut[i]]
        labels = lut[labels]
        _, labels = np.unique(labels, return_inverse=True)
        labels = labels.reshape(a.shape).astype(np.int32)
    return labels


def unify_ink(centres: np.ndarray, lum_max: float = 55.0,
              chroma_max: float = 40.0) -> np.ndarray:
    """Give the OUTLINE one solid ink colour. color-last samples each dark
    outline segment locally, so AA bleeds neighbour colours in and the ink
    comes out a patchwork of dark tones. Snap every NEUTRAL-dark region
    (luminance < lum_max AND low chroma) to a single ink = their median, so the
    outline reads as one clean digital ink. Chromatic darks (navy eyes, dark
    coloured shadows) have chroma >= chroma_max and are left alone."""
    c = centres.astype(int)
    lum = 0.299 * c[:, 0] + 0.587 * c[:, 1] + 0.114 * c[:, 2]
    chroma = c.max(1) - c.min(1)
    ink = (lum < lum_max) & (chroma < chroma_max)
    if ink.any():
        centres = centres.copy()
        centres[ink] = np.median(centres[ink], axis=0)
    return centres


def _mode_smooth_fast(labels: np.ndarray, ksize: int) -> np.ndarray:
    """Majority (mode) filter on the label map — same result as the global
    vote, but computed PER REGION inside its own bounding box (+ksize margin),
    so cost is O(sum of bbox areas) ≈ O(pixels), not O(regions × pixels), and
    it never allocates the giant regions×H×W array."""
    from scipy import ndimage
    H, W = labels.shape
    n = int(labels.max()) + 1
    slices = ndimage.find_objects(labels + 1)
    best_score = np.zeros((H, W), np.float32)
    best_label = labels.copy()
    for r in range(n):
        sl = slices[r]
        if sl is None:
            continue
        y0 = max(0, sl[0].start - ksize); y1 = min(H, sl[0].stop + ksize)
        x0 = max(0, sl[1].start - ksize); x1 = min(W, sl[1].stop + ksize)
        v = cv2.boxFilter((labels[y0:y1, x0:x1] == r).astype(np.float32),
                          -1, (ksize, ksize))
        bs = best_score[y0:y1, x0:x1]
        upd = v > bs
        bs[upd] = v[upd]
        best_label[y0:y1, x0:x1][upd] = r
    return best_label


def guarded_smooth(labels: np.ndarray, centres: np.ndarray, work: np.ndarray,
                   passes: int, ksize: int) -> np.ndarray:
    """Smooth the SHAPE of each region (mode filter on the label map) so the
    sides of every filled polygon become clean curves instead of lumpy
    staircase — USER's "lines are polygons whose sides are clean". GUARDED:
    thin dark ink pixels are restored afterward wherever the smoothing tried to
    lighten them, so outlines are not eroded away. Fast per-bbox mode filter."""
    from scipy import ndimage
    lum = 0.299 * work[:, :, 0] + 0.587 * work[:, :, 1] + 0.114 * work[:, :, 2]
    dark = lum < 75
    dist = ndimage.distance_transform_edt(dark)
    thin_ink = dark & (dist <= 2.5)          # thin dark structures = outlines
    orig = labels.copy()
    lumc = (0.299 * centres[:, 0] + 0.587 * centres[:, 1]
            + 0.114 * centres[:, 2])
    out = labels
    for _ in range(max(1, passes)):
        out = _mode_smooth_fast(out, ksize)
        # protect ink each pass: never let a thin dark pixel go to a lighter label
        flip = thin_ink & (out != orig) & (lumc[np.clip(out, 0, len(lumc) - 1)]
                                           > lumc[orig])
        out[flip] = orig[flip]
    # compact labels so no empty region reaches recolor (kills the empty-slice
    # warning)
    _, out = np.unique(out, return_inverse=True)
    return out.reshape(labels.shape).astype(np.int32)


def recolor_from_interior(orig: np.ndarray, labels: np.ndarray,
                          erode: int) -> np.ndarray:
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
    p = {"work_dim": 1536, "group_color": 14.0, "group_space": 3.0,
         "fz_scale": 120.0, "min_area_frac": 1.1e-5, "merge_de": 7.0,
         "ink_lum": 55.0, "ink_chroma": 40.0,
         # smoothing level chosen by score_vs_recraft.py, NOT by eye:
         # p2/k5/sw11/t2 = best mean MS-SSIM (0.962); aggressive smoothing
         # (p4/k9/sw45/t6) distorted structure and scored worst (0.936).
         "smooth_passes": 2, "smooth_ksize": 5,
         "corner_deg": 155.0, "smooth_win": 21, "fit_tol": 4.0}
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
    else:
        work = img
    Hh, Ww = work.shape[:2]

    # 2. light colour group — gentle, coloured shadows survive
    group = cv2.bilateralFilter(work, d=0, sigmaColor=float(p["group_color"]),
                                sigmaSpace=float(p["group_space"]))
    if dump is not None:
        dump["01_group"] = group.copy()

    # 3. GENTLE segmentation — outlines survive as their own dark regions
    from skimage.segmentation import felzenszwalb
    lab = cv2.cvtColor(group, cv2.COLOR_RGB2LAB)
    min_size = max(6, int(round(p["min_area_frac"] * Hh * Ww)))
    fz = felzenszwalb(lab, scale=float(p["fz_scale"]), sigma=0.5,
                      min_size=min_size)
    _, labels = np.unique(fz, return_inverse=True)
    labels = labels.reshape(work.shape[:2]).astype(np.int32)

    # 4. AGGREGATE BY COLOUR — join same-colour fragments (kills noise seams,
    # leaves the differently-coloured dark outline alone)
    labels = merge_similar(labels, work, float(p["merge_de"]))

    # 4b. ABSORB TRANSITIONS — dissolve AA ramp fragments (halo bands, eye rim)
    # that colour-merge can't reach; also cuts region count ~5x
    labels = absorb_transitions(labels, work)

    # 4c. CLEANUP SLIVERS — dissolve small low-contrast leftover fragments
    # (soft-shading ghosts inside one colour) that 4b's ramp test misses
    labels = cleanup_slivers(labels, work)

    # 5. SMOOTH SHAPES — clean each polygon's sides (guarded so thin outlines
    # survive). Needs a first colouring to know which regions are ink.
    tmp = recolor_from_interior(work, labels, 1)
    labels = guarded_smooth(labels, tmp, work, int(p["smooth_passes"]),
                            int(p["smooth_ksize"]))

    # 6. colour last from the ORIGINAL, then UNIFY the outline ink to one solid
    # colour (patchy dark tones → one clean digital ink; navy eyes kept)
    centres = recolor_from_interior(work, labels, 1)
    centres = unify_ink(centres, float(p["ink_lum"]), float(p["ink_chroma"]))
    if dump is not None:
        dump["02_regions"] = centres[labels]

    # 6. aggregate GEOMETRY — smooth curve fit (loops_to_svg_curves: gentle
    # curves through the region boundaries; corner_deg high so organic blobs
    # round into smooth shapes instead of polygonising). Fill fitter, NOT
    # stroke machinery.
    import boundary
    edges, _ = boundary.build_edges(labels)
    loops = boundary.region_loops(edges, len(centres))
    return boundary.loops_to_svg_curves(labels, centres, edges, loops,
                                        tol=float(p["fit_tol"]),
                                        corner_deg=float(p["corner_deg"]),
                                        smooth_win=int(p["smooth_win"]),
                                        parsimony=0.0)
