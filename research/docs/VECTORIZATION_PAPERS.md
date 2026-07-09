# Image Vectorization Research — Reference Sheet
(USER-compiled 2026-07-09; the loop mines this for approaches. Keep verbatim.)

A working reference for image-to-SVG / vectorization research: links, core
formulas, benchmark numbers, and each paper's stated conclusion. Grouped by
approach. Papers most relevant to a render-in-the-loop idealization engine are
flagged **[loop-relevant]**.
---
## 0. Raw PDF links — full index
Every paper, direct PDF. (arXiv PDFs use `arxiv.org/pdf/{id}`; the `.pdf`
suffix is optional and omitted here since arXiv redirects either way.)
**Foundational renderer**
- DiffVG — https://people.csail.mit.edu/tzumao/diffvg/diffvg.pdf
- Differentiable MC Ray Tracing through Edge Sampling (DiffVG's math basis) — https://arxiv.org/pdf/1804.09865
**Optimization-based (layer-wise)**
- LIVE — https://arxiv.org/pdf/2206.04655
- Layered Image Vectorization via Semantic Simplification — https://arxiv.org/pdf/2412.15673
- SAMVG — https://arxiv.org/pdf/2311.05276
**Learning-based / feed-forward**
- SuperSVG — https://arxiv.org/pdf/2406.09794
- Im2Vec — https://arxiv.org/pdf/2102.02798
- Deep Vectorization of Technical Drawings — https://arxiv.org/pdf/2003.05471
- VectorArk — https://arxiv.org/pdf/2605.24398
**LLM / multimodal SVG code generation**
- StarVector — https://arxiv.org/pdf/2312.11556
- OmniSVG — https://arxiv.org/pdf/2504.06263
- Chat2SVG — https://arxiv.org/pdf/2411.16602 (CVPR open-access mirror: https://openaccess.thecvf.com/content/CVPR2025/papers/Wu_Chat2SVG_Vector_Graphics_Generation_with_Large_Language_Models_and_Image_CVPR_2025_paper.pdf)
- LayerTracer — https://arxiv.org/pdf/2502.01105
- Empowering LLMs to Understand and Generate Complex Vector Graphics — https://arxiv.org/pdf/2412.11102
**Newest (late 2025 / 2026)**
- Render-in-the-Loop — https://arxiv.org/pdf/2604.20730
- Rendering-aware RL for Vector Graphics Generation — https://arxiv.org/pdf/2505.20793
- Reason-SVG — https://arxiv.org/pdf/2505.24499
- AmodalSVG — https://arxiv.org/pdf/2604.10940
- InternSVG — https://arxiv.org/pdf/2510.11341
- DuetSVG — https://arxiv.org/pdf/2512.10894
- RoboSVG — https://arxiv.org/pdf/2510.22684
- DOGE (Bezier-graph optimization) — https://arxiv.org/pdf/2511.19850
**Surveys & benchmarks**
- Image Vectorization: a Review — https://arxiv.org/pdf/2306.06441
- VectorGym — https://arxiv.org/pdf/2603.29852
- SVGenius — https://arxiv.org/pdf/2506.03139
**Classical baselines**
- Potrace (tech report) — https://potrace.sourceforge.net/potrace.pdf
- Depixelizing Pixel Art — https://johanneskopf.de/publications/pixelart/paper/pixel.pdf
- VTracer — code only: https://github.com/visioncortex/vtracer
> Verification status: all IDs here were confirmed via search **except** two I
> matched from citation records but could not independently re-confirm at fetch
> time — **Layered Semantic Simplification (2412.15673)** and **SVGenius
> (2506.03139)**. If either 404s, search the exact title on arXiv; the top hit is
> correct. (Chat2SVG 2411.16602 and Empowering LLMs 2412.11102 were both verified
> against the OmniSVG reference list and direct search.)
---
## 1. Foundational renderer
### DiffVG — Differentiable Vector Graphics Rasterization for Editing and Learning
Li, Lukáč, Gharbi, Ragan-Kelley. ACM TOG / SIGGRAPH Asia 2020.
- Paper (PDF): https://people.csail.mit.edu/tzumao/diffvg/diffvg.pdf
- ACM: https://dl.acm.org/doi/abs/10.1145/3414685.3417871
- Code: https://github.com/BachiLi/diffvg
**Core idea.** Vector rasterization becomes differentiable *after pixel
prefiltering*. Define the vector scene as `f(x, y; Θ)` for parameters Θ (control
points, colors, stroke widths). The prefiltered (anti-aliased) pixel value is a
convolution of the scene with kernel `k` over the filter support `A`:
```
I(x, y) = ∬_A  k(u, v) · f(x − u, y − v; Θ)  du dv
```
The gradient w.r.t. Θ:
```
∂I(x, y)/∂Θ = ∂/∂Θ  ∬_A k(u, v) f(x − u, y − v; Θ) du dv
```
`f` is discontinuous at shape boundaries, so you cannot swap ∂/∂Θ inside the
integral directly. DiffVG offers two evaluations:
- **Monte Carlo sampling** (better quality): discretize the pixel integral by
  sampling `N` points `uᵢ` around `x`,  `I(x) ≈ (1/N) Σᵢ k(uᵢ) f(x − uᵢ)`.
  Boundary discontinuities become Dirac deltas under differentiation, handled via
  an explicit **edge-sampling** correction term derived from the **Reynolds
  transport theorem** (extending Li et al. 2018's differentiable MC ray tracing to
  curves/strokes).
- **Analytical prefiltering** (faster, but conflation artifacts).
**Conclusion / significance.** First general differentiable rasterizer bridging
vector ↔ raster domains. It is the substrate almost every optimization-based and
many learning-based methods build on (LIVE, SuperSVG, VectorFusion, CLIPasso,
DiffSketcher, etc.). Enables any raster-space loss (MSE, LPIPS, CLIP) to
backprop into path parameters.
---
## 2. Optimization-based (layer-wise)
### LIVE — Towards Layer-wise Image Vectorization
Ma, Zhou, Xu, Sun, Filev, Orlov, Fu, Shi. CVPR 2022 (Oral). **[loop-relevant]**
- Abstract: https://arxiv.org/abs/2206.04655
- PDF: https://arxiv.org/pdf/2206.04655
- Code: https://github.com/Picsart-AI-Research/LIVE-Layerwise-Image-Vectorization
**Method.** Model-free (no trained net, no shape labels). Progressively adds
closed cubic Bézier paths in a coarse-to-fine loop, optimizing all paths at each
stage with DiffVG as the renderer. Three ingredients:
**(a) Component-wise path initialization.** Compute L1 color diff between current
render and target; reject diffs < `c_α` (= 0.1); quantize remaining into 200 bins;
find the largest connected component; place the new path (circle-initialized
control points, radius 5px) at its center of mass. Targets large *and* missing
regions rather than random/MSE placement.
**(b) UDF loss (Unsigned Distance guided Focal).** Fixes MSE's mean-color bias by
weighting pixels near the path contour. For per-pixel unsigned distance `dᵢ` to
the path, threshold τ (=10), flip, normalize:
```
d′ᵢ = ReLU(τ − |dᵢ|) / Σⱼ ReLU(τ − |dⱼ|)
L_UDF = (1/3) Σᵢ d′ᵢ Σ_c (I_{i,c} − Î_{i,c})²      (c over RGB)
```
**(c) Xing loss (self-crossing).** Prevents Bézier self-intersection by
constraining the angle between control-point segments AB and CD. With
`D₁ = 𝟙(AB × BC)` and `D₂ = (AB × CD)/(‖AB‖‖CD‖)`:
```
L_Xing = D₁ · ReLU(−D₂)  +  (1 − D₁) · ReLU(D₂)
```
Total: `L = L_UDF + λ · L_Xing`,  λ = 0.01.
**Benchmarks.** Introduced two eval sets: **Emoji** (134 NotoEmoji, 240×240) and
**Pics** (153 mixed clipart/fonts/icons). Metric = MSE vs. path count. LIVE beats
DiffVG substantially at *low* path counts (e.g. reconstructs a 4-component emoji
with 4 paths where DiffVG needs many more). User study (21 images, 20 users):
LIVE 73.8% preferred vs. DiffVG 14.3%, Neural Painting 11.9%.
**Conclusion.** Produces compact, human-editable, deterministically-ordered SVGs
with layer semantics matching human perception. **Limitation:** layer-wise
optimization is *slow* (per-image optimization; sequential passes) — the central
weakness later work attacks. Gradient-color paths and adaptive segment counts
left as future work.
### Layered Image Vectorization via Semantic Simplification
Wang, Huang, Sun, Gong, Cohen-Or, Lu. CVPR 2025.
- PDF: https://arxiv.org/pdf/2412.15673
- Progressively simplifies image semantics to build a clean, ordered layer stack.
  Same lineage as LIVE, better foreground/background separation.
### SAMVG — multi-stage vectorization with Segment-Anything
Zhu, Chong, Hu, Yi, Lai, Rosin. arXiv:2311.05276 (2023).
- https://arxiv.org/abs/2311.05276 — uses SAM masks to seed layer-wise
  optimization; a bridge between segmentation-first and optimization methods.
---
## 3. Learning-based / feed-forward
### SuperSVG — Superpixel-based Scalable Vector Graphics Synthesis
Hu, Yi, Qian, Zhang, Rosin, Lai. CVPR 2024. **[loop-relevant: two-stage self-teaching]**
- PDF: https://arxiv.org/pdf/2406.09794
- Code: https://github.com/sjtuplayer/SuperSVG
**Method.** First deep method targeting *complex* images at speed. Decompose
image into **SLIC superpixels** (compactness 30), vectorize each separately.
Two-stage self-teaching:
- **Coarse model `E_c`** (ViT encoder + cross-attn with learnable path queries +
  self-attn) predicts main-structure paths. Path query cross-attention:
  `T′_f = softmax( (W_Q T_l)(W_K T_f)ᵀ / √d ) (W_V T_f)`.
- **Refinement model `E_r`** takes the coarse render + target, adds detail paths.
**Losses.**
- Normalized recon: `L₂ = ‖x̂ − x‖² · (Σ_p mask(p) / wh)`
- Boundary (keep paths inside superpixel): `L_Bound = 𝔼[ R(S_binary)·(1 − mask) ]`
- Path efficiency (fewest visible paths): `L_PE = Σᵢ Sign(βᵢ − 0.5)`, gradient
  approximated by `Sig(βᵢ)(1 − Sig(βᵢ))`.
- **Dynamic Path Warping (DPW)** — the key novelty. A SoftDTW variant where each
  *generated* path matches exactly one *target* path (target paths may be
  skipped), preventing one path from averaging several targets. DP recurrence:
  ```
  p_{i,j} = d_{i,j} + min^γ( q_{i,j−1}, p_{i,j−1} )
  q_{i,j} =            min^γ( q_{i−1,j}, p_{i−1,j} )
  min^γ(a…) = −γ log Σ e^{−aᵢ/γ}   (γ>0; hard min at γ=0)
  ```
  This is the first differentiable DTW variant specialized to SVG path-sequence
  alignment.
**Benchmark (1,000 ImageNet test images; NVIDIA RTX 4090).** Two variants:
`-B` (feed-forward) and `-F` (+~10s L₂ finetune). Lower MSE/LPIPS better; higher
PSNR/SSIM better.
| #Paths | Method       | Time (s) | MSE ↓  | PSNR ↑ | LPIPS ↓ | SSIM ↑ |
|--------|--------------|----------|--------|--------|---------|--------|
| 500    | LIVE         | 20,000   | 0.0039 | 24.10  | 0.4467  | 0.7983 |
| 500    | DiffVG       | 19.29    | 0.0069 | 21.42  | 0.5319  | 0.6671 |
| 500    | Adobe Illus. | 0.87     | 0.0067 | 21.82  | 0.5595  | 0.6939 |
| 500    | Potrace      | 0.98     | 0.0208 | 17.85  | 0.5115  | 0.6920 |
| 500    | SuperSVG-B   | **0.31** | 0.0044 | 24.80  | 0.4452  | 0.7687 |
| 500    | SuperSVG-F   | 10.00    | **0.0026** | **27.46** | **0.3558** | **0.8383** |
| 2,000  | LIVE         | 120,000  | 0.0025 | 26.98  | 0.3994  | 0.8431 |
| 2,000  | DiffVG       | 73.65    | 0.0036 | 25.88  | 0.4683  | 0.7710 |
| 2,000  | SuperSVG-F   | 10.00    | **0.0017** | **29.12** | **0.2931** | **0.8828** |
| 4,000  | LIVE         | 300,000  | 0.0024 | 26.80  | 0.3981  | 0.8446 |
| 4,000  | DiffVG       | 140.34   | 0.0025 | 27.29  | 0.3858  | 0.8492 |
| 4,000  | SuperSVG-F   | 10.00    | **0.0014** | **29.96** | **0.2496** | **0.9028** |
Headline: LIVE takes ~6 GPU-hours/image at 500 paths; SuperSVG-B is ~0.3s and
beats it on PSNR. **Conclusion.** Superpixel decomposition + coarse-to-fine
self-teaching gets both quality *and* speed on complex images — the practical
sweet spot among pre-LLM methods.
### Im2Vec — Synthesizing Vector Graphics without Vector Supervision
Reddy, Gharbi, Lukáč, Mitra. CVPR 2021.
- PDF: https://arxiv.org/pdf/2102.02798 · Code: https://github.com/preddy5/Im2Vec
- Project: http://geometry.cs.ucl.ac.uk/projects/2021/Im2Vec/
- VAE + LSTM → path params, trained with only raster supervision (via
  differentiable rasterizer). Domain-specific; struggles on complex/general
  images. Path ordering not robust (LIVE cites this as motivation).
### Deep Vectorization of Technical Drawings
Egiazarian, Voynov, Artemov et al. ECCV 2020. **[relevant to "idealization"]**
- PDF: https://arxiv.org/pdf/2003.05471
- Pipeline: (1) deep cleaning stage removes background/imperfections + inpaints;
  (2) transformer estimates vector primitives (lines, arcs); (3) optimization
  refines primitive configs. Trained on synthetic renders + manual vectorizations.
  Strong where inputs have regular geometry — closest classical-DL analog to a
  "make it clean/ideal" objective.
### VectorArk — Learning Practical Image Vectorization with Rounded Polygon Representation
- PDF: https://arxiv.org/pdf/2605.24398 (2026)
- Rounded-polygon primitive aimed at production-quality practical vectorization;
  benchmarks against LLM baselines (GPT-4o, Gemini 2.5) and classical tracers
  (VTracer, Potrace).
---
## 4. LLM / multimodal SVG code generation (2024–2025 shift)
Treat SVG as *code*, generate with (V)LLMs. Better semantics/editability,
historically weaker pixel-accurate reconstruction than optimization.
### StarVector — Generating SVG Code from Images and Text
Rodriguez et al. CVPR 2025.
- PDF: https://arxiv.org/pdf/2312.11556 · Abstract: https://arxiv.org/abs/2312.11556
- Project/code: https://github.com/joanrod/star-vector
- LLM + image encoder → SVG code. Dataset **SVG-Stack** (2M samples). Handles
  primitives beyond path curves; generalizes across vectorization tasks.
### OmniSVG — A Unified Scalable Vector Graphics Generation Model
Yang et al. NeurIPS 2025.
- PDF: https://arxiv.org/pdf/2504.06263 · Abstract: https://arxiv.org/abs/2504.06263
- Project: https://omnisvg.github.io/ · Code: https://github.com/OmniSVG/OmniSVG
- Unified model spanning simple icons → complex illustrations/characters.
  Dataset **MMSVG-2M**. Autoregressive, parameterizes SVG as a token sequence.
### Chat2SVG — Vector Graphics Generation with LLMs and Image Diffusion
Wu, Su, Liao. CVPR 2025.
- PDF: https://arxiv.org/pdf/2411.16602
- LLMs draft SVG templates → diffusion-guided refinement of shapes.
### LayerTracer — Cognitive-Aligned Layered SVG Synthesis via Diffusion Transformer
Song, Chen, Shou. arXiv:2502.01105 (2025). **[loop-relevant: layered generation]**
- PDF: https://arxiv.org/pdf/2502.01105
- Diffusion transformer producing *layered* SVGs aligned to how designers build
  them up (background → detail).
### Empowering LLMs to Understand and Generate Complex Vector Graphics
Xing, Hu, Liang, Zhang, Xu, Yu. CVPR 2025 (SVGDreamer++/related line).
- PDF: https://arxiv.org/pdf/2412.11102 · pp. 19487–19497, CVPR Proceedings 2025.
---
## 5. Newest work (late 2025 / 2026)
### Render-in-the-Loop — Vector Graphics Generation via Visual Self-Feedback  **[most loop-relevant]**
- PDF: https://arxiv.org/pdf/2604.20730
- Closes the generate → render → visually-compare → refine loop. Conceptually the
  closest published analog to an autonomous idealization research loop with
  orchestrator re-verification.
### Rendering-aware Reinforcement Learning for Vector Graphics Generation  **[loop-relevant: reward design]**
Rodriguez, Zhang, Puri, Feizi et al. arXiv:2505.20793 (2025).
- PDF: https://arxiv.org/pdf/2505.20793
- RL with a *rendering-aware* reward (render the SVG, score against target) rather
  than pure token-level supervision. Directly relevant if your loop uses a
  visual judge as the reward signal.
### Reason-SVG — Hybrid Reward RL for "Aha-Moments" in Vector Graphics Generation
arXiv:2505.24499 (2025).
- PDF: https://arxiv.org/pdf/2505.24499
- Hybrid reward combining reasoning traces + visual fidelity for RL fine-tuning.
### AmodalSVG — Amodal Image Vectorization via Semantic Layer Peeling
arXiv:2604.10940 (2026).
- PDF: https://arxiv.org/pdf/2604.10940
- Recovers *occluded* layers during vectorization (amodal completion), producing
  fuller layer stacks than surface-only tracing.
### InternSVG — Unified SVG Tasks with Multimodal LLMs
Wang, Yin, Wei et al. arXiv:2510.11341 (2025).
- PDF: https://arxiv.org/pdf/2510.11341
- Single MLLM across understanding/editing/generation of SVG.
### DuetSVG — Unified Multimodal SVG Generation with Internal Visual Guidance
arXiv:2512.10894 (2025).
- PDF: https://arxiv.org/pdf/2512.10894
- Notes classical vectorizers score high on reconstruction but produce verbose,
  layer-poor, low-semantics code — motivates measuring *code similarity* and
  *path semantics*, not just pixel MSE.
### RoboSVG — Unified Framework for Interactive SVG Generation with Multimodal Guidance
arXiv:2510.22684 (2025).
- PDF: https://arxiv.org/pdf/2510.22684
### DOGE — Differentiable Bezier Graph Optimization for Road Network Extraction
arXiv:2511.19850 (2025).
- PDF: https://arxiv.org/pdf/2511.19850
- Applies DiffVG-style differentiable Bézier-graph optimization to a structured
  extraction task; useful example of the technique outside pure vectorization.
---
## 6. Surveys & benchmarks (start here for orientation)
### Image Vectorization: a Review
Dziuba, Jarsky, Efimova, Filchenkov. arXiv:2306.06441 (2023).
- Abstract: https://arxiv.org/abs/2306.06441
- Compares ML-compatible methods: Mang2Vec, Deep Vectorization, DiffVG, LIVE.
- **Conclusion:** no fast universal automatic method existed as of 2023; ML
  methods are slow and don't perfectly recreate the source; human control still
  needed per method. (A useful baseline claim to test your engine against.)
### VectorGym — Multitask Benchmark for SVG Code Gen, Sketching, Editing
- PDF: https://arxiv.org/pdf/2603.29852 (2026)
### SVGenius — Benchmarking LLMs in SVG Understanding, Editing, Generation
Chen et al. 2025.
- PDF: https://arxiv.org/pdf/2506.03139 — standard LLM-SVG capability benchmark.
---
## 7. Classical baselines (quality bar to beat on editability)
- **Potrace** — Selinger 2003, polygon tracing → Bézier. http://potrace.sourceforge.net/
- **VTracer** — Vision Cortex 2020, color raster→vector. https://github.com/visioncortex/vtracer
- **Depixelizing Pixel Art** — Kopf & Lischinski, SIGGRAPH 2011.
- **Diffusion Curves** (Orzan 2008), **Gradient Meshes** (Sun 2007) — smooth-shaded
  vector primitives; relevant if you want gradient fills rather than flat paths.
---
## Standard evaluation metrics (cross-paper)
- **MSE / PSNR** — pixel fidelity of the SVG render vs. target (↓ / ↑).
- **SSIM** — structural similarity, luminance+contrast+structure (↑).
- **LPIPS** — learned perceptual patch similarity, deep-feature distance (↓).
- **Path count / file size** — compactness & editability proxy (↓).
- **Inference time** — the axis where optimization methods (LIVE) lose badly.
- **Path Semantics / SVG Code Similarity** (DuetSVG) — layer organization &
  code cleanliness, which pixel metrics miss.
- **Novelty / Uniqueness** (IconShop-style, used by DuetSVG) — for generative,
  via CLIP-embedding matching against the training corpus.
## Threads most worth pulling for a render-in-the-loop idealization engine
1. **Visual reward / self-feedback** — Render-in-the-Loop (2604.20730),
   Rendering-aware RL (2505.20793), Reason-SVG (2505.24499). Formalize the
   "judge visually, feed back" loop and reward design.
2. **Layer topology** — LIVE, Layered Semantic Simplification, LayerTracer,
   AmodalSVG. Editable output = ordered layers, not path spaghetti.
3. **Speed + quality** — SuperSVG's coarse-to-fine self-teaching + DPW; the
   `-B`/`-F` split (fast feed-forward, optional short optimization finetune) is a
   good architecture template.
4. **Beyond-pixel metrics** — DuetSVG's Path Semantics / Code Similarity if you
   care about clean, editable output, not just reconstruction MSE.
