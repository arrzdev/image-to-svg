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
