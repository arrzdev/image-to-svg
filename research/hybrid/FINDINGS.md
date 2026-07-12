# Hybrid experiments — learned prior + classical pipeline (2026-07-12)

## A. Diffusion pre-idealization via img2img (SD-turbo) — DEAD
Idea: img2img at low strength with a "clean flat vector illustration" prompt
melts noise/AA/texture before quant-13 vectorizes; tilecmp judges vs the
Recraft target with colour anchored to the ORIGINAL source.

Result: WORSE on all images, all channels, at every strength — monotonic.

| image    | baseline | s=0.35 | s=0.20 | s=0.12 |
|----------|----------|--------|--------|--------|
| chopchop | 0.3313   | 0.4032 | 0.3857 | 0.3756 |
| crystals | 0.3749   | 0.4759 | —      | —      |
| fox      | 0.2899   | 0.3536 | —      | —      |

Autopsy: img2img does not idealize the input, it REPLACES it with a nearby
image from the model's prior (content drift: chopchop's face redrawn), and
even at strength 0.12 the 768px VAE encode/decode roundtrip alone destroys
more crisp source detail than the prior repairs. Recraft's idealization is
conservative w.r.t. source geometry; img2img's is not.

Implication for any future attempt: the learned prior must operate
CONSERVATIVELY and at full resolution — candidates: SDS latent optimization
(Layered 2406.05404's mechanism, anchored to the current image; still
VAE-bound), learned segmentation/edge priors instead of pixel resynthesis,
or tile-based full-res cleanup models. Script: idealize_img2img.py.

## B. OmniSVG-4B direct image->SVG — measured separately
(see omnisvg_test/ report; testing how close open-weights SOTA gets on our
corpus with tilecmp.)

## B. OmniSVG1.1_4B direct image->SVG — MEASURED, not a competitor
Ran locally on M3 Max/MPS (bf16; fp16 NaNs — Qwen2.5-VL issue; state-dict
remap for transformers 4.57; 6-13 tok/s; 1-5 min/image). tilecmp vs Recraft
targets, colour anchored to input:

| image          | OmniSVG (best) | quant-13 |
|----------------|----------------|----------|
| logo-geometric | 0.336          | 0.104    |
| chopchop       | 0.797          | 0.331    |

Easy icon: pretty but LOSSY reinterpretation (solid triangle -> hollow ring,
circles filled white, colour channel 0.643 = invents/drops colours). Complex
illustration: catastrophic collapse — output is the sand ellipse (+ a
repetition-loop blob in other candidates); one candidate EOS'd voluntarily at
417 tokens. Structural ceiling: 200x200 quantised grid, ~2k-token budget
(~50-150 paths) vs Recraft's 997 paths / 408KB on the same image.

CONCLUSION: open-weights image->SVG SOTA is 2.4-3.2x behind our classical
quant-13 on our corpus, in the direction that matters (fidelity). Its one
Recraft-like property — idealisation (clean arcs, minimal paths) — comes with
hallucination. The Recraft-class recipe (VectorArk: conservative outline-
normalised vectorization + learned cleanup, 5M-SVG training) exists only
closed. Artifacts: research/omnisvg_test/ (weights + clone gitignored).

## C. Curve-pair mining census (2026-07-12) — training data EXISTS
Mined quant-13-vs-Recraft matched curve pairs across all 11 images (pathflow
matcher, 8x8 tile grid, dE<=60, >=30px, turning<=1.2 after ORIENTATION/START
canonicalization — winding direction was 81% of raw mismatch):
**1,311 unique usable pairs** (~2.2k natural crops, ~42k augmented), quality
p50 turning 0.51, 78% closed fills. Dump: research/curveprior/pairs.jsonl.

TWO KEY FINDINGS:
1. **No cubic-count gap on matched curves** (ours 2.41 vs theirs 2.61 per
   100px, ratio 0.96). Recraft's edge is control-point PLACEMENT (smooth
   flow), not budget — an idealizer learns geometry regularization, not
   compression. (Confirms auto-loop it9: wander, not count.)
2. **31.8% of Recraft's paths (13.3% by arclength) have NO counterpart** in
   our output — micro-detail shards + invented content. No curve model
   touches that; it is the hard ceiling of this route.
Risks: diversity concentrated (chopchop+crystals+mountain = 66% of pairs);
corpus biased to smooth organic contours (aligned with where quant is
weakest). Hold-image-out eval mandatory.

## D. Curve idealizer v0 (trained on mined pairs) — LOSES TO GEOMETRY, closed
142K-param offset model, N=64 resampled curves, image-holdout (fox/shield/
elephant). Result: model LOSES to identity on both metrics on unseen images
(m1 0.450 vs 0.4225; m2 0.711 vs 0.598); oracle-tuned geometric smoothing
itself only improves turning by ~4% over identity. Autopsy (the real finding):
given shape ALONE, Recraft's redraw is mostly irreducible — the matched-pair
differences are either genuine route changes (unlearnable pointwise) or noise
that edge-10's smooth_closed already removes. A memorization control confirms
the trainer works; the supervision has ~no learnable signal. Also found+fixed:
pairs.jsonl their_pts were not canonicalized (re-canonicalize in any future
loader; corr(L2, centroid offset)=0.995 before fix).

TRIANGULATION ACROSS A-D: shape-alone learned mappings are exhausted — the
classical pipeline already extracts nearly all shape-level signal. The two
doors left open (untested): (1) SYNTHETIC-CORRUPTION training — corrupt
Recraft's clean curves with OUR pipeline's noise model, learn the inverse
(pixel-perfect supervision, unlimited data, no correspondence problem);
(2) IMAGE-CONDITIONED idealization — give the model the raster context so it
can locate the true edge instead of regressing shapes to the mean (subsumes
the earlier boundary-prior U-Net idea). Both are half-session experiments.
Artifacts: research/curveprior/ (model_v0*.pt, REPORT.md, train_idealizer.py,
overlays).

## E. Door 2 probe: image-conditioned idealization — CLOSED WITHOUT TRAINING
(2026-07-12, research/curveprior/v1_probe.py / v1_diag.py / v1_diag2.py /
v1_zoom.py; report JSON + overlays + zoom crops alongside.)

Design: training-free ladder in the ABSOLUTE 2048-canvas frame (no
canonicalization — position vs the image is the point; mismatched instances
gated out by co-location: chamfer<=12px & centroid<=24px -> 692/1,311 pairs,
150 holdout). Symmetric chamfer, canvas px, holdout = fox/shield/elephant.

Ladder (holdout, n=150):
  R0 identity                 3.137 px
  R1 oracle smoothing (B1)    3.170 px  (+1.0% — WORSE)
  R2 classical subpixel snap  3.166 px  (+0.9% — WORSE)
  R2b snap+smooth             3.219 px  (+2.6%)
  R3 oracle normal projection 1.732 px  (-44.8%, coverage 93%)
  offsets: |t| median 0.94px, p90 2.48px (pair medians)

So the PLACEMENT gap is real and big (R3): perfect per-point normal offsets
would remove ~45% of matched-curve error. But every attempt to PREDICT the
offset from the image fails:
- Q1 corr(classical snap delta, t_oracle) = +0.32; corr(gradient-peak
  position, t) = +0.44 — moderate raw signal, holdout.
- Q3 ridge (Lab profile 33 taps x3 + grad features + curvature, 104k points):
  holdout R2=+0.19 but MAE -1.2% (nothing).
- D2 MLP (nonlinear, same features): train R2=0.67, HOLDOUT R2=0.13,
  MAE +3.0% — nonlinear transfers WORSE. Overfits image-specific patterns.
- D1 model-independent bound: Recraft's line sits within 1px of the image
  gradient peak at only 30% of holdout points -> even a PERFECT
  edge-locating model caps at -21% normal-MAE (~ -9% chamfer); realized ~0.
- Eye (v1_zoom.png, x16): small |t| (the bulk) = both curves inside the SAME
  AA band, sub-SOURCE-pixel apart (fox: 3 canvas px < 1 image px) — Recraft's
  in-band choice is stylistic and locally unpredictable. Large |t| (tail) =
  route/topology differences (corner cuts, different decomposition), not
  placement — a normal offset can't express them.

VERDICT: door 2 dead at the local level. Recraft's exact placement is
dominated by their generative redraw prior (global/semantic consistency),
not by local image evidence. Matched-curve placement is a closed subject:
unpredictable where small, un-expressible where large.

DOOR 1 (synthetic corruption) DOWNGRADED by the same data, not run: the
inverse-corruption model only removes OUR tracing noise, and the ladder shows
our curves barely have removable noise left (oracle smoothing +1.0% i.e.
WORSE in absolute frame; census: no cubic-count gap). The residual to Recraft
is their redraw, which synthetic corruption cannot supervise. Expected value
~nil; do not spend a session unless a new noise source is identified.

WHERE THE REAL GAP LIVES (triangulated A-E): (a) unmatched/invented content —
31.8% of Recraft paths have no counterpart in ours; (b) global stylistic
coherence (their redraw prior); (c) color decisions (tilecmp color channel).
None of these are learnable from 11 pairs at curve level. The learned-hybrid
program on this corpus is CLOSED; remaining movement is classical (tilecmp
loop) or a Recraft-scale trained model (VectorArk recipe — not public).
