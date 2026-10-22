"""Build ORIGINAL | OURS(HEAD) | RECRAFT side-by-side panels for every input.

Full-frame at 640px/panel plus a 2x2 grid of 256px zoom crops (2x scale) for
each of ours/recraft at deterministic spots (quarter centers).
"""
import pathlib, sys
sys.path.insert(0, 'engines/quant/quant-9/src')
import numpy as np
from PIL import Image, ImageDraw
from render import svg_to_rgb

ROOT = pathlib.Path('.').resolve()
OUT = ROOT / 'research/experiments/audit24/grids'
PANEL = 640

def load_raster(p, size):
    im = Image.open(p).convert('RGB')
    im.thumbnail((size, size), Image.LANCZOS)
    bg = Image.new('RGB', (size, size), 'white')
    bg.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    return bg

def load_svg(p, size):
    arr = svg_to_rgb(p.read_text(), size, size)
    return Image.fromarray(arr.astype(np.uint8))

def label(im, txt):
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 8 + 7 * len(txt), 16], fill='black')
    d.text((4, 2), txt, fill='white')
    return im

def main():
    inputs = sorted(p for p in (ROOT / 'data/inputs').iterdir()
                    if p.suffix.lower() in ('.png', '.jpg', '.jpeg'))
    for inp in inputs:
        name = inp.stem
        ours_p = ROOT / f'research/experiments/audit24/svg/{name}.svg'
        rec_p = ROOT / f'data/targets/{name}.svg'
        panels = [label(load_raster(inp, PANEL), 'ORIGINAL'),
                  label(load_svg(ours_p, PANEL), 'OURS')]
        if rec_p.exists():
            panels.append(label(load_svg(rec_p, PANEL), 'RECRAFT'))
        w = PANEL * len(panels) + 4 * (len(panels) - 1)
        canvas = Image.new('RGB', (w, PANEL), 'red')
        for i, p in enumerate(panels):
            canvas.paste(p, (i * (PANEL + 4), 0))
        canvas.save(OUT / f'{name}_full.png')
        print(name, 'ok', 'recraft' if rec_p.exists() else 'no-target')

if __name__ == '__main__':
    main()
