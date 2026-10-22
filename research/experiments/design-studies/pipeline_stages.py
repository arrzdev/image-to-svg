"""Production-line visualizer: dump an image after EVERY v11 pipeline stage.

Replicates engines/quant/quant-11/src/pipelines/contour_lines.ContourLines.run() step by
step (same defaults, same order) and writes one PNG per stage plus a labeled
contact sheet, so the eye can locate WHERE in the line a defect is introduced.

Usage:
    DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python \
        research/experiments/design-studies/pipeline_stages.py data/inputs/rabbit.jpg \
        research/experiments/design-studies/stages_rabbit
"""
import importlib.util
import os
import sys

_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, os.path.join(_ROOT, "engines", "quant", "quant-11", "src"))

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _load_entry():
    spec = importlib.util.spec_from_file_location(
        "v11_entry", os.path.join(_ROOT, "models", "v11", "entry.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def save(outdir, idx, name, arr, stages, kind="px"):
    """kind: 'px' = raster data (image / label map), 'svg' = render of
    actual vector output — the sheet marks where pixels become vectors."""
    path = os.path.join(outdir, f"{idx:02d}_{name}.png")
    Image.fromarray(arr).save(path)
    stages.append((f"{idx:02d} {name}", arr, kind))
    print(f"  wrote {path}")


def lab_img(labels, centers):
    return centers.astype(np.uint8)[labels]


def strokes_only_svg(w, h, elements):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">'
            f'<rect width="{w}" height="{h}" fill="#ffffff"/>'
            + elements + "</svg>")


def main(image_path, outdir, native=False):
    os.makedirs(outdir, exist_ok=True)
    stages = []

    from pipelines.contour_lines import (_flatten_gradient_regions,
                                         _sharpen_prepass,
                                         _thin_dark_line_lock)
    from pipelines.quantize_contours import (_quantize, _consolidate_palette,
                                             _merge_shadow_tones,
                                             _own_transitions,
                                             _despeckle_labels,
                                             _smooth_labels,
                                             _dissolve_speckle)
    from contours_exp import (extract_contour_strokes, _light_line_capsules,
                              _fill_svg_corner_pinned, _stroke_elements)
    from strokes import absorb_mask
    import boundary
    from render import svg_to_rgb
    from imgstats import analyze

    # ---- defaults exactly as ContourLines declares them
    P = dict(num_colors=16, seed=0, merge_de=12.0, min_area=120, blur=1,
             presharpen=1.6, gradflat=1, fill_tol=2.5, fill_smooth=0,
             fill_parsimony=1.0, dark_lum=96.0, width_scale=0.85)

    # The web interface / CLI route through models/v11/entry.py, which
    # white-flattens alpha and resizes the longest side to 1024 BEFORE the
    # pipeline runs — replicate that exact prep or every pixel-unit
    # heuristic downstream behaves differently (verified: byte-identical
    # final SVG only via entry._prepare).
    if native:
        # bypass entry prep: pipeline sees the image at native resolution
        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        raw = img
        h, w = img.shape[:2]
        save(outdir, 0, f"NATIVE_{w}x{h}_no_entry_prep", raw, stages)
    else:
        entry = _load_entry()
        proc, (ow, oh) = entry._prepare(image_path)
        img = np.asarray(proc).copy()
        raw = img
        h, w = img.shape[:2]
        save(outdir, 0, f"entry_prep_{w}x{h}_from_{ow}x{oh}", raw, stages)

    # ---- 1 gradient flatten
    regions = []
    if P["gradflat"]:
        img, regions = _flatten_gradient_regions(img)
    save(outdir, 1, f"gradflat_{len(regions)}regions", img, stages)

    # ---- 2 sharpen + blur prepasses
    sharpen_ok = analyze(raw)["kind"] != "flat"

    def prepasses(a):
        if P["presharpen"] > 0 and sharpen_ok:
            a = _sharpen_prepass(a, P["presharpen"])
        if P["blur"] > 0:
            a = cv2.medianBlur(a, P["blur"] * 2 + 1)
        return a

    img = prepasses(img)
    save(outdir, 2, f"prepass_sharpen{'ON' if sharpen_ok else 'SKIP'}+blur",
         img, stages)

    # ---- 3 global k-means quantize
    if regions:
        labels, centers = _quantize(prepasses(raw), P["num_colors"], P["seed"])
    else:
        labels, centers = _quantize(img, P["num_colors"], P["seed"])
    save(outdir, 3, f"quantize_k{P['num_colors']}", lab_img(labels, centers),
         stages)

    # ---- 4 palette consolidation + shadow merge (+ gradient re-stamp)
    labels, centers = _consolidate_palette(labels, centers, P["merge_de"])
    labels, centers = _merge_shadow_tones(labels, centers)
    if regions:
        cf = centers.astype(np.float32)
        for m, mean in regions:
            li = int(((cf - mean[None, :]) ** 2).sum(1).argmin())
            labels[m] = li
    save(outdir, 4, f"consolidate_{len(centers)}colors",
         lab_img(labels, centers), stages)

    # ---- 5 transition ownership (E1)
    labels = _own_transitions(labels, centers)
    save(outdir, 5, "own_transitions", lab_img(labels, centers), stages)

    # ---- 6 thin-dark-line lock (shown as overlay)
    lock = _thin_dark_line_lock(labels, centers)
    ov = lab_img(labels, centers).copy()
    ov[lock] = (255, 0, 0)
    save(outdir, 6, "lock_mask_red", ov, stages)
    labels0 = labels.copy()

    # ---- 7-9 cleanup chain
    labels = _despeckle_labels(labels, max(P["min_area"], 16), centers)
    save(outdir, 7, "despeckle", lab_img(labels, centers), stages)
    labels = _smooth_labels(labels, len(centers), centers=centers)
    save(outdir, 8, "smooth", lab_img(labels, centers), stages)
    labels = _dissolve_speckle(labels, centers, 300)
    save(outdir, 9, "dissolve_speckle", lab_img(labels, centers), stages)

    # ---- 10 lock re-stamp
    flipped = lock & (labels != labels0)
    labels[flipped] = labels0[flipped]
    save(outdir, 10, f"lock_restamp_{int(flipped.sum())}px",
         lab_img(labels, centers), stages)

    # ---- 11 stroke extraction
    strokes, stroke_mask, info = extract_contour_strokes(
        labels, centers, dark_lum=P["dark_lum"], width_scale=P["width_scale"],
        src_img=img)
    ov = lab_img(labels, centers).copy()
    ov[stroke_mask] = (255, 0, 0)
    save(outdir, 11, f"stroke_pixels_red_{len(strokes)}strokes", ov, stages)
    save(outdir, 12, "strokes_only",
         svg_to_rgb(strokes_only_svg(w, h, _stroke_elements(strokes)), w, h),
         stages, kind="svg")

    # ---- 13 absorb ink out of fills + light capsules
    new_labels = absorb_mask(labels, stroke_mask)
    new_labels, capsules = _light_line_capsules(new_labels, centers, img)
    save(outdir, 13, f"fills_after_absorb_{len(capsules)}capsules",
         lab_img(new_labels, centers), stages)

    # ---- 14 fill fitting + layered emission (fills only)
    edges, _ = boundary.build_edges(new_labels)
    loops = boundary.region_loops(edges, len(centers))
    fills_svg = _fill_svg_corner_pinned(new_labels, centers, edges, loops,
                                        parsimony=P["fill_parsimony"],
                                        stats=info)
    save(outdir, 14, "fills_fitted_svg", svg_to_rgb(fills_svg, w, h), stages,
         kind="svg")

    # ---- 15 final assembly
    svg = fills_svg
    if capsules:
        svg = svg.replace("\n</svg>", "\n" + _stroke_elements(capsules)
                          + "\n</svg>")
    if strokes:
        svg = svg.replace("\n</svg>", "\n" + _stroke_elements(strokes)
                          + "\n</svg>")
    save(outdir, 15, "FINAL", svg_to_rgb(svg, w, h), stages, kind="svg")
    with open(os.path.join(outdir, "final.svg"), "w") as f:
        f.write(svg)

    # ---- contact sheet
    cols, pad, cap = 4, 12, 34
    tw = 480
    th = int(round(tw * h / w))
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except Exception:
        font = ImageFont.load_default()
    rows = (len(stages) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + pad) + pad,
                              rows * (th + cap + pad) + pad), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    KIND = {"px": ((90, 140, 235), "PIXELS"),      # blue frame = raster data
            "svg": ((46, 204, 113), "SVG")}        # green frame = vector out
    for i, (name, arr, kind) in enumerate(stages):
        r, c = divmod(i, cols)
        x = pad + c * (tw + pad)
        y = pad + r * (th + cap + pad)
        color, tag = KIND[kind]
        sheet.paste(Image.fromarray(arr).resize((tw, th), Image.LANCZOS),
                    (x, y))
        for b in range(4):                         # 4px kind-colored frame
            d.rectangle([x - b - 1, y - b - 1, x + tw + b, y + th + b],
                        outline=color)
        d.text((x, y + th + 8), f"[{tag}] {name}",
               fill=color, font=font)
    sheet_path = os.path.join(outdir, "production_line.png")
    sheet.save(sheet_path)
    print(f"contact sheet: {sheet_path}")


if __name__ == "__main__":
    argv = [a for a in sys.argv[1:] if a != "--native"]
    src = argv[0] if argv else "data/inputs/rabbit.jpg"
    out = argv[1] if len(argv) > 1 else "research/experiments/design-studies/stages_rabbit"
    main(src, out, native="--native" in sys.argv)
