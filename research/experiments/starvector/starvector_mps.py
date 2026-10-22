#!/usr/bin/env python3
"""
StarVector image-to-SVG on Apple Silicon (MPS).

Setup (see README-MPS.md):
    python3.12 -m venv venv && source venv/bin/activate
    pip install -r requirements-mac.txt
    pip install -e star-vector --no-deps
    huggingface-cli login          # bigcode/starcoderbase-1b is a gated repo

Usage:
    python starvector_mps.py rabbit.jpg -o out.svg
    python starvector_mps.py logo.png -o out.svg --greedy
    python starvector_mps.py logo.png -o out.svg --model 8b --fp32

Notes on the CUDA situation, verified by reading the source rather than assumed:
  - The HF remote code (starvector_arch.py) is a thin wrapper; the real model
    lives in the locally-installed `starvector` package. So there is very little
    "code we don't control".
  - There are NO .cuda() calls on the im2svg inference path. The only ones in the
    repo are in metrics/compute_fid.py and the validators, none of which we touch.
    The monkeypatch below is kept purely as a cheap safety net.
  - flash-attn is never imported: starvector/model/llm/starcoder.py gates on
    transformers.utils.is_flash_attn_2_available(), which is False without CUDA,
    and self-heals by setting config.use_flash_attn = False.
"""

import os

# Must be set BEFORE torch is imported. Lets unimplemented MPS ops fall back to
# CPU instead of raising. Costs speed, avoids hard crashes.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import argparse
import sys
import time

import torch
from PIL import Image

MODELS = {
    "1b": "starvector/starvector-1b-im2svg",
    "8b": "starvector/starvector-8b-im2svg",
}

VOID_SVG = "<svg></svg>"  # starvector.data.util.VOID_SVF -- the "generation failed" sentinel

# Per-model generation defaults, taken from the repo's own eval configs:
#   configs/generation/hf/starvector-{1b,8b}/im2svg.yaml
# These differ substantially -- the 8B is evaluated at temperature 0.7, the 1B at
# 0.2 -- so running the 8B on the 1B's settings is not a fair comparison, and low
# temperature is exactly what makes degenerate loops more likely.
GEN_DEFAULTS = {
    "1b": dict(max_length=7800, temperature=0.2, length_penalty=1.0),
    "8b": dict(max_length=16000, temperature=0.7, length_penalty=0.5),
}


class LoopDetector:
    """
    Stop generation once the token stream becomes exactly periodic.

    Degenerate repetition is this model's main failure mode on complex inputs
    (see README-MPS.md). Left alone it runs to max_length -- ~12 minutes of
    decode for an output that is already garbage. This aborts within a few
    hundred tokens instead.

    Deliberately strict: requires an *exact* period repeated `repeats` times, so
    legitimately repetitive SVG (path commands, a run of same-coloured shapes)
    does not trip it. `.cls-N{fill:#f2b1c8;}` sequences are not exactly periodic
    -- N increments -- so the window has to be long enough to span several of
    them; that is what max_period covers.
    """

    def __init__(self, tokenizer=None, min_period=2, max_period=48, repeats=6,
                 chunk=100):
        self.tok = tokenizer
        self.min_period, self.max_period, self.repeats = min_period, max_period, repeats
        self.chunk = chunk
        self.tripped = False
        self.reason = None

    def __call__(self, input_ids, scores, **kwargs):
        ids = input_ids[0].tolist()

        # Exact token periodicity -- catches tight loops cheaply.
        if len(ids) % 8 == 0:
            for p in range(self.min_period, self.max_period + 1):
                need = p * self.repeats
                if len(ids) < need:
                    break
                tail = ids[-need:]
                if all(tail[i] == tail[i % p] for i in range(need)):
                    self.tripped, self.reason = True, f"exact token period {p}"
                    return True

        # Text-level recurrence. The 8B degenerates by re-emitting near-identical
        # <path> elements whose coordinates wobble slightly, so it is never
        # exactly periodic in tokens. An exact 100-char string recurring earlier
        # in the document is still vanishingly unlikely in legitimate SVG.
        if self.tok is not None and len(ids) % 32 == 0:
            text = self.tok.decode(ids, skip_special_tokens=True)
            if len(text) > self.chunk * 3:
                tail = text[-self.chunk:]
                if tail in text[:-self.chunk]:
                    self.tripped = True
                    self.reason = f"{self.chunk}-char block recurred"
                    return True
        return False


class ProgressStreamer:
    """
    Minimal transformers BaseStreamer: report decode rate while generating.

    Autoregressive decode over thousands of tokens on MPS takes minutes with no
    output of its own. This makes the wait observable and, more usefully, shows
    *what* is being emitted -- degenerate repetition or non-SVG text is obvious
    immediately instead of after the full run.
    """

    def __init__(self, tokenizer, every=64, preview=90):
        self.tok = tokenizer
        self.every = every
        self.preview = preview
        self.n = 0
        self.text = []
        self.t0 = time.time()

    def put(self, value):
        ids = value.view(-1).tolist()
        self.n += len(ids)
        self.text.append(self.tok.decode(ids, skip_special_tokens=True))
        if self.n % self.every < len(ids):
            dt = time.time() - self.t0
            tail = "".join(self.text)[-self.preview:].replace("\n", " ")
            print(f"  [{self.n:5d} tok  {dt:6.1f}s  {self.n/max(dt,1e-9):5.1f} tok/s]  ...{tail}",
                  flush=True)

    def end(self):
        dt = time.time() - self.t0
        print(f"  [stream done: {self.n} tok in {dt:.1f}s]", flush=True)


def get_device():
    if not torch.backends.mps.is_available():
        if not torch.backends.mps.is_built():
            sys.exit("PyTorch was built without MPS. Install a recent arm64 build.")
        sys.exit("MPS unavailable (needs macOS 12.3+ on Apple Silicon).")
    return torch.device("mps")


def patch_cuda_to_mps(device, fake_cuda_available=False):
    """Safety net -- see module docstring. Not required on the paths we exercise."""
    torch.nn.Module.cuda = lambda self, *a, **k: self.to(device)
    torch.Tensor.cuda = lambda self, *a, **k: self.to(device)

    # Faking availability can help OR hurt -- it may push code into genuinely
    # CUDA-only APIs (amp, nvml). Off by default.
    if fake_cuda_available:
        torch.cuda.is_available = lambda: True
        torch.cuda.current_device = lambda: 0
        torch.cuda.device_count = lambda: 1


def repair_svg(raw):
    """
    Fix a narrow, well-defined malformation in the root tag.

    The 8B sometimes emits `<svg="true" xmlns=... viewBox=...>` -- a valueless
    attribute glued to the tag name. Everything after it is fine, but
    BeautifulSoup's xml parser rejects the document, so process_and_rasterize_svg
    silently swaps in the <svg></svg> placeholder and a 95%-correct drawing is
    thrown away.

    Only this one pattern is touched, and the caller reports when it fires --
    a repair that hides how often the model misformats would be worse than none.
    """
    import re
    fixed, n = re.subn(r'^(\s*<svg)=(?:"[^"]*"|\'[^\']*\'|[^\s>]+)', r"\1", raw)
    return fixed, n > 0


def output_for(args, image_path):
    """Single image -> args.output as a file. Several -> args.output as a dir."""
    if len(args.images) == 1 and not os.path.isdir(args.output):
        return args.output
    os.makedirs(args.output, exist_ok=True)
    stem = os.path.splitext(os.path.basename(image_path))[0]
    return os.path.join(args.output, stem + ".svg")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", help="input raster image(s) (png/jpg)")
    ap.add_argument("-o", "--output", default="output.svg",
                    help="output .svg for a single input; output DIRECTORY when "
                         "several inputs are given (model loads once)")
    ap.add_argument("--model", choices=["1b", "8b"], default="1b")
    # Unset by default so GEN_DEFAULTS[model] applies; passing one overrides it.
    ap.add_argument("--max-length", type=int, default=None)
    ap.add_argument("--length-penalty", type=float, default=None)
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--min-length", type=int, default=10)
    ap.add_argument("--num-beams", type=int, default=1)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--repetition-penalty", type=float, default=1.0,
                    help="raise slightly (1.02-1.1) if generation falls into a "
                         "degenerate loop; SVG legitimately repeats tokens, so "
                         "large values hurt")
    ap.add_argument("--greedy", action="store_true",
                    help="disable sampling -- deterministic, usually cleaner SVG")
    ap.add_argument("--dtype", choices=["fp16", "bf16", "fp32"], default="fp16",
                    help="fp16 is the checkpoint's native dtype and is "
                         "numerically sound with --attn sdpa; fp32 is the "
                         "reference fallback (~2x slower)")
    ap.add_argument("--fp32", action="store_true", help="alias for --dtype fp32")
    ap.add_argument("--attn", choices=["eager", "sdpa"], default="sdpa",
                    help="attention impl for the inner StarCoder LLM (must be "
                         "forced -- see starcoder_offline._Model). eager produces "
                         "all-NaN hidden states on MPS in fp16/bf16 and is only "
                         "usable with --dtype fp32.")
    ap.add_argument("--no-loop-guard", action="store_true",
                    help="do not abort on degenerate periodic repetition")
    ap.add_argument("--quiet", action="store_true",
                    help="disable the live decode-progress stream")
    ap.add_argument("--fake-cuda", action="store_true",
                    help="spoof torch.cuda.is_available() -- see patch_cuda_to_mps")
    ap.add_argument("--gated-starcoder", action="store_true",
                    help="use upstream's gated bigcode/starcoderbase-1b download "
                         "instead of the local config (needs an accepted license "
                         "and pulls ~4.5GB that is then overwritten)")
    args = ap.parse_args()

    defaults = GEN_DEFAULTS[args.model]
    for k, v in defaults.items():
        if getattr(args, k) is None:
            setattr(args, k, v)
    print(f"generation defaults for {args.model}: max_length={args.max_length} "
          f"temperature={args.temperature} length_penalty={args.length_penalty}",
          flush=True)

    # Measured, not assumed: eager + fp16/bf16 yields all-NaN hidden states on
    # MPS, which surfaces much later as "probability tensor contains inf, nan".
    # Fail up front rather than after minutes of decoding.
    if args.attn == "eager" and not args.fp32 and args.dtype != "fp32":
        sys.exit("--attn eager gives NaN hidden states on MPS in "
                 f"{args.dtype}; use --dtype fp32 or --attn sdpa.")

    device = get_device()
    patch_cuda_to_mps(device, fake_cuda_available=args.fake_cuda)
    dtype = {"fp16": torch.float16, "bf16": torch.bfloat16,
             "fp32": torch.float32}[("fp32" if args.fp32 else args.dtype)]

    from transformers import AutoModelForCausalLM

    model_name = MODELS[args.model]

    import starcoder_offline
    if args.model == "8b":
        # Different code path entirely: StarCoder2 (starvector_v2). Its base repo
        # is ungated, so this only skips the redundant ~14GB weight download and
        # undoes the hardcoded flash_attention_2.
        starcoder_offline.install_v2(attn=args.attn, dtype=dtype)
        print("patched StarCoder2 path (no redundant weight download, "
              f"attn={args.attn})", flush=True)
    elif not args.gated_starcoder:
        starcoder_offline.install(tokenizer_source=model_name, attn=args.attn)
        print("using offline StarCoder config (skipping gated bigcode repo)", flush=True)

    print(f"loading {model_name} ({dtype}) ...", flush=True)

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=dtype,
        trust_remote_code=True,
        attn_implementation="eager",    # flash-attn is CUDA-only
        low_cpu_mem_usage=True,
    )
    # Applies to both paths -- see retie_lm_head's docstring. On the gated path
    # skipping this is silent, not fatal.
    import starcoder_offline
    if starcoder_offline.retie_lm_head(model):
        print("re-tied lm_head -> wte (broken by low_cpu_mem_usage)", flush=True)

    # Generic check -- nested from_pretrained calls inside the outer
    # init_empty_weights context are exactly how params get stranded on meta
    # (this is what caught the lm_head tie). Applies to 8b's siglip encoder too.
    problems = starcoder_offline.verify_load(model, strict=False)
    if problems:
        sys.exit("load looks wrong: " + "; ".join(problems))
    print("load verified: no missing keys, no meta params", flush=True)

    model.to(device)
    model.eval()

    processor = model.model.processor

    gen_kwargs = dict(
        max_length=args.max_length,
        min_length=args.min_length,
        num_beams=args.num_beams,
        temperature=args.temperature,
        top_p=args.top_p,
        use_nucleus_sampling=not args.greedy,   # maps to do_sample downstream
        repetition_penalty=args.repetition_penalty,
        length_penalty=args.length_penalty,
    )

    # generate_im2svg builds its kwargs internally and only lets
    # _get_im2svg_specific_kwargs add to them, so hook there.
    tokenizer = model.model.svg_transformer.tokenizer
    _base = model.model._get_im2svg_specific_kwargs

    try:
        from starvector.data.util import process_and_rasterize_svg
    except ImportError:
        process_and_rasterize_svg = None
        print("warning: starvector package not importable "
              "(pip install -e star-vector --no-deps); writing raw output",
              file=sys.stderr)

    failures = 0
    for path in args.images:
        out_path = output_for(args, path)
        print(f"\n=== {path} -> {out_path} ===", flush=True)

        # SimpleStarVectorProcessor returns a bare (3, H, W) tensor for a single
        # PIL image -- no batch dim, and it ignores return_tensors for images.
        # The reference loader (starvector_hf_validator.SVGValDataset) relies on
        # a DataLoader to batch it. We have none, so batch it here. Getting this
        # wrong feeds (3, 224, 224) to a conv2d expecting (B, 3, H, W).
        image_pil = Image.open(path).convert("RGB")
        # V1 uses SimpleStarVectorProcessor; V2/8b uses an AutoImageProcessor,
        # which needs return_tensors to hand back tensors.
        image = processor(image_pil, return_tensors="pt")["pixel_values"]
        if not torch.is_tensor(image):
            image = torch.as_tensor(image)
        if image.dim() == 3:
            image = image.unsqueeze(0)
        image = image.to(device=device, dtype=dtype)

        # Fresh streamer and detector per image -- both carry per-run state.
        extra = {}
        if not args.quiet:
            extra["streamer"] = ProgressStreamer(tokenizer)
        detector = None
        if not args.no_loop_guard:
            from transformers.generation.stopping_criteria import StoppingCriteriaList
            from starvector.model.models.starvector_base import StoppingCriteriaSub
            # _get_generation_kwargs sets stopping_criteria and our update()
            # replaces it wholesale, so re-add the "</svg>" stop next to the guard.
            detector = LoopDetector(tokenizer)
            end_seq = tokenizer("</svg>", add_special_tokens=False)["input_ids"]
            extra["stopping_criteria"] = StoppingCriteriaList(
                [StoppingCriteriaSub(stops=[end_seq]), detector])
        model.model._get_im2svg_specific_kwargs = lambda kw, _e=extra: {**_base(kw), **_e}

        t0 = time.time()
        with torch.no_grad():
            raw_svg = model.model.generate_im2svg({"image": image}, **gen_kwargs)[0]
        dt = time.time() - t0

        looped = detector is not None and detector.tripped
        if looped:
            print(f"LOOP: aborted on degenerate repetition ({detector.reason}). "
                  f"Output is truncated and almost certainly unusable.", flush=True)

        # Cleans up malformed paths. On failure it silently substitutes
        # VOID_SVG, so check for that explicitly.
        candidate, repaired = repair_svg(raw_svg)
        if repaired:
            print("  repaired malformed root tag (<svg=... -> <svg)", flush=True)
        svg = candidate
        if process_and_rasterize_svg is not None:
            svg, _raster = process_and_rasterize_svg(candidate)

        with open(out_path, "w") as f:
            f.write(svg)
        with open(out_path + ".raw", "w") as f:
            f.write(raw_svg)

        void = svg.strip() == VOID_SVG
        status = "LOOP" if looped else ("VOID" if void else "OK")
        if status != "OK":
            failures += 1
        print(f"RESULT {status}  {path}  {dt:.1f}s  {len(svg)}B  "
              f"{svg.count('<path')} paths  -> {out_path}", flush=True)
        if void:
            print(f"  the generated markup would not parse; see {out_path}.raw",
                  file=sys.stderr)

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
