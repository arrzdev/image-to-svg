"""0b staged diagnosis (run 58): where does chopchop's maroon pinstripe die?

Track the strut pinstripe's pixels through the v11 label chain stage by
stage. At each stage: n distinct labels on the stripe mask, share of stripe
pixels whose label centroid is maroon-class (dE<25 in Lab), dominant label
centroid RGB. The first stage where maroon-share collapses is the culprit.
"""
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'engines/quant/quant-hifi/src'))
import numpy as np
import cv2
from skimage.color import rgb2lab, deltaE_ciede2000
from testbed import Testbed
from pipelines.contour_lines import _sharpen_prepass
from pipelines.quantize_contours import (
    _quantize, _consolidate_palette, _merge_shadow_tones,
    _despeckle_labels, _smooth_labels, _dissolve_speckle)
from pipelines.quantize_contours import _own_transitions

tb = Testbed('chopchop.png')
_, _, _, proc = tb.prep()
img = _sharpen_prepass(proc.copy(), 1.6)
img = cv2.medianBlur(img, 3)
H, W = img.shape[:2]

# stripe mask: dark-red pixels in the strut bbox
x0, y0, x1, y1 = int(.22*W), int(.52*H), int(.52*W), int(.97*H)
sub = img[y0:y1, x0:x1].astype(int)
R, G, B = sub[...,0], sub[...,1], sub[...,2]
m = (R > 55) & (R < 150) & (G < 48) & (B < 48) & (R > G + 45) & (R > B + 45)
mask = np.zeros((H, W), bool); mask[y0:y1, x0:x1] = m
n_px = mask.sum()
stripe_rgb = img[mask].mean(0)
stripe_lab = rgb2lab(stripe_rgb[None, None]/255.0)[0,0]
print(f'stripe pixels: {n_px}, mean RGB {stripe_rgb.round(0)}')

def report(tag, labels, centers):
    ls = labels[mask]
    vals, cts = np.unique(ls, return_counts=True)
    labs = rgb2lab(centers[vals][None]/255.0)[0]
    de = deltaE_ciede2000(np.tile(stripe_lab, (len(vals),1)), labs)
    maroon_share = cts[de < 25].sum() / cts.sum() if cts.sum() else 0
    dom = vals[cts.argmax()]
    print(f'{tag:22s} labels-on-stripe {len(vals):2d}  maroon-share {maroon_share:5.2f}  '
          f'dominant-centroid {centers[dom].round(0)}')

labels, centers = _quantize(img, 16, 0)
report('quantize k16', labels, centers)
labels, centers = _consolidate_palette(labels, centers, 12.0)
report('consolidate dE12', labels, centers)
labels, centers = _merge_shadow_tones(labels, centers)
report('shadow-merge', labels, centers)
labels = _own_transitions(labels, centers)
report('own_transitions (A)', labels, centers)
labels = _despeckle_labels(labels, 120, centers)
report('despeckle 120', labels, centers)
labels = _smooth_labels(labels, len(centers), centers=centers)
report('smooth', labels, centers)
labels = _dissolve_speckle(labels, centers, 300)
report('dissolve 300', labels, centers)
