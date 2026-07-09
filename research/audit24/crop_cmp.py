"""Zoom-crop comparator: ORIGINAL | OURS | RECRAFT at a normalized bbox.

usage: crop_cmp.py <name> <x0> <y0> <x1> <y1> <outname>  (coords in 0..1)
Renders SVGs at 2048, crops the bbox, upscales original raster crop to match.
"""
import pathlib, sys
sys.path.insert(0, 'models/v9/src')
import numpy as np
from PIL import Image, ImageDraw
from render import svg_to_rgb

ROOT = pathlib.Path('.').resolve()
RES = 2048

def svg_img(p):
    return Image.fromarray(svg_to_rgb(p.read_text(), RES, RES).astype(np.uint8))

def raster_img(p):
    im = Image.open(p).convert('RGB')
    bg = Image.new('RGB', (RES, RES), 'white')
    r = min(RES / im.width, RES / im.height)
    im = im.resize((round(im.width * r), round(im.height * r)), Image.LANCZOS)
    bg.paste(im, ((RES - im.width) // 2, (RES - im.height) // 2))
    return bg

def main():
    name, x0, y0, x1, y1, out = sys.argv[1], *map(float, sys.argv[2:6]), sys.argv[6]
    inp = next((ROOT / 'data/inputs').glob(name + '.*'))
    panels = [('ORIGINAL', raster_img(inp)),
              ('OURS', svg_img(ROOT / f'research/audit24/svg/{name}.svg'))]
    rec = ROOT / f'data/targets/{name}.svg'
    if rec.exists():
        panels.append(('RECRAFT', svg_img(rec)))
    box = (int(x0 * RES), int(y0 * RES), int(x1 * RES), int(y1 * RES))
    crops = []
    W = 620
    for t, im in panels:
        c = im.crop(box)
        c = c.resize((W, int(c.height * W / c.width)), Image.LANCZOS)
        d = ImageDraw.Draw(c)
        d.rectangle([0, 0, 8 + 7 * len(t), 16], fill='black')
        d.text((4, 2), t, fill='white')
        crops.append(c)
    h = max(c.height for c in crops)
    canvas = Image.new('RGB', (W * len(crops) + 4 * (len(crops) - 1), h), 'red')
    for i, c in enumerate(crops):
        canvas.paste(c, (i * (W + 4), 0))
    canvas.save(ROOT / f'research/audit24/grids/{out}.png')
    print('saved', out)

if __name__ == '__main__':
    main()
