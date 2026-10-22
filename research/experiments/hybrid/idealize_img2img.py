"""Diffusion pre-idealization: SD-turbo img2img pulls the raster toward clean
flat vector art before classical vectorization."""
import sys, time
import numpy as np
import torch
from PIL import Image
from diffusers import AutoPipelineForImage2Image

DEV = "mps" if torch.backends.mps.is_available() else "cpu"
PROMPT = ("clean flat vector illustration, smooth solid color regions, "
          "crisp clean outlines, simple flat shading, no noise, no grain")
NEG = "photo, noise, grain, film grain, texture, blur, jpeg artifacts"

def main(names, strength=0.35, steps=4, size=768):
    t0=time.time()
    pipe = AutoPipelineForImage2Image.from_pretrained(
        "stabilityai/sd-turbo", torch_dtype=torch.float16, variant="fp16",
        safety_checker=None)
    pipe = pipe.to(DEV)
    print(f"pipeline loaded {time.time()-t0:.0f}s on {DEV}")
    for name in names:
        src = Image.open(f"data/inputs/{name}").convert("RGB")
        ow, oh = src.size
        img = src.resize((size, size), Image.LANCZOS)
        t=time.time()
        out = pipe(prompt=PROMPT, negative_prompt=NEG, image=img,
                   strength=strength, num_inference_steps=steps,
                   guidance_scale=0.0,
                   generator=torch.Generator().manual_seed(7)).images[0]
        out = out.resize((ow, oh), Image.LANCZOS)
        stem = name.rsplit(".",1)[0]
        p = f"data/inputs_idealized/{stem}.png"
        out.save(p)
        print(f"{name}: idealized in {time.time()-t:.1f}s -> {p}")

if __name__ == "__main__":
    import os
    os.makedirs("data/inputs_idealized", exist_ok=True)
    main(sys.argv[1:] or ["chopchop.png","crystals.jpg","fox.jpg"])
