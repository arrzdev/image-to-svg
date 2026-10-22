#!/usr/bin/env python3
"""
Locate where non-finite values enter the pipeline, per input image and dtype.

Generation dies in torch.multinomial with "probability tensor contains inf, nan
or element < 0". That is the last stop, not the origin. This walks the actual
stages -- pixels -> CLIP vision encoder -> ln_vision -> adapter -> first LLM
forward -> logits -- and reports the first one that goes non-finite.
"""
import os
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import argparse
import torch
from PIL import Image

import starcoder_offline

MODEL = "starvector/starvector-1b-im2svg"
DTYPES = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}


def stat(name, t):
    f = torch.isfinite(t)
    bad = (~f).sum().item()
    finite = t[f].float()
    lo = finite.min().item() if finite.numel() else float("nan")
    hi = finite.max().item() if finite.numel() else float("nan")
    flag = "  <-- NON-FINITE" if bad else ""
    print(f"    {name:22s} {str(tuple(t.shape)):20s} "
          f"min {lo:11.3f}  max {hi:11.3f}  bad {bad}{flag}")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+")
    ap.add_argument("--dtype", choices=list(DTYPES), default="fp16")
    ap.add_argument("--attn", choices=["eager", "sdpa"], default="eager")
    args = ap.parse_args()

    dtype = DTYPES[args.dtype]
    device = torch.device("mps")

    starcoder_offline.install(tokenizer_source=MODEL, attn=args.attn)
    from transformers import AutoModelForCausalLM
    print(f"loading ({args.dtype}, attn={args.attn}) ...", flush=True)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, torch_dtype=dtype, trust_remote_code=True,
        attn_implementation="eager", low_cpu_mem_usage=True,
    )
    starcoder_offline.retie_lm_head(model)
    model.to(device).eval()

    sv = model.model
    proc = sv.processor

    for path in args.images:
        print(f"\n=== {path}  [{args.dtype}] ===")
        px = proc(Image.open(path).convert("RGB"))["pixel_values"]
        if px.dim() == 3:
            px = px.unsqueeze(0)
        px = px.to(device=device, dtype=dtype)

        with torch.no_grad():
            if stat("pixel_values", px):
                continue

            # ImageEncoder.forward: visual_encoder -> ln_vision
            embeds = sv.image_encoder.visual_encoder(px)
            bad = stat("clip visual_encoder", embeds)
            out = sv.image_encoder.ln_vision(embeds)
            bad += stat("ln_vision", out)

            proj = sv.image_projection(out)
            bad += stat("image_projection", proj)
            if bad:
                continue

            # First LLM forward over the conditioning embeddings.
            att = torch.ones(proj.size()[:-1], dtype=torch.long, device=device)
            hs = sv.svg_transformer.transformer.transformer(
                inputs_embeds=proj, attention_mask=att
            )[0]
            stat("llm hidden_states", hs)
            logits = sv.svg_transformer.transformer.lm_head(hs)
            stat("lm_head logits", logits)
            probs = torch.softmax(logits[:, -1, :].float(), dim=-1)
            stat("softmax probs", probs)


if __name__ == "__main__":
    main()
