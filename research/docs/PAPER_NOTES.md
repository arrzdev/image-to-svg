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

## Batch-1 digests (agent extraction, 2026-07-10 — all 8 papers read from PDFs)

Corrections vs VECTORIZATION_PAPERS.md: "Layered Image Vectorization via
Semantic Simplification" is **arXiv 2406.05404v2** (2412.15673 is a
trajectory-prediction paper — fix the reference sheet when next edited).

### Layered Image Vectorization via Semantic Simplification (2406.05404)
Simplification tool = SDS "feature-average effect" on the pixels themselves
(unconditional/empty prompt so shapes don't distort); snapshots every 20
iters → 5-image simplification sequence. SAM-segment EVERY level; each mask
goes into the furthest-back layer where it doesn't intersect that layer's
masks → back-to-front stack, macro shapes at the bottom. Boundaries
Douglas-Peucker'd → closed cubics. Stage I fits shape-only (per-layer MSE +
overlap penalty `L_overlap = Σ ReLU(θ−α(p))`), Stage II freezes structure,
fits colors, adds LIVE-style refinement paths on top-K error components,
periodic redundant-vector cleanup. Beats DiffVG/LIVE/O&R/SGLIVE on MSE+LPIPS;
"Vector Compactness" = fraction of primitives ≥85% inside one semantic mask.
KEY CLASSICAL TAKEAWAY: decide region TOPOLOGY on a simplified image
(edge-preserving cascade), refine colors/details within that structure —
gradients can't fragment because they never define topology.

### Depixelizing Pixel Art (Kopf & Lischinski 2011)
Similarity graph: 8-connected, cut edges when YUV Δ > (48,7,6)/255.
Diagonal-crossing votes: curve-length continuation, sparse-pixels (smaller
component = foreground), island (never orphan 1px, weight 5). **Two-tier
edge classes: cell YUV distance ≤100/255 = SHADING edge, >100/255 = CONTOUR
edge; at T-junctions the two contour edges ALWAYS continue as one smooth
curve, the shading edge terminates on it.** Smoothness E_s=∫|κ|ds +
positional leash E_p=‖p−p̂‖⁴ (free micro-movement, hard wall on drift);
CORNER PATTERNS (quantized dictionary) are excluded from the smoothness
integral so corners survive smoothing.

### Potrace (Selinger 2003) — the straightness/corner semantics
- Straightness certificate: subpath is straight iff one segment approximates
  all points within ±½px AND ≤3 of the 4 pixel directions occur (kills
  staircase creep). Possible segment i→j requires extended p(i−1,j+1)
  straight.
- Optimal polygon: fewest segments, tie-break P_ij = |v_j−v_i| · stddev of
  point distances (O(1) prefix moments), cyclic lexicographic DP.
- Vertex adjust: least-squares line per side (centroid + dominant
  eigenvector), vertex = intersection clamped to ±½px.
- **Corner test (alphamax): α = 4γ/3 from the unit-square parallel-line
  construction; α ≥ αmax(=1.0) → SHARP corner (two straight segments);
  α < 1 → convex Bézier, α clamped [0.55, 1]. Property: long segments
  meeting at a slight angle still corner — drawing intent encoded.**
- Curve optimization: merge same-convexity runs (<179° turn) fixing the new
  α by EQUAL ENCLOSED AREA (standardized Bézier area = (3/10)(2α+2β−αβ)),
  accept on tangency tolerance.
- Why idealized: every decision carries an explicit ±½px tolerance band —
  noise inside the band cannot reach the output by construction.

### SuperSVG (CVPR 2024)
Superpixels + coarse/refine ViT; path-efficiency loss + boundary loss
(needed to hide patch seams); Dynamic Path Warping for path-sequence
alignment. Lessons: per-region processing needs explicit seam handling;
parsimony via explicit path-efficiency penalties.

### VectorArk (Adobe 2026)
- **Rounded-polygon representation**: lines + circular arcs (Cornucopia G1
  fit); knots (x, y, d), r = d·tan(α/2), d=−1 = sharp vertex; arcs split at
  120°. Straightness structural, corners one scalar, ~30-45% more compact
  than cubics.
- **Outline normalization**: geometry decided on a decolorized fixed-width
  outline render of a first-pass trace; colors + z-order re-attached from
  the source afterward (geometry/styling decoupled).
- **Degradation model**: training pairs = clean SVG rendered small+blurred →
  classical trace (imperfect input) vs clean geometry (target). "Without it
  the model faithfully reproduces the imperfections of the input raster" =
  the formal statement of our Recraft gap. Classically usable as an
  idealization REGRESSION SUITE: render recraft targets degraded → run our
  engine → diff vs the clean geometry.
- Criticizes classical tracers: "treat all color transitions equally →
  over-segmentation and redundant paths" (= our E1, named).

### Deep Vectorization of Technical Drawings (ECCV 2020)
Clean → estimate → refine → merge. Cleaning to a BILEVEL ideal (ink vs
background, gaps infilled, noise removed) — vectorize only the idealized
intermediate. Refinement: primitives attracted to ink, REPELLED by each
other's overlap (two strokes can't collapse onto one line — our 0a/0b weld
family). IoU 86-88% vs ≤60% competitors.

### Image Vectorization: a Review (2306.06441)
LIVE most accurate/path but ~2h@1080p; DiffVG fast but path-hungry;
VTracer best overall quality+speed, path count only indirectly
controllable. The field's open problem = ours verbatim: no method both
picks a small path budget automatically AND idealizes. Implied
recommendation: segment-first backbone + light optimization as validator.

## TRANSFERABLE IDEAS (ranked, mapped to our root causes)

1. **(E3/E1) Two-tier edge classes + T-junction rule** (Depixelizing):
   merge-level vs contour-level thresholds; dissolve shading edges inside
   contour-bounded super-regions (average the colors); at T-junctions
   contour edges continue, shading edges terminate. → quantize/despeckle.
2. **(E4/E5) Potrace alphamax + straightness certificate** in the
   fill/boundary fitter; corners favored by long segments at slight angles.
3. **(E1/E7) Decide colors LAST** (VectorArk/Layered): geometry on a
   normalized view; per-region colors re-extracted from source (eroded
   means — run-33 lead, now literature-confirmed).
4. **(E2/topology) Simplification-sequence guidance** (Layered): region
   topology from an edge-preserving simplified level; details only refine.
5. **(idealization QA) Degradation regression suite** (VectorArk): render
   recraft SVGs degraded, trace, diff vs clean — automated idealization
   test that eye-only judging can't scale to.
6. **(E3) Overlap repulsion** (DeepVec/Layered) between same-layer shapes;
   LIVE Xing check as cubic validity repair.
7. **(E5) Corner-pattern exclusion from smoothing + ‖p−p̂‖⁴ leash**
   (Depixelizing) as the "make it look drawn" post-pass.

## Pending digests

Batch 2 (loop/judge: Render-in-the-Loop, Rendering-aware RL, Reason-SVG,
LayerTracer, AmodalSVG, DuetSVG, Chat2SVG) — **agent cancelled by USER
2026-07-10; not relaunched.** If those digests become needed (idealization
judge design, E8 layering), ask the USER before re-dispatching.
