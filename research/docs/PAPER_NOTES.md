# Paper notes — extraction digests for the idealization engine

_Deep-read digests of research/docs/VECTORIZATION_PAPERS.md entries, mined for
mechanisms this classical pipeline can adopt. Populated 2026-07-10; more
digests append as the paper-mining agents report._

## LIVE — Towards Layer-wise Image Vectorization (CVPR 2022) [full extraction]

Model-free, direct optimization of closed cubic Béziers with DiffVG. What
transfers to us:

- **Component-wise init (classically runnable, no optimization needed):**
  L1 color diff current-vs-target → reject residual < c_α=0.1 → quantize the
  remaining residual into 200 bins → largest connected component → its center
  of mass gets the next path (circle init r=5px, color from the component).
  "One component = one connected area of uniform color." This is a recipe for
  **region-to-one-shape + z-order for free**: emit largest-first,
  background at the bottom, details on top (their layer order emerges purely
  from residual size ranking). → our E8 layered emission.
- **UDF loss (boundary-band scoring):** per-pixel weight
  `d'_i = ReLU(τ−|d_i|)/Σ ReLU(τ−|d_j|)` (τ=10px), loss = weighted MSE in
  the ±τ band around the contour only. Fixes MSE's mean-color bias (their
  Fig 2: yellow face RGB(244,196,72) → MSE converges to muddy (108,126,152);
  UDF gets (244,197,87)). **Classical translation: judge/refit a region
  boundary and pick its fill color from a contour band, not whole-region
  means — resists exactly the AA/occluder contamination behind our E7 drift
  and E1 shrapnel ownership.**
- **Xing loss / validity check:** a cubic segment self-intersects iff its
  control polygon does (angle test on AB→ vs CD→: D1=𝟙(AB×BC), D2=sinθ;
  L=D1·ReLU(−D2)+(1−D1)·ReLU(D2), λ=0.01). Cheap post-fit sanity check for
  our fitted cubics (bowtie repair).
- **Schedule:** paths added 1,2,4,8,16,32/stage, 4 segments per path, all
  paths re-optimized each stage; Adam lr 1.0 (points) / 0.01 (colors), 500
  iters. Path budget = the idealization knob (recognizable at N=8-16).
- **Gradients:** NOT handled (solid RGBA only; "gradient color… future
  work") — consistent with our flatten-first rule (VISION item 3).
- **Their critique of segmentation-first pipelines (us):** heavy
  pre-processing; "high-contrast texture segmented into multiple small
  regions, resulting in redundancy" — that is our E1 shrapnel, named in 2022.
- Limits: slow (500 iters × stages, all paths re-optimized), no
  straight/corner notion (everything cubic), complex topology punted to
  amodal segmentation.

## Pending digests

Batch 1 (idealization): Layered Semantic Simplification, Depixelizing Pixel
Art, Potrace corner semantics, SuperSVG, VectorArk, Deep Vectorization of
Technical Drawings (cleaning stage), Vectorization Review.
Batch 2 (loop/judge: Render-in-the-Loop, Rendering-aware RL, Reason-SVG,
LayerTracer, AmodalSVG, DuetSVG, Chat2SVG) — **agent cancelled by USER
2026-07-10; not relaunched.** If those digests become needed (idealization
judge design, E8 layering), ask the USER before re-dispatching.
