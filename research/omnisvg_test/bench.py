"""Benchmark OmniSVG outputs vs Recraft targets with tilecmp; save side-by-side PNGs."""
import sys, os, json
ROOT = '/Users/arrz/Documents/Github/image-to-svg'
os.chdir(ROOT)
sys.path.insert(0, 'research/design')
sys.path.insert(0, 'models/quant-11/src')
import numpy as np
from PIL import Image
import tilecmp, render

OUT = 'research/omnisvg_test'

for stem in ['logo-geometric', 'chopchop']:
    svg_path = f'{OUT}/{stem}.svg'
    if not os.path.exists(svg_path):
        print(f'{stem}: SVG missing, skipping')
        continue
    svg = open(svg_path).read()
    target = open(f'data/targets/{stem}.svg').read()
    input_png = f'data/inputs/{stem}.png'

    # tilecmp vs Recraft target, color anchored to original input
    res = tilecmp.compare(svg, target, n=40, native=2048, input_img=input_png)
    print(f'== {stem} ==')
    print(json.dumps(res['agg'], indent=2, default=str))

    # side-by-side render: original | omnisvg
    size = 896
    ours = render.svg_to_rgb(svg, size, size)
    orig = Image.open(input_png).convert('RGB').resize((size, size), Image.LANCZOS)
    sxs = np.concatenate([np.asarray(orig), np.full((size, 8, 3), 255, np.uint8),
                          ours.astype(np.uint8)], axis=1)
    Image.fromarray(sxs).save(f'{OUT}/{stem}_sxs.png')
    print(f'saved {OUT}/{stem}_sxs.png')

    # stats
    n_paths = svg.count('<path')
    print(f'file size: {len(svg)} bytes, paths: {n_paths}')
