"""Quality + complexity metrics for a generated SVG vs. the source raster.

The headline number is `quality` in [0, 1]: a weighted geometric mean of three
perceptual components, each measuring a different failure mode:

  - ms_ssim    structure/layout across scales  (blur, gross shape errors)
  - color_score  perceptual color error (CIEDE2000, Lab)  (wrong/quantized hues)
  - edge_score   gradient-magnitude similarity (GMSD)  (lost detail, faceting)

Geometric mean means any single component collapsing drags the whole score
down, so a result can't hide a destroyed edge behind a good color match. All
components are exposed individually so an optimization loop can target one.
"""
from __future__ import annotations

import gzip
import re
from typing import Optional

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim
from skimage.color import rgb2lab, deltaE_ciede2000

from render import svg_to_rgb

# Compute perceptual metrics at this long-side. Robust to modest downscaling and
# keeps CIEDE2000 (the expensive one) fast enough for interactive comparison.
METRIC_DIM = 768

# Weights for the composite quality score (must sum to 1).
# `local` exists because global means hide local catastrophes: a missing cloud
# or a recolored mountain face is ~1% of pixels (invisible to mean SSIM/dE) but
# perceptually severe. It scores the WORST small region, so dropped objects
# tank the composite even when the rest of the image matches.
_W_STRUCT, _W_COLOR, _W_EDGE, _W_LOCAL = 0.35, 0.25, 0.25, 0.15

# Local-completeness window (px at metric resolution) and the dE at which a
# worst-region is considered fully failed.
_LOCAL_WIN = 32
_LOCAL_FAIL_DE = 14.0

# Stroke coherence: measure edge jaggedness — the fraction of Canny edge
# length that disappears under a small median filter — on the SVG render, and
# score the EXCESS over the source's own jaggedness at the same resolution.
# Ragged multi-patch strokes (a line drawn as many little blocks) add
# jaggedness the source doesn't have; intrinsically detailed content (texture,
# text) is jagged in BOTH and is not penalized. Reference-free scoring wrongly
# flagged dense-detail images (game-assets sheets scored 0.17 while looking
# perfect) — hence source-relative.
_COHERENCE_DIM = 1536
_COHERENCE_SCALE = 0.05
_W_COHERENCE = 0.10  # quality = fidelity_composite^0.90 * coherence^0.10

# MS-SSIM scale weights (Wang et al.).
_MS_WEIGHTS = np.array([0.0448, 0.2856, 0.3001, 0.2363, 0.1333])

# Matches a single path command letter + its parameter blob.
_CMD_RE = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)")
_NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _count_points_in_d(d: str) -> int:
    """Count coordinate vertices (anchor points) in a path 'd' string.

    We count implicit endpoints per command, ignoring control handles, so the
    number reflects editable vertices rather than raw numeric density.

    Numbers are counted by whitespace splitting rather than a numeric regex —
    ~5x faster on the multi-MB path data that high-fidelity traces produce.
    All our generators emit space-delimited coordinates; commas are normalized
    first so standard SVG comma syntax still counts correctly.
    """
    if "," in d:
        d = d.replace(",", " ")
    pts = 0
    for cmd, blob in _CMD_RE.findall(d):
        c = cmd.lower()
        if c == "z":
            continue
        n = len(blob.split())
        if c in ("m", "l", "t"):
            pts += n // 2
        elif c in ("h", "v"):
            pts += n
        elif c in ("s", "q"):
            pts += n // 4
        elif c == "c":
            pts += n // 6
        elif c == "a":
            pts += n // 7
    return pts


def _palette_stats(svg: str) -> dict:
    """Editability signals from the fill palette itself.

    A professional, editable asset uses FEW colors that are all perceptually
    distinct (Recraft: ~10 fills, all 20+ dE apart). Near-duplicate fills mean
    one visual element is painted as stacked fragments of slightly different
    shades — high pixel fidelity, terrible editability. Reported (not yet
    weighted into `quality`).
    """
    fills = set(re.findall(r'fill="(#[0-9a-fA-F]{6})"', svg))
    n = len(fills)
    if n < 2:
        return {"num_fills": n, "palette_min_de": None}
    cols = np.array([[int(f[1:3], 16), int(f[3:5], 16), int(f[5:7], 16)]
                     for f in sorted(fills)][:64], dtype=np.float64)
    lab = rgb2lab(cols.reshape(1, -1, 3) / 255.0)[0]
    min_de = np.inf
    for i in range(len(lab)):
        de = deltaE_ciede2000(lab[i][None, None, :], lab[i + 1:][None, :, :])
        if de.size:
            min_de = min(min_de, float(de.min()))
    return {"num_fills": n, "palette_min_de": round(min_de, 1)}


def structural_metrics(svg: str) -> dict:
    paths = re.findall(r"<path\b[^>]*\bd=\"([^\"]*)\"", svg)
    num_paths = len(paths)
    num_points = sum(_count_points_in_d(d) for d in paths)
    raw = svg.encode("utf-8")
    out = {
        "num_paths": num_paths,
        "num_points": num_points,
        "points_per_path": round(num_points / num_paths, 1) if num_paths else 0,
        "size_bytes": len(raw),
        "gzip_bytes": len(gzip.compress(raw)),
    }
    out.update(_palette_stats(svg))
    return out


def _to_metric_size(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    scale = min(1.0, METRIC_DIM / max(h, w))
    if scale < 1.0:
        img = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    return img


def _gray01(rgb: np.ndarray) -> np.ndarray:
    return (rgb[..., :3] @ np.array([0.299, 0.587, 0.114])) / 255.0


def _ms_ssim(a: np.ndarray, b: np.ndarray) -> float:
    """Multi-scale SSIM: weighted geometric mean of SSIM over an image pyramid."""
    vals = []
    ca, cb = a, b
    for i in range(len(_MS_WEIGHTS)):
        if min(ca.shape[:2]) < 8:                 # too small for the SSIM window
            vals.append(vals[-1] if vals else 1.0)
        else:
            vals.append(float(ssim(ca, cb, channel_axis=2, data_range=255)))
        if i < len(_MS_WEIGHTS) - 1:
            ca = cv2.pyrDown(ca)
            cb = cv2.pyrDown(cb)
    vals = np.clip(np.array(vals), 1e-6, 1.0)
    return float(np.prod(vals ** _MS_WEIGHTS))


def _gmsd(a_rgb: np.ndarray, b_rgb: np.ndarray):
    """Gradient Magnitude Similarity. Returns (edge_similarity, deviation)."""
    a = _gray01(a_rgb.astype(np.float64))
    b = _gray01(b_rgb.astype(np.float64))
    hx = np.array([[1, 0, -1], [1, 0, -1], [1, 0, -1]], dtype=np.float64) / 3.0
    hy = hx.T
    ga = np.hypot(cv2.filter2D(a, -1, hx), cv2.filter2D(a, -1, hy))
    gb = np.hypot(cv2.filter2D(b, -1, hx), cv2.filter2D(b, -1, hy))
    c = 0.0026
    gms = (2 * ga * gb + c) / (ga ** 2 + gb ** 2 + c)
    return float(gms.mean()), float(gms.std())


def _color_error(a_rgb: np.ndarray, b_rgb: np.ndarray):
    """Perceptual color difference (CIEDE2000).

    Returns (mean_dE, p95_dE, worst_region_dE) where worst_region_dE is the
    p99.5 of the box-filtered dE map — the mean error of the worst ~32px
    window. Missing objects (a cloud, a recolored face) make an entire window
    wrong, while mere edge misalignment only pollutes a thin sliver of any
    window, so this isolates true local destruction from boundary noise.
    """
    la = rgb2lab(a_rgb.astype(np.float64) / 255.0)
    lb = rgb2lab(b_rgb.astype(np.float64) / 255.0)
    de = deltaE_ciede2000(la, lb)
    box = cv2.boxFilter(de, -1, (_LOCAL_WIN, _LOCAL_WIN))
    return float(de.mean()), float(np.percentile(de, 95)), float(np.percentile(box, 99.5))


def _jaggedness(gray: np.ndarray) -> float:
    e1 = float((cv2.Canny(gray, 40, 120) > 0).sum())
    if e1 < 1:
        return 0.0
    e2 = float((cv2.Canny(cv2.medianBlur(gray, 5), 40, 120) > 0).sum())
    return max(0.0, 1.0 - e2 / e1)


def _stroke_coherence(svg: str, source_rgb: np.ndarray) -> tuple:
    """(coherence_score, excess_jaggedness). Source-relative: penalizes only
    jaggedness the render ADDS beyond the source's own edge character."""
    h, w = source_rgb.shape[:2]
    scale = _COHERENCE_DIM / max(h, w)
    W, H = max(2, round(w * scale)), max(2, round(h * scale))
    try:
        r = svg_to_rgb(svg, W, H)
    except Exception:
        return 1.0, 0.0
    g_r = cv2.cvtColor(r, cv2.COLOR_RGB2GRAY)
    src_big = cv2.resize(source_rgb, (W, H), interpolation=cv2.INTER_LANCZOS4)
    g_s = cv2.cvtColor(src_big, cv2.COLOR_RGB2GRAY)
    excess = max(0.0, _jaggedness(g_r) - _jaggedness(g_s))
    return float(np.exp(-excess / _COHERENCE_SCALE)), excess


def fidelity_metrics(svg: str, source_rgb: np.ndarray) -> dict:
    """Perceptual quality of the rendered SVG vs. the source image."""
    src = _to_metric_size(source_rgb)
    h, w = src.shape[:2]
    try:
        rendered = svg_to_rgb(svg, w, h)
    except Exception as e:  # rendering can fail on exotic SVG features
        return {"quality": None, "ssim": None, "psnr": None, "render_error": str(e)}

    a = src.astype(np.float64)
    b = rendered.astype(np.float64)

    mse = float(np.mean((a - b) ** 2))
    psnr = float(10 * np.log10((255.0 ** 2) / mse)) if mse > 0 else 99.0
    plain_ssim = float(ssim(src, rendered, channel_axis=2, data_range=255))
    ms = _ms_ssim(src, rendered)
    edge_sim, gmsd = _gmsd(src, rendered)
    mean_de, p95_de, worst_de = _color_error(src, rendered)

    # Map raw measures to [0, 1] "scores" (higher = better).
    color_score = max(0.0, 1.0 - mean_de / 20.0)   # dE ~2.3 = JND; 20 = very off
    edge_score = max(0.0, min(1.0, edge_sim))
    struct_score = max(0.0, min(1.0, ms))
    local_score = max(0.0, min(1.0, 1.0 - worst_de / _LOCAL_FAIL_DE))
    coherence, jag = _stroke_coherence(svg, source_rgb)  # full eval res, not the 768 copy

    fidelity = ((struct_score ** _W_STRUCT) * (color_score ** _W_COLOR)
                * (edge_score ** _W_EDGE) * (max(local_score, 1e-6) ** _W_LOCAL))
    quality = (fidelity ** (1.0 - _W_COHERENCE)) * (max(coherence, 1e-6) ** _W_COHERENCE)

    return {
        "quality": round(float(quality), 4),
        "coherence": round(float(coherence), 4),
        "jaggedness": round(float(jag), 4),
        "ms_ssim": round(ms, 4),
        "color_score": round(color_score, 4),
        "edge_score": round(edge_score, 4),
        "local_score": round(local_score, 4),
        "worst_region_de": round(worst_de, 2),
        "delta_e": round(mean_de, 2),
        "delta_e_p95": round(p95_de, 2),
        "gmsd": round(gmsd, 4),
        "ssim": round(plain_ssim, 4),
        "psnr": round(psnr, 2),
    }


def all_metrics(svg: str, source_rgb: Optional[np.ndarray]) -> dict:
    m = structural_metrics(svg)
    if source_rgb is not None:
        m.update(fidelity_metrics(svg, source_rgb))
    return m
