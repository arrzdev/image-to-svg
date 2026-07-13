"""Disk-cached experiment harness — iterate in seconds, not minutes.

Full engine runs cost 2-7 min, which throttles research. Every expensive
stage here is memoized on disk keyed by (image bytes, stage, params): change
one fitting parameter and only fitting re-runs; the k-means partition, the
prep rasters, even DV results for identical configs come back instantly.

Usage:
    from testbed import Testbed
    tb = Testbed("elephant.jpg")                    # data/inputs/ or a path
    labels, centers = tb.labels(num_colors=16)      # cached partition
    svg = tb.svg(tol=3.0, smooth_win=9)             # cached fit
    ref = tb.dv(tol=3.0, smooth_win=9)              # cached refinement
    print(tb.score(svg))                            # cached metrics
    tb.crops({"mine": svg,
              "recraft": open("data/targets/elephant.svg").read()},
             out="exp1.png")                        # vision grid: original |
                                                    # variants side by side
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(HERE))

CACHE = HERE.parent / "outputs" / "_cache"
CACHE.mkdir(parents=True, exist_ok=True)


def _key(*parts) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(p if isinstance(p, bytes) else
                 json.dumps(p, sort_keys=True, default=str).encode())
    return h.hexdigest()[:20]


class Testbed:
    def __init__(self, image, dim: int = 1024):
        from app import SAMPLES
        p = Path(image)
        if not p.exists():
            p = next(iter(SAMPLES.glob(p.stem + ".*")))
        self.raw = p.read_bytes()
        self.name = p.stem
        self.dim = dim
        self._prep = None

    # ---------------------------------------------------------- stages
    def prep(self):
        """(proc_png_path, eval_rgb ndarray, (ow, oh)) — cached in-process."""
        if self._prep is None:
            from app import _prepare
            proc, ev, (ow, oh) = _prepare(self.raw, self.dim)
            path = CACHE / f"proc_{_key(self.raw, self.dim)}.png"
            if not path.exists():
                proc.save(path)
            self._prep = (str(path), np.asarray(ev), (ow, oh),
                          np.asarray(proc))
        return self._prep

    def labels(self, **params):
        """Quantized + cleaned label map. params: num_colors, seed, merge_de,
        min_area, blur (shared_boundary semantics)."""
        pp, _, _, proc = self.prep()
        k = CACHE / f"labels_{_key(self.raw, self.dim, params)}.npz"
        if k.exists():
            z = np.load(k)
            return z["labels"], z["centers"]
        import cv2
        from pipelines.quantize_contours import (
            _quantize, _consolidate_palette, _despeckle_labels, _smooth_labels)
        img = proc.copy()
        blur = params.get("blur", 1)
        if blur:
            img = cv2.medianBlur(img, blur * 2 + 1)
        L, C = _quantize(img, params.get("num_colors", 16), params.get("seed", 0))
        md = params.get("merge_de", 12.0)
        if md > 0:
            L, C = _consolidate_palette(L, C, md)
            L = _despeckle_labels(L, max(params.get("min_area", 120), 16), C)
            L = _smooth_labels(L, len(C), centers=C)
        np.savez_compressed(k, labels=L, centers=C)
        return L, C

    def ctx(self, **params):
        """shared_boundary build_context (graph rebuilt fresh — it's ~50ms;
        the label map above is the slow part and comes from cache)."""
        from pipelines import get_pipeline
        pp, _, _, _ = self.prep()
        return get_pipeline("shared_boundary").build_context(pp, params)

    def svg(self, **params) -> str:
        """Fitted shared-boundary SVG at original size. Cached."""
        k = CACHE / f"svg_{_key(self.raw, self.dim, params)}.svg"
        if k.exists():
            return k.read_text()
        from svgutil import fit_svg_size
        _, _, (ow, oh), _ = self.prep()
        s = fit_svg_size(self.ctx(**params)["svg"], ow, oh)
        k.write_text(s)
        return s

    def dv(self, _dv: dict | None = None, **params) -> str:
        """Shared-edge refined SVG. _dv: refine_shared_v2 kwargs. Cached."""
        k = CACHE / f"dv_{_key(self.raw, self.dim, params, _dv or {})}.svg"
        if k.exists():
            return k.read_text()
        import refine_shared_v2 as RS
        from svgutil import fit_svg_size
        _, _, (ow, oh), proc = self.prep()
        s = RS.refine_shared(self.ctx(**params), proc, **(_dv or {}))
        s = fit_svg_size(s, ow, oh)
        k.write_text(s)
        return s

    # ---------------------------------------------------------- judging
    def target(self):
        """The Recraft 'holy grail' SVG for this input, or None if we don't
        have it yet (placeholder files in data/targets/ are ignored). Matched
        by basename: data/inputs/<name>.* -> data/targets/<name>.svg."""
        p = HERE.parent / "data" / "targets" / (self.name + ".svg")
        if not p.exists():
            return None
        s = p.read_text()
        return s if s.lstrip().startswith("<") else None   # skip placeholders

    def score(self, svg: str) -> dict:
        k = CACHE / f"m_{_key(self.raw, self.dim, svg)}.json"
        if k.exists():
            return json.loads(k.read_text())
        import metrics as M
        _, ev, _, _ = self.prep()
        m = M.all_metrics(svg, ev)
        k.write_text(json.dumps(m))
        return m

    def crops(self, svgs: dict, out: str, spots=None, zoom: int = 4096,
              size: int = 420):
        """Vision grid: rows = spots, columns = ORIGINAL | each svg variant.
        Returns the output path — Read it and LOOK."""
        from render import svg_to_rgb
        from PIL import Image
        import cv2
        _, ev, (ow, oh), _ = self.prep()
        # honor the image's aspect so original and renders align pixel-perfect
        sc = zoom / max(ow, oh)
        W, H = int(round(ow * sc)), int(round(oh * sc))
        src = cv2.resize(ev, (W, H), interpolation=cv2.INTER_LANCZOS4)
        rendered = {n: svg_to_rgb(s, W, H) for n, s in svgs.items()}
        zoom_w, zoom_h = W, H
        if spots is None:
            spots = [(int(zoom_h*0.38), int(zoom_w*0.42)), (int(zoom_h*0.66), int(zoom_w*0.35)),
                     (int(zoom_h*0.25), int(zoom_w*0.22)), (int(zoom_h*0.5), int(zoom_w*0.6))]
        rows = []
        sep_v = np.full((size, 12, 3), 255, np.uint8)
        for (y, x) in spots:
            y = max(0, min(y, zoom_h - size)); x = max(0, min(x, zoom_w - size))
            cells = [src[y:y+size, x:x+size]]
            for n in svgs:
                cells.append(rendered[n][y:y+size, x:x+size])
            row = cells[0]
            for c in cells[1:]:
                row = np.hstack([row, sep_v, c])
            rows.append(row)
        sep_h = np.full((12, rows[0].shape[1], 3), 255, np.uint8)
        grid = rows[0]
        for r in rows[1:]:
            grid = np.vstack([grid, sep_h, r])
        outp = str((HERE.parent / "outputs" / out))
        Image.fromarray(grid).save(outp)
        return outp

    def full_grid(self, svgs: dict, out: str, grid_n: int = 4, zoom: int = 4096,
                  size: int = 420, rows_per_page: int = 4):
        """FULL-COVERAGE vision grid (MANDATORY before any keep/ship decision —
        research/autoresearch.md, Testing progression §3). Tiles the WHOLE
        zoom render into grid_n x grid_n blocks; each block becomes a row of
        ORIGINAL | <variants...> cells. Emits pages of rows_per_page rows named
        <out>.pageK.png and returns the list of paths — Read and LOOK at every
        page. Focused crops (self.crops) remain for defect diagnosis; this is
        the ship gate. [User-mandated harness extension, 2026-07-08 — additive
        only; does not alter crops/score/metrics.]"""
        from render import svg_to_rgb
        from PIL import Image
        import cv2
        _, ev, (ow, oh), _ = self.prep()
        sc = zoom / max(ow, oh)
        W, H = int(round(ow * sc)), int(round(oh * sc))
        src = cv2.resize(ev, (W, H), interpolation=cv2.INTER_LANCZOS4)
        rendered = {n: svg_to_rgb(s_, W, H) for n, s_ in svgs.items()}
        bw, bh = W // grid_n, H // grid_n
        sep_v = np.full((size, 12, 3), 255, np.uint8)
        pages, rows = [], []
        outp_base = str((HERE.parent / "outputs" / out))
        if outp_base.endswith(".png"):
            outp_base = outp_base[:-4]
        page_i = 0
        for gy in range(grid_n):
            for gx in range(grid_n):
                y0, x0 = gy * bh, gx * bw
                cells = [cv2.resize(src[y0:y0+bh, x0:x0+bw], (size, size),
                                    interpolation=cv2.INTER_AREA)]
                for n in svgs:
                    cells.append(cv2.resize(rendered[n][y0:y0+bh, x0:x0+bw],
                                            (size, size), interpolation=cv2.INTER_AREA))
                row = cells[0]
                for c in cells[1:]:
                    row = np.hstack([row, sep_v, c])
                rows.append(row)
                if len(rows) == rows_per_page:
                    sep_h = np.full((12, rows[0].shape[1], 3), 255, np.uint8)
                    grid = rows[0]
                    for r in rows[1:]:
                        grid = np.vstack([grid, sep_h, r])
                    page_i += 1
                    pth = f"{outp_base}.page{page_i}.png"
                    Image.fromarray(grid).save(pth)
                    pages.append(pth); rows = []
        if rows:
            sep_h = np.full((12, rows[0].shape[1], 3), 255, np.uint8)
            grid = rows[0]
            for r in rows[1:]:
                grid = np.vstack([grid, sep_h, r])
            page_i += 1
            pth = f"{outp_base}.page{page_i}.png"
            Image.fromarray(grid).save(pth)
            pages.append(pth)
        return pages
