"""0j staged diagnosis (run 59): where does the rabbit paw/basket weld happen?

Audit evidence (z_rabbit_hand): the white paw holding the basket disappears —
merged into the gray basket-content mass; its dark outline vanishes.
Track BOTH features through the v11 label chain:
  paw interior = near-white pixels in the paw bbox
  paw outline  = ink pixels (lum<60) in a ring around the paw bbox
At each stage report: white-share of interior (label centroid within dE 20
of paw white), ink-share of the outline mask. Whichever collapses first,
and at which stage, names the culprit.
"""
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'models/staged/src'))
import numpy as np
import cv2
from skimage.color import rgb2lab, deltaE_ciede2000
from testbed import Testbed
from pipelines.contour_lines import _sharpen_prepass
from pipelines.quantize_contours import (
    _quantize, _consolidate_palette, _merge_shadow_tones, _own_transitions,
    _despeckle_labels, _smooth_labels, _dissolve_speckle)

tb = Testbed('rabbit.jpg')
_, _, _, proc = tb.prep()
img = _sharpen_prepass(proc.copy(), 1.6)
img = cv2.medianBlur(img, 3)
H, W = img.shape[:2]

x0, y0, x1, y1 = int(.54*W), int(.50*H), int(.76*W), int(.72*H)
sub = img[y0:y1, x0:x1].astype(int)
lum = 0.299*sub[...,0] + 0.587*sub[...,1] + 0.114*sub[...,2]
paw_m = lum > 195
ink_m = lum < 60
paw = np.zeros((H, W), bool); paw[y0:y1, x0:x1] = paw_m
ink = np.zeros((H, W), bool); ink[y0:y1, x0:x1] = ink_m
paw_rgb = img[paw].mean(0)
paw_lab = rgb2lab(paw_rgb[None,None]/255.0)[0,0]
print(f'paw px {paw.sum()}, mean {paw_rgb.round(0)}; ink px {ink.sum()}')

def report(tag, labels, centers):
    for label_mask, ref_lab, name, thresh in [
            (paw, paw_lab, 'paw-white', 20), (ink, None, 'ink', None)]:
        ls = labels[label_mask]
        vals, cts = np.unique(ls, return_counts=True)
        if name == 'paw-white':
            labs = rgb2lab(centers[vals][None]/255.0)[0]
            de = deltaE_ciede2000(np.tile(ref_lab, (len(vals),1)), labs)
            share = cts[de < thresh].sum()/cts.sum()
        else:
            lums = 0.299*centers[vals][:,0] + 0.587*centers[vals][:,1] + 0.114*centers[vals][:,2]
            share = cts[lums < 70].sum()/cts.sum()
        print(f'  {name:9s} share {share:5.2f}  ({len(vals)} labels)', end='')
    print(f'   [{tag}]')

labels, centers = _quantize(img, 16, 0)
report('quantize', labels, centers)
labels, centers = _consolidate_palette(labels, centers, 12.0)
labels, centers = _merge_shadow_tones(labels, centers)
report('consolidate+shadow', labels, centers)
labels = _own_transitions(labels, centers)
report('own_transitions', labels, centers)
labels = _despeckle_labels(labels, 120, centers)
report('despeckle', labels, centers)
labels = _smooth_labels(labels, len(centers), centers=centers)
labels = _dissolve_speckle(labels, centers, 300)
report('smooth+dissolve', labels, centers)
