"""Run 8: measure Recraft's palette re-grading as (dL, dC, dh) in OKLCH.

For each of the 8 paired targets: render OUR current output and the Recraft
SVG, extract area-weighted palettes, match entries by OKLab distance, and
report per-entry deltas (recraft - ours). If shadow/midtone deltas cluster
across images, those are Recraft's ramp constants (data, not taste).

Measurement only — no pipeline changes.
"""
import sys
sys.path.insert(0, "backend")
import numpy as np
import pathlib

from testbed import Testbed
from pipelines import get_pipeline
from svgutil import fit_svg_size
from render import svg_to_rgb


def srgb_to_oklch(rgb):
    """rgb in [0,1], returns (L, C, h_deg). Björn Ottosson's OKLab."""
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    l = 0.4122214708 * c[..., 0] + 0.5363325363 * c[..., 1] + 0.0514459929 * c[..., 2]
    m = 0.2119034982 * c[..., 0] + 0.6806995451 * c[..., 1] + 0.1073969566 * c[..., 2]
    s = 0.0883024619 * c[..., 0] + 0.2817188376 * c[..., 1] + 0.6299787005 * c[..., 2]
    l_, m_, s_ = np.cbrt(l), np.cbrt(m), np.cbrt(s)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    C = np.hypot(a, b)
    h = np.degrees(np.arctan2(b, a)) % 360.0
    return L, C, h


def palette(svg, res=512, min_cov=0.01):
    """Area-weighted palette: unique colors of the render with coverage."""
    img = svg_to_rgb(svg, res, res).reshape(-1, 3)
    cols, counts = np.unique(img, axis=0, return_counts=True)
    # merge near-identical (AA) colors into their heaviest neighbor
    order = np.argsort(counts)[::-1]
    kept, kcnt = [], []
    for i in order:
        c = cols[i].astype(int)
        for j, k in enumerate(kept):
            if np.abs(c - k).sum() < 24:
                kcnt[j] += counts[i]
                break
        else:
            kept.append(c)
            kcnt.append(int(counts[i]))
    tot = float(sum(kcnt))
    out = [(np.array(k), c / tot) for k, c in zip(kept, kcnt) if c / tot >= min_cov]
    return out


NAMES = ["elephant", "rabbit", "fox", "chopchop", "crystals", "mountain",
         "logo-geometric", "monster-flat-line"]

rows = []
for nm in NAMES:
    ext = ".jpg" if pathlib.Path(f"data/inputs/{nm}.jpg").exists() else ".png"
    tb = Testbed(nm + ext)
    rec = tb.target()
    if not rec:
        continue
    pp, _, (ow, oh), _ = tb.prep()
    ours = fit_svg_size(get_pipeline("contour_lines").run(pp, {}), ow, oh)
    P_o, P_r = palette(ours), palette(rec)
    # match each of OUR entries to nearest recraft entry in OKLab
    for co, cov in P_o:
        Lo, Co, ho = srgb_to_oklch(co[None].astype(float) / 255.0)
        best, bd = None, 1e9
        for cr, covr in P_r:
            Lr, Cr, hr = srgb_to_oklch(cr[None].astype(float) / 255.0)
            dh = np.radians((hr - ho + 180) % 360 - 180)
            d = float((Lr - Lo) ** 2 + Co ** 2 + Cr ** 2
                      - 2 * Co * Cr * np.cos(dh))
            if d < bd:
                bd, best = d, (cr, float(Lr), float(Cr), float(hr))
        cr, Lr, Cr, hr = best
        dL = Lr - float(Lo)
        dC = Cr - float(Co)
        dh = ((hr - float(ho) + 180) % 360) - 180
        rows.append((nm, tuple(co), tuple(cr), cov, float(Lo), float(Co),
                     dL, dC, dh))

print(f"{'target':<18}{'ours':>9} {'recraft':>9} {'cov%':>5} {'L':>5} {'C':>5}"
      f" {'dL':>7} {'dC':>7} {'dh':>7}")
for r in rows:
    nm, co, cr, cov, L, C, dL, dC, dh = r
    print(f"{nm:<18}#{co[0]:02x}{co[1]:02x}{co[2]:02x} "
          f"#{cr[0]:02x}{cr[1]:02x}{cr[2]:02x} {cov*100:5.1f} {L:5.2f} {C:5.3f}"
          f" {dL:+7.3f} {dC:+7.3f} {dh:+7.1f}")

# cluster check on CHROMATIC midtones (C > 0.02, 0.35 < L < 0.9, cov > 2%)
sel = [r for r in rows if r[5] > 0.02 and 0.35 < r[4] < 0.9 and r[3] > 0.02]
if sel:
    dLs = np.array([r[6] for r in sel]); dCs = np.array([r[7] for r in sel])
    dhs = np.array([r[8] for r in sel])
    print(f"\nchromatic midtones n={len(sel)}:"
          f" dL {np.median(dLs):+.3f}±{dLs.std():.3f}"
          f" dC {np.median(dCs):+.3f}±{dCs.std():.3f}"
          f" dh {np.median(dhs):+.1f}±{dhs.std():.1f}")
