"""ideal-3 — ideal-1 fills + carve original-dark ink as BLACK FILLS + gentle merge.

USER feedback on ideal-1/ideal-2 (2026-07-09): ideal-1 is almost perfect; its
ONLY defect is that black outlines take neighbour colours in places. ideal-2
went the wrong way by bolting on quant-11's STROKE machinery (over-processed).
The right fix stays in ideal-1's fills world:

  "for every region of those red lines, look at the ORIGINAL pixels underneath,
   grab the right colour and apply it — while also averaging so sections with
   almost the same colour are joined, but don't make the average too aggressive."

Why ideal-1 failed: the mean-shift idealize LIGHTENS thin dark lines and the
segmentation then MERGES them into the light neighbour, so there is no dark
region left to colour — colour-last samples the light interior. Recraft's
outlines are black because at "what colour is each region" the source is black
there; they only look right because the dark region still EXISTS.

ideal-3 keeps ideal-1 exactly, and:
  * carves the ORIGINAL-dark ink into its OWN regions BEFORE colouring (so
    colour-last makes them black — kept as FILLS, never stroked), and
  * does a GENTLE same-colour region merge (join near-identical fills, reduce
    fragmentation) — not aggressive, so real colour breaks survive.

No quant stroke machinery. Emission = ideal-1's fills-only layered emitter.
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


def measure_scale(img: np.ndarray) -> float:
    return float(np.clip(max(img.shape[:2]) / 256.0, 2.0, 24.0))


def idealize(img: np.ndarray, scale: float) -> np.ndarray:
    a = cv2.bilateralFilter(img, d=0, sigmaColor=18,
                            sigmaSpace=max(2.0, scale * 0.6))
    sp = float(np.clip(scale * 1.2, 6, 40))
    a = cv2.pyrMeanShiftFiltering(a, sp=sp, sr=24.0, maxLevel=2)
    return a


def local_regions(simp: np.ndarray, tol: float, min_area: int) -> np.ndarray:
    from skimage.segmentation import felzenszwalb
    lab = cv2.cvtColor(simp, cv2.COLOR_RGB2LAB)
    fz = felzenszwalb(lab, scale=float(tol) ** 2, sigma=0.5,
                      min_size=int(min_area))
    _, labels = np.unique(fz, return_inverse=True)
    return labels.reshape(simp.shape[:2]).astype(np.int32)


def detect_ink(work: np.ndarray, scale: float, dark_lum: float) -> np.ndarray:
    """The truly-dark ink in the ORIGINAL (not the washed idealized image).

    Thin 1px lines MUST survive (they are the outline), so we do NOT
    morphologically open — that erases them. Instead drop only tiny isolated
    speckles by connected-component area, which keeps long thin lines."""
    lum = (0.299 * work[:, :, 0] + 0.587 * work[:, :, 1]
           + 0.114 * work[:, :, 2])
    ink = (lum < dark_lum).astype(np.uint8)
    # close 1px gaps so the outline is FEW connected pieces (fewer paths),
    # then keep a component if big enough OR elongated (a real thin line has
    # small area but large bbox extent) — drops compact AA speckle, preserves
    # 1px outlines.
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    area = stats[:, cv2.CC_STAT_AREA]
    ext = np.maximum(stats[:, cv2.CC_STAT_WIDTH], stats[:, cv2.CC_STAT_HEIGHT])
    speck = max(20, int(round(scale * scale * 2)))
    line_len = max(10, int(round(scale * 4.0)))
    keep = np.zeros(n, bool)
    keep[1:] = (area[1:] >= speck) | (ext[1:] >= line_len)
    return keep[lbl]


def ink_overlay_svg(work: np.ndarray, ink: np.ndarray, scale: float) -> str:
    """Emit the ink as BLACK FILLED shapes painted ON TOP of the fills — a
    layer, not a cut. Fills span underneath untouched (no fragmentation);
    the ink is one evenodd path (holes handled) coloured by the ORIGINAL's
    own dark tone (grab-from-underneath, gently averaged to one ink colour).
    NOT stroked — filled, so it keeps the drawn line's real thickness."""
    u = ink.astype(np.uint8)
    cnts, _ = cv2.findContours(u, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    eps = max(0.6, scale * 0.12)
    subpaths = []
    for c in cnts:
        a = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
        if len(a) < 3:
            continue
        subpaths.append("M " + " L ".join(f"{x} {y}" for x, y in a) + " Z")
    if not subpaths:
        return ""
    col = np.median(work[ink], axis=0).astype(int) if ink.any() else [10, 10, 10]
    hexc = "#%02x%02x%02x" % (int(col[0]), int(col[1]), int(col[2]))
    return (f'<path d="{" ".join(subpaths)}" fill="{hexc}" '
            f'fill-rule="evenodd"/>')


def recolor_from_interior(orig: np.ndarray, labels: np.ndarray,
                          erode: int) -> np.ndarray:
    """Each region's colour = median of the ORIGINAL over its eroded interior
    (thin regions fall back to their own pixels). Ink regions → black."""
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


def merge_similar(labels: np.ndarray, centres: np.ndarray, orig: np.ndarray,
                  de: float) -> tuple:
    """GENTLE join: union adjacent regions whose fill colours are within `de`
    (LAB). Not aggressive — real colour breaks (ink vs fill, distinct hues)
    are far above `de` and survive. Re-colours merged regions from the
    ORIGINAL so the join is a true area-weighted tone, not a drift."""
    n = len(centres)
    lab = cv2.cvtColor(centres.reshape(1, -1, 3),
                       cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float64)

    # vectorised adjacency: unique neighbouring (r,q) label pairs
    a = labels
    hp = np.stack([a[:, :-1].ravel(), a[:, 1:].ravel()], 1)
    vp = np.stack([a[:-1, :].ravel(), a[1:, :].ravel()], 1)
    pr = np.vstack([hp, vp])
    pr = pr[pr[:, 0] != pr[:, 1]]
    pr = np.sort(pr, axis=1)
    pr = np.unique(pr, axis=0)

    parent = np.arange(n)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    d2 = de * de
    for r, q in pr:
        if ((lab[r] - lab[q]) ** 2).sum() <= d2:
            ra, rb = find(int(r)), find(int(q))
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    roots = np.array([find(i) for i in range(n)])
    _, new = np.unique(roots, return_inverse=True)
    labels2 = new[labels].astype(np.int32)
    centres2 = recolor_from_interior(orig, labels2, 1)
    return labels2, centres2


def run_pipeline(image_path: str, params: dict,
                 dump: Dict[str, np.ndarray] = None) -> str:
    p = {"work_dim": 1024, "tol": 11.0, "min_area_frac": 0.0008,
         "erode_frac": 0.004, "parsimony": 1.0, "dark_lum": 80.0,
         "merge_de": 8.0}
    p.update(params or {})

    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"cannot read {image_path}")
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    H0, W0 = img.shape[:2]
    wd = int(p["work_dim"])
    s = wd / max(H0, W0)
    interp = cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC
    work = cv2.resize(img, (max(1, round(W0 * s)), max(1, round(H0 * s))),
                      interpolation=interp) if abs(s - 1) > 1e-3 else img
    Hh, Ww = work.shape[:2]
    scale = measure_scale(work)

    simp = idealize(work, scale)
    if dump is not None:
        dump["01_idealized"] = simp.copy()

    min_area = max(24, int(p["min_area_frac"] * Hh * Ww))
    labels = local_regions(simp, p["tol"], min_area)

    # colour LAST from the ORIGINAL eroded interior. Fills span the WHOLE area
    # (ink not carved) — the interior sample sits away from the boundary ink,
    # so fills come out clean and stay ONE piece each (no fragmentation).
    erode = max(1, int(p["erode_frac"] * max(Hh, Ww)))
    centres = recolor_from_interior(work, labels, erode)
    if dump is not None:
        dump["02_fills_recolored"] = centres[labels]

    # GENTLE same-colour merge (join near-identical fills; not aggressive)
    labels, centres = merge_similar(labels, centres, work, p["merge_de"])
    if dump is not None:
        dump["03_fills_merged"] = centres[labels]

    # FILLS layered emission (ideal-1 backend, NO stroke machinery)
    import boundary
    from contours_exp import _fill_svg_corner_pinned
    edges, _ = boundary.build_edges(labels)
    loops = boundary.region_loops(edges, len(centres))
    fills_svg = _fill_svg_corner_pinned(labels, centres, edges, loops,
                                        parsimony=p["parsimony"], stats={})

    # INK LAYER on top: black filled shapes from the ORIGINAL-dark network,
    # coloured from underneath. Painted last = over the fills.
    ink = detect_ink(work, scale, p["dark_lum"])
    if dump is not None:
        v = work.copy(); v[ink] = (255, 0, 0); dump["04_ink_layer"] = v
    ink_svg = ink_overlay_svg(work, ink, scale)
    svg = fills_svg.replace("</svg>", ink_svg + "</svg>") if ink_svg \
        else fills_svg
    return svg
