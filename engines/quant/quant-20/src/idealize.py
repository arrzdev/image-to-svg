"""Raster idealization pre-pass: L0 gradient minimization.

Smooths a raster into clean piecewise-constant plateaus BEFORE quantization,
so JPEG block noise, ringing, and soft AO shadows never reach the vectorizer.
The fitter then refines against the IDEALIZED raster — the idealized image is
the ground truth we actually want to reproduce, not the compression mush.

Implements Xu, Lu, Xu & Jia, "Image Smoothing via L0 Gradient Minimization"
(SIGGRAPH Asia 2011) via half-quadratic splitting: alternate a closed-form
hard threshold on the (h, v) gradient pair with an FFT Poisson-style screen
solve, annealing the splitting weight beta by `kappa` each round.

API (pure numpy, no torch/cv2 dependency):
    out_rgb = idealize.l0(rgb_uint8, lam=0.02)      # HxWx3 uint8 in, out
    path    = idealize.l0_png(png_in, png_out, lam) # file-to-file helper

`lam` is the sparsity weight on gradient count: higher = fewer, larger
plateaus. Useful range for 1024px logo/illustration rasters: 0.01-0.03.
"""
from __future__ import annotations

import numpy as np

__all__ = ["l0", "l0_png"]


def l0(img, lam: float = 0.02, kappa: float = 2.0,
       beta_max: float = 1e5) -> np.ndarray:
    """L0 gradient minimization. img: HxW or HxWxC uint8 (or float in
    [0,255]). Returns uint8 array of the same shape: piecewise-constant
    plateaus, true edges preserved crisp, gradient count minimized.

    lam:      smoothing strength (0.01 gentle .. 0.03 aggressive).
    kappa:    beta annealing rate per iteration (paper default 2.0).
    beta_max: anneal stop; iterations = log_kappa(beta_max / (2 lam)) ~ 21.
    """
    arr = np.asarray(img)
    S = arr.astype(np.float32) / 255.0
    squeeze = S.ndim == 2
    if squeeze:
        S = S[..., None]
    H, W, _ = S.shape

    # OTFs of the circular forward-difference filters d/dx, d/dy
    ax = np.zeros((H, W), np.float32); ax[0, 0] = -1.0; ax[0, -1] = 1.0
    ay = np.zeros((H, W), np.float32); ay[0, 0] = -1.0; ay[-1, 0] = 1.0
    otfx = np.fft.fft2(ax)[..., None]
    otfy = np.fft.fft2(ay)[..., None]
    denom2 = np.abs(otfx) ** 2 + np.abs(otfy) ** 2
    FI = np.fft.fft2(S, axes=(0, 1))

    beta = 2.0 * lam
    while beta < beta_max:
        # gradient subproblem: closed-form L0 hard threshold, joint over
        # channels and the (h, v) pair
        h = np.roll(S, -1, axis=1) - S
        v = np.roll(S, -1, axis=0) - S
        kill = (h * h + v * v).sum(axis=2) < lam / beta
        h[kill] = 0.0
        v[kill] = 0.0
        # image subproblem: screened Poisson solve in Fourier space
        FS = (FI + beta * (np.conj(otfx) * np.fft.fft2(h, axes=(0, 1))
                           + np.conj(otfy) * np.fft.fft2(v, axes=(0, 1)))) \
            / (1.0 + beta * denom2)
        S = np.real(np.fft.ifft2(FS, axes=(0, 1))).astype(np.float32)
        beta *= kappa

    out = np.clip(S * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return out[..., 0] if squeeze else out


def l0_png(png_in: str, png_out: str, lam: float = 0.02,
           kappa: float = 2.0) -> str:
    """File-to-file convenience: idealize an RGB(A) png. Alpha, if present,
    is passed through untouched. Returns png_out."""
    from PIL import Image
    im = Image.open(png_in)
    if im.mode == "RGBA":
        rgba = np.asarray(im)
        rgb = l0(rgba[..., :3], lam, kappa)
        out = np.dstack([rgb, rgba[..., 3]])
    else:
        out = l0(np.asarray(im.convert("RGB")), lam, kappa)
    Image.fromarray(out).save(png_out)
    return png_out
