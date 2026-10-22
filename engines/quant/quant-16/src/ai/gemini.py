"""Nano Banana (Gemini 2.5 Flash Image) preprocessing stage.

This is the AI-assisted arm of the playground: clean / simplify / re-render the
raster BEFORE classical vectorization (research note approaches #2, #6). It is
OPTIONAL and only activates when GEMINI_API_KEY is set. Until then the app runs
fully on the no-API classical pipelines.

Cost note (confirm current pricing before enabling): "nano banana" =
gemini-2.5-flash-image, ~$0.039 per generated image. The pricier "nano banana
pro" = gemini-3-pro-image. We default to the cheap Flash model.

Preprocessing here is a hypothesis to TEST, not a guaranteed win: asking an
image model to "clean up" a logo can also hallucinate detail. The playground
lets you A/B it via SSIM against the original.
"""
from __future__ import annotations

import io
import os
from typing import Optional

from PIL import Image

MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")

# Prompt presets keyed by an id the frontend can pick from.
PROMPTS = {
    "clean_flatten": (
        "Redraw this image as a clean, flat vector-style illustration. Remove "
        "noise, JPEG artifacts, gradients and shading. Use flat solid color "
        "regions with crisp edges. Keep the exact same shapes, layout and "
        "colors. Do not add or remove any elements."
    ),
    "denoise": (
        "Remove noise, compression artifacts and blur from this image while "
        "preserving every edge, shape and color exactly. Do not stylize."
    ),
    "posterize": (
        "Simplify this image into a small number of flat solid color regions "
        "with clean sharp boundaries, like a screen-print poster. Preserve the "
        "overall composition and palette."
    ),
}


def is_configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def status() -> dict:
    return {
        "configured": is_configured(),
        "model": MODEL,
        "prompts": list(PROMPTS.keys()),
        "note": "Set GEMINI_API_KEY to enable. Default model gemini-2.5-flash-image (~$0.039/image).",
    }


def preprocess(image_bytes: bytes, prompt_key: str = "clean_flatten") -> bytes:
    """Send the image to Gemini and return the returned image bytes (PNG).

    Raises RuntimeError with a clear message if the key/model is not configured.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set; AI preprocessing is disabled.")

    try:
        from google import genai
        from google.genai import types
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"google-genai not importable: {e}")

    prompt = PROMPTS.get(prompt_key, PROMPTS["clean_flatten"])
    client = genai.Client(api_key=api_key)
    src = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    resp = client.models.generate_content(
        model=MODEL,
        contents=[prompt, src],
    )

    # Find the first inline image part in the response.
    for cand in resp.candidates or []:
        for part in (cand.content.parts if cand.content else []) or []:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                return inline.data
    raise RuntimeError("Gemini response contained no image data.")
