# StarVector on Apple Silicon (M3 Max)

Running `starvector/starvector-1b-im2svg` locally on macOS/MPS. Upstream assumes
CUDA; this directory is the bridge.

## Setup

```bash
brew install cairo
python3.12 -m venv venv
./venv/bin/pip install -r requirements-mac.txt
./venv/bin/pip install -e star-vector --no-deps
```

`star-vector/` is a clone of https://github.com/joanrod/star-vector.
`--no-deps` is mandatory: upstream's `pyproject.toml` lists `flash_attn==2.7.3`
as a hard dependency, which is CUDA-only and needs `nvcc`.

## Run

```bash
./venv/bin/python starvector_mps.py ../../../data/inputs/rabbit.jpg -o out.svg
```

Useful flags: `--greedy` (deterministic), `--fp32` (slower, more stable),
`--model 8b`, `--max-length N`.

## What the handoff got right

- `--no-deps` is required, and for the stated reason.
- `PYTORCH_ENABLE_MPS_FALLBACK=1` must be set before `import torch`.
- `attn_implementation="eager"`.
- `process_and_rasterize_svg` silently substitutes `<svg></svg>` on a parse
  failure, so an empty-looking output means generation failed. The runner now
  checks for this explicitly, exits non-zero, and always writes the
  pre-cleanup model output alongside it as `<output>.raw`.

## What turned out differently

These were corrected by reading the source rather than assuming.

**1. There is no CUDA problem to solve.**
The handoff's central worry — hardcoded `.cuda()` calls inside remote code we
can't edit — does not apply on this path. The HF remote `starvector_arch.py` is
a thin wrapper that delegates to the *locally installed* `starvector` package
(`starvector.model.models.starvector_v1`), so nearly all the code is editable.
And `grep -rn '\.cuda()' starvector/` finds hits only in `metrics/compute_fid.py`
and the validators, none of which inference touches. flash-attn is never
imported either: `starvector/model/llm/starcoder.py` gates on
`is_flash_attn_2_available()` (False here) and self-heals by setting
`config.use_flash_attn = False`. The monkeypatch is retained as a cheap safety
net; `--fake-cuda` has not been needed.

**2. `open-clip-torch` is not required.**
Listed as an assumption in the handoff. This checkpoint is
`image_encoder_type: "clip"`, which builds a self-contained `VisionTransformer`
from `starvector/model/image_encoder/clip_model.py`. `open_clip` is imported
only by `build_convnext_encoder()`, which is never called. `fairscale` *is*
required — `clip_model.py` imports `checkpoint_wrapper` at module level.

**3. The real blocker was a gated repo, not MPS.**
`StarCoderModel.__init__` calls `from_pretrained("bigcode/starcoderbase-1b")`,
which is gated (`gated: "auto"`). Without an accepted license it fails with:

```
403: Access to model bigcode/starcoderbase-1b is restricted
     and you are not in the authorized list.
```

That download is also ~4.5 GB of pure waste: the StarVector checkpoint is
self-contained (all 292 `model.svg_transformer.transformer.*` tensors are in its
safetensors index), so every starcoderbase weight is overwritten moments later.
Only the *config* and *tokenizer* are actually needed.

`starcoder_offline.py` therefore rebuilds the config locally and takes the
tokenizer from the ungated StarVector repo, which already ships the exact
tokenizer (`vocab.json`, `merges.txt`, and `added_tokens.json` mapping
`[PAD]`/`<svg-start>`/`<image-start>`/`<caption-start>` to 49152-49155). This
is the default; it needs no Hub license and skips the 4.5 GB download.

The config values are recovered from the checkpoint's safetensors headers via
HTTP range requests, not guessed:

| tensor | shape | implies |
| --- | --- | --- |
| `wte.weight` | `[49156, 2048]` | `vocab_size=49156`, `n_embd=2048` |
| `wpe.weight` | `[8192, 2048]` | `n_positions=8192` |
| `h.{0..23}` | 24 blocks | `n_layer=24` |
| `h.0.mlp.c_fc.weight` | `[8192, 2048]` | `n_inner=8192` |
| `h.0.attn.c_attn.weight` | `[2304, 2048]` | 2048 + 2×128 → `multi_query=True`, `n_head=16` |
| no `lm_head` tensor | — | `tie_word_embeddings=True` |

Load is verified at runtime (`verify_load`): it fails loudly on missing keys or
params left on the meta device, which is what a wrong config would produce.

To use upstream's path instead, accept the license at
https://huggingface.co/bigcode/starcoderbase-1b (auto-approved) and pass
`--gated-starcoder`.

**4. The handoff script's image preprocessing was wrong.**
`SimpleStarVectorProcessor` returns a bare `(3, H, W)` tensor for a single PIL
image — it does not add a batch dimension, and it ignores `return_tensors` for
images. The reference loader (`starvector_hf_validator.SVGValDataset`) leans on
a DataLoader to batch it. The original script's `if image.shape[0] != 1:
image.squeeze(0)` leaves `(3, 224, 224)` untouched, which reaches a conv2d
expecting `(B, 3, H, W)`. Fixed to `unsqueeze(0)`.

**5. Generation defaults.**
`_get_generation_kwargs` defaults to `max_length=30`, `num_beams=2`,
`do_sample=True` — not what the model was evaluated with. The runner now
defaults to `configs/generation/hf/starvector-1b/im2svg.yaml`:
`max_length=7800, min_length=10, num_beams=1, temperature=0.2, top_p=0.95`.
`num_beams=1` matters on MPS — the code default of 2 doubles decode cost.

## Status: working

`logo-geometric.png` (512², flat, in-domain) — 219 tokens, 17.8 s, terminated
naturally at `</svg>`:

```svg
<svg width="256" height="256" viewBox="0 0 256 256" ...>
<rect width="256" height="256" fill="#F4F4F0"/>
<circle cx="164.5" cy="132.5" r="52.5" fill="#FF5A5A"/>
<circle cx="92.5" cy="96.5" r="56.5" fill="#2684FF"/>
<path d="M128.5 30L221 212H36L128.5 30Z" fill="#30CC74"/>
<circle cx="124.5" cy="125.5" r="25.5" fill="#FFD60A"/>
</svg>
```

378 bytes. Note what this is: **semantic primitives** — a real `<circle>` with
cx/cy/r, a triangle as three points — with correct z-order and colors. Not a
traced polygon approximation of a circle. That is the property VTracer cannot
give and the reason this model was worth standing up.

Compare with `compare.py`:

```bash
./venv/bin/python compare.py ../data/inputs/logo-geometric.png out_logo.svg -o compare_logo.png
```

Decode runs ~10-14 tok/s on the M3 Max at fp16 (rate decays as context grows).

## `attn_implementation` does not reach the inner LLM — and eager is broken on MPS

Two separate findings here, the second one counterintuitive.

First: passing `attn_implementation="eager"` to the outer `from_pretrained` does
**not** give you eager attention. Constructing the inner `GPTBigCodeForCausalLM`
runs `_autoset_attn_implementation`, which silently upgrades `eager` to `sdpa`:

```
config._attn_implementation before: eager
config._attn_implementation after : sdpa
attention class                   : GPTBigCodeSdpaAttention
```

So every run was really SDPA regardless of what was asked for. `starcoder_offline`
now forces it via `_from_config(config, attn_implementation=...)`, exposed as
`--attn {eager,sdpa}`. This applies to the gated path too.

Second — and this is why the first one mattered less than it looked: **eager
attention produces all-NaN hidden states on MPS in fp16 and bf16.** It only works
in fp32. SDPA is fine in every dtype. Measured with `debug_nan.py`, first forward
pass over the conditioning embeddings, `logo-geometric.png`:

| dtype | attn | hidden_states | verdict |
| --- | --- | --- | --- |
| fp16 | eager | all NaN (526336/526336) | broken |
| bf16 | eager | all NaN | broken |
| fp16 | sdpa | min -53.469 max 156.375 | ok |
| bf16 | sdpa | min -53.000 max 155.000 | ok |
| fp32 | eager | min -53.638 max 156.415 | ok |
| fp32 | sdpa | min -53.638 max 156.415 | ok (reference) |

fp16+sdpa tracks the fp32 reference closely (156.375 vs 156.415), so fp16 itself
is numerically sound here — the failure is specific to the eager kernel in low
precision. Defaults are therefore `--dtype fp16 --attn sdpa`, and asking for
`eager` outside fp32 now exits immediately instead of failing minutes later
inside `torch.multinomial`.

`debug_nan.py` is the tool for this: it walks pixels → CLIP encoder → ln_vision →
adapter → LLM forward → logits and names the first stage that goes non-finite.
The `multinomial` error is the last stop, not the origin.

## Known failure: degenerate repetition on complex inputs

`rabbit.jpg` (4096², detailed illustration) falls into a decode loop. It opens
correctly — `viewBox`, then a `<defs><style>` block whose first ~20 classes match
the source palette exactly (peach ground, the greens of the bag, carrot oranges,
cheek pink, off-white body) — so the image encoder and adapter are wired
correctly and the model is genuinely seeing the image. But from `.cls-23` onward
it emits `.cls-N{fill:#f2b1c8;}` forever and never reaches any `<path>`.

The `ProgressStreamer` in `starvector_mps.py` exists to catch exactly this: the
loop is obvious within ~30 s instead of after a full 7800-token run.

**It is not numerical.** fp32 — the reference precision — reproduces it exactly:
1088 tokens in, still inside `<style>`, zero `<path>` emitted, class 49+, with
runs of 10 identical class definitions. Only the repeated colour changes between
dtypes (`#f2b1c8` in fp16, `#1a174e` in fp32). Combined with fp16+sdpa tracking
fp32 closely on the first forward (156.375 vs 156.415), precision is exonerated.

`--no-loop-guard` disables the `LoopDetector` stopping criterion, which aborts
once the token stream becomes exactly periodic. Without it a degenerate run
burns the full 7800 tokens (~12 min) producing garbage. It requires an *exact*
repeated period, so legitimately repetitive SVG does not trip it.

The 8B fails the same input differently but just as completely: it spends
hundreds of tokens on memorised namespace boilerplate — Adobe Illustrator,
Inkscape *and* Sozi declarations, `i:rulerOrigin`, `i:pageBounds`, `<switch>`,
`i:extraneous` — and loops before drawing anything. Both models fall back on
memorised training-set preambles when the image gives them nothing they
recognise.

This is the model card's stated scope limit rather than a bug —
StarVector was trained on icons, logos, diagrams and charts, and its card says
outright that it will not work on natural images or illustrations. The 224×224
encoder input also discards most of a 4096² source, which is in direct tension
with this repo's native-resolution requirement.

Levers if you want to push on it: `--repetition-penalty 1.02-1.1` (SVG
legitimately repeats tokens, so keep it small), `--fp32` (MPS is more stable,
~2× slower), `--greedy`. If illustrations are the real target, OmniSVG
(`OmniSVG/OmniSVG1.1_4B`) is the broader-domain alternative.

## The 8B is a different architecture, not a bigger 1B

Worth knowing before comparing them:

| | 1B | 8B |
| --- | --- | --- |
| LLM | StarCoder (`gpt_bigcode`) | StarCoder2 |
| vision | CLIP ViT, 224×224 | **siglip_384**, 384×384 |
| image tokens | 257 | 576 |
| SVG dialect | `<defs><style>` + classes | inline `style="fill:…"` |
| eval temperature | 0.2 | **0.7** |

That last row matters: `GEN_DEFAULTS` now applies each model's own settings from
`configs/generation/hf/starvector-{1b,8b}/im2svg.yaml`. Running the 8B on the 1B's
temperature 0.2 is not a fair test, and low temperature is exactly what makes
degenerate loops more likely.

The 8B path needed its own patches (`install_v2`): `starcoder2.py` hardcodes
`attn_implementation="flash_attention_2"` with **no availability check**, so
unlike the V1 path it does not self-heal and would raise on any non-CUDA machine.
Its base repo `bigcode/starcoder2-7b` is ungated, so only the redundant ~14 GB of
weights are skipped.

`logit_bias: 5` in the 8B eval config is inert on the HF path — it is only read
by the vLLM validator — and V2 leaves `eos_token_id` commented out. So the
configuration here is faithful to upstream's own HF evaluation.

Findings, load verified each time (no missing keys, no meta params; siglip
preprocessing confirmed at (1,3,384,384) = 576 patches = query_length):

| input | 1B | 8B (own params) |
| --- | --- | --- |
| logo-geometric | perfect, 219 tok, 17.8 s | loop |
| logo-badge | loop | **OK**, 1329 B, good geometry, broken fills |
| rabbit | loop in `<style>` | loop, 164.7 s, never drew anything |

Neither model dominates: each solves the logo the other loops on. Greedy decoding
is worse than sampling for the 8B (exact 2-token loop). Since the 8B fails the
same way on the rabbit, **model capacity is not what stands between this and a
usable illustration** — the scope limit is.

The 8B's `logo-badge` is worth studying, because its failure is instructive
rather than random. Geometry is excellent — one compound `evenodd` path holding
both rings and the star, with correct radii. The colours collapse:

```svg
<use fill="#000" filter="url(#ratings-star-a)" xlink:href="#ratings-star-a"/>
<use fill="#121C2F" xlink:href="#ratings-star-a"/>
<use fill="#F1C211" xlink:href="#ratings-star-a"/>
```

Three `<use>` on the *same* shape, so only the last fill survives and the navy
vanishes; the `filter` reference points at the path's own id, so it resolves to
nothing. This is a memorised Sketch drop-shadow export idiom — down to a
plausible real-world layer name, `ratings-star-a`. The model is a code LLM
completing SVG source it has seen, and here it reproduced the idiom's *shape*
without its *structure*. Expect this class of error, not noise.

## Versions

Python 3.12.13, torch 2.5.1, torchvision 0.20.1, transformers 4.49.0,
tokenizers 0.21.1, numpy 1.26.4. `torch.backends.mps.is_available()` → True,
`is_flash_attn_2_available()` → False.

Note upstream pins `requires-python >=3.11` and there is no `python3.11` on this
machine; 3.12 satisfies the constraint.
