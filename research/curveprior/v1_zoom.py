"""Deep-zoom eye check for door 2: what does the normal-offset gap LOOK like?

Picks holdout points across the |t| range (small / medium / large oracle
offsets), renders x16 crops of the SOURCE image with our curve (red), Recraft
(green), and the oracle-snapped point (yellow dot + normal ray). The eye
answers: is Recraft finding a truer edge, or redrawing to taste?

Run: .venv/bin/python research/curveprior/v1_zoom.py
"""
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v1_probe import (PAIRS, HOLDOUT, DS, GATE_CHAMFER, GATE_CENTROID,
                      resample_step, normals, chamfer, ray_project,
                      load_image, close_pts)

OUTDIR = os.path.dirname(os.path.abspath(__file__))
Z = 16                       # zoom factor per IMAGE px
HALF = 14.0                  # crop half-size, canvas px


def main():
    recs = [json.loads(l) for l in open(PAIRS)]
    cands = []               # (|t|, stem, ours, theirs, closed, i, toff)
    for d in recs:
        if d["stem"] not in HOLDOUT:
            continue
        closed = bool(d["closed"])
        ours = resample_step(np.asarray(d["our_pts"]), DS, closed)
        theirs = resample_step(np.asarray(d["their_pts"]), DS, closed)
        cen = float(np.linalg.norm(ours.mean(0) - theirs.mean(0)))
        c0 = chamfer(close_pts(ours, closed), close_pts(theirs, closed))
        if c0 > GATE_CHAMFER or cen > GATE_CENTROID:
            continue
        _, nrm = normals(ours, closed)
        toff, valid = ray_project(ours, nrm, close_pts(theirs, closed))
        for i in np.nonzero(valid)[0][::4]:
            cands.append((abs(float(toff[i])), d["stem"], ours, theirs,
                          closed, int(i), float(toff[i]), nrm))
    cands.sort(key=lambda c: c[0])
    # sample across the |t| range, skewed to the informative middle+top
    qs = [0.30, 0.55, 0.70, 0.80, 0.87, 0.92, 0.95, 0.97, 0.985, 0.995]
    picks, seen = [], set()
    for q in qs:
        j = int(q * (len(cands) - 1))
        while j in seen:
            j += 7
        seen.add(j)
        picks.append(cands[j % len(cands)])

    tiles = []
    for absr, stem, ours, theirs, closed, i, toff, nrm in picks:
        lab, scale = load_image(stem)
        img = cv2.cvtColor((cv2.cvtColor(lab, cv2.COLOR_Lab2RGB) * 255)
                           .astype(np.uint8), cv2.COLOR_RGB2BGR)
        p = ours[i]
        lo = ((p - HALF) * scale).astype(int)
        hi = np.ceil((p + HALF) * scale).astype(int)
        h, w = img.shape[:2]
        x0, y0 = max(0, lo[0]), max(0, lo[1])
        x1, y1 = min(w, hi[0]), min(h, hi[1])
        if x1 - x0 < 4 or y1 - y0 < 4:
            continue
        big = cv2.resize(img[y0:y1, x0:x1], None, fx=Z, fy=Z,
                         interpolation=cv2.INTER_NEAREST)

        def cpt(q):
            return tuple(np.round((np.asarray(q) * scale - [x0, y0]) * Z)
                         .astype(int))

        def draw(poly, color, wpx=2):
            pts = np.array([cpt(q) for q in close_pts(poly, closed)])
            cv2.polylines(big, [pts], False, color, wpx, cv2.LINE_AA)
        draw(ours, (0, 0, 255))
        draw(theirs, (0, 200, 0))
        n = nrm[i]
        a = cpt(p - n * 6)
        b = cpt(p + n * 6)
        cv2.line(big, a, b, (255, 200, 0), 1, cv2.LINE_AA)
        cv2.circle(big, cpt(p), 5, (0, 0, 255), -1, cv2.LINE_AA)
        cv2.circle(big, cpt(p + n * toff), 5, (0, 220, 255), -1, cv2.LINE_AA)
        cv2.putText(big, f"{stem} t={toff:+.2f}px", (6, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 3,
                    cv2.LINE_AA)
        cv2.putText(big, f"{stem} t={toff:+.2f}px", (6, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
        tiles.append(big)

    th = max(t.shape[0] for t in tiles)
    tw = max(t.shape[1] for t in tiles)
    rows_, cols = 2, 5
    grid = np.full((rows_ * th + 6, cols * tw + 8, 3), 255, np.uint8)
    for k, t_ in enumerate(tiles[:rows_ * cols]):
        r, c = divmod(k, cols)
        grid[r * (th + 2):r * (th + 2) + t_.shape[0],
             c * (tw + 2):c * (tw + 2) + t_.shape[1]] = t_
    out = os.path.join(OUTDIR, "v1_zoom.png")
    cv2.imwrite(out, grid)
    print(f"wrote {out} (red=ours green=recraft yellow=oracle target, "
          f"x{Z} image px)")


if __name__ == "__main__":
    main()
