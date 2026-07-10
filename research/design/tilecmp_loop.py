"""tilecmp-driven improvement loop.

One iteration = baseline sweep -> candidate sweep (a param change) -> a 3-part
GATE -> keep/revert decision, an eye-confirm montage, and a ledger line.

The gate is deliberately mode-targeted and anti-gaming (see tilecmp.py):
  1. the TARGET failure mode's ink-weighted share must DROP,
  2. corpus overall distance must NOT regress,
  3. a montage of the previously-worst tiles (source | baseline | candidate |
     Recraft) is written so the eye confirms the fix on the exact tiles — the
     metric only points; the eye still rules.

    python research/design/tilecmp_loop.py --target UNDER-RESOLVE \
        --set min_area=40 [--set num_colors=20] [--tiles 40] [--engine quant-12]

Baseline (default params) is cached under research/design/.tilecmp_cache/.
"""
import argparse
import glob
import hashlib
import importlib.util as u
import json
import os
import pickle
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "models", "quant-11", "src"))
import tilecmp  # noqa: E402
from render import svg_to_rgb  # noqa: E402

ROOT = os.path.join(HERE, "..", "..")
CACHE = os.path.join(HERE, ".tilecmp_cache")
LEDGER = os.path.join(HERE, "tilecmp_loop_ledger.jsonl")
MODE_CHANNEL = {"UNDER-RESOLVE": "census", "OVER-FRAGMENT": "census",
                "FITTER": "flow", "COLOR": "color", "MIXED": "overall"}


def load_engine(name):
    spec = u.spec_from_file_location("eng", os.path.join(ROOT, "models", name,
                                                         "entry.py"))
    m = u.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def input_for(stem):
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = os.path.join(ROOT, "data", "inputs", stem + ext)
        if os.path.exists(p):
            return p


def sweep(eng, params, tiles):
    """Run the engine + tilecmp across the whole target corpus."""
    targets = sorted(glob.glob(os.path.join(ROOT, "data", "targets", "*.svg")))
    per = {}
    mix = {}
    ch = {"census": [], "flow": [], "color": [], "overall": []}
    for tp in targets:
        stem = os.path.splitext(os.path.basename(tp))[0]
        inp = input_for(stem)
        if inp is None:
            continue
        theirs = open(tp).read()
        if not theirs.lstrip().startswith("<"):
            continue
        ours = eng.run(inp, params) if params else eng.run(inp)
        res = tilecmp.compare(ours, theirs, n=tiles, native=2048, input_img=inp)
        w = res["weight"]
        imix = {}
        for i in range(tiles):
            for j in range(tiles):
                if w[i, j] > 0:
                    lab = res["labels"][i, j]
                    imix[lab] = imix.get(lab, 0.0) + w[i, j]
                    mix[lab] = mix.get(lab, 0.0) + w[i, j]
        worst = sorted([(float(res["overall"][i, j]), i, j)
                        for i in range(tiles) for j in range(tiles)
                        if w[i, j] > 0], reverse=True)[:6]
        per[stem] = {"agg": res["agg"], "mix": imix, "worst": worst,
                     "ours": ours}
        for k in ("census", "flow", "color", "overall"):
            ch[k].append(res["agg"][k])
    tot = sum(mix.values()) + 1e-9
    corpus = {k: float(np.mean(v)) for k, v in ch.items()}
    corpus["mode_frac"] = {k: v / tot for k, v in mix.items()}
    return {"per": per, "corpus": corpus, "params": params, "tiles": tiles}


def cached_baseline(eng, name, tiles):
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.md5(f"{name}|{tiles}|default".encode()).hexdigest()[:12]
    path = os.path.join(CACHE, f"base_{name}_{tiles}_{key}.pkl")
    if os.path.exists(path):
        return pickle.load(open(path, "rb"))
    base = sweep(eng, None, tiles)
    pickle.dump(base, open(path, "wb"))
    return base


def montage(stem, base_sw, cand_sw, tiles, out):
    """source | baseline-ours | candidate-ours | Recraft, on baseline's worst
    tiles for `stem` — so the eye confirms the fix on the exact hot tiles."""
    inp = input_for(stem)
    theirs = open(os.path.join(ROOT, "data", "targets", stem + ".svg")).read()
    C = 2048
    src = np.asarray(Image.open(inp).convert("RGB").resize((C, C)))
    bimg = np.asarray(svg_to_rgb(base_sw["per"][stem]["ours"], C, C))[:, :, :3]
    cimg = np.asarray(svg_to_rgb(cand_sw["per"][stem]["ours"], C, C))[:, :, :3]
    timg = np.asarray(svg_to_rgb(theirs, C, C))[:, :, :3]
    cols = [("source", src), ("baseline", bimg), ("candidate", cimg),
            ("Recraft", timg)]
    tw = C // tiles
    CELL, PAD = 210, 6
    worst = base_sw["per"][stem]["worst"]
    W = PAD + len(cols) * (CELL + PAD)
    H = 18 + PAD + len(worst) * (CELL + PAD)
    cv = Image.new("RGB", (W, H), (28, 28, 28))
    dr = ImageDraw.Draw(cv)
    dr.text((6, 3), f"{stem}: baseline vs candidate on baseline's worst tiles",
            fill=(255, 255, 0))
    for r, (sc, i, j) in enumerate(worst):
        y0, x0 = i * tw, j * tw
        a0, b0 = max(0, y0 - tw), max(0, x0 - tw)
        a1, b1 = min(C, y0 + 2 * tw), min(C, x0 + 2 * tw)
        yy = 18 + PAD + r * (CELL + PAD)
        for c, (name, img) in enumerate(cols):
            crop = Image.fromarray(img[a0:a1, b0:b1].astype(np.uint8)).resize(
                (CELL, CELL), Image.NEAREST)
            d2 = ImageDraw.Draw(crop)
            px = (x0 - b0) / (b1 - b0) * CELL
            py = (y0 - a0) / (a1 - a0) * CELL
            pw = tw / (b1 - b0) * CELL
            d2.rectangle([px, py, px + pw, py + pw], outline=(255, 0, 0), width=2)
            xx = PAD + c * (CELL + PAD)
            cv.paste(crop, (xx, yy))
            if r == 0:
                dr.text((xx + 4, yy - 13), name, fill=(255, 255, 255))
    cv.save(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, choices=list(MODE_CHANNEL))
    ap.add_argument("--set", action="append", default=[],
                    help="param override k=v (repeatable)")
    ap.add_argument("--tiles", type=int, default=40)
    ap.add_argument("--engine", default="quant-12")
    a = ap.parse_args()

    params = {}
    for kv in a.set:
        k, v = kv.split("=")
        params[k] = float(v) if ("." in v or "e" in v.lower()) else int(v)

    eng = load_engine(a.engine)
    print(f"[baseline] {a.engine} default params, {a.tiles}x{a.tiles} ...")
    base = cached_baseline(eng, a.engine, a.tiles)
    print(f"[candidate] {params} ...")
    cand = sweep(eng, params, a.tiles)

    ch = MODE_CHANNEL[a.target]
    bmf = base["corpus"]["mode_frac"].get(a.target, 0.0)
    cmf = cand["corpus"]["mode_frac"].get(a.target, 0.0)
    b_over, c_over = base["corpus"]["overall"], cand["corpus"]["overall"]
    b_ch, c_ch = base["corpus"][ch], cand["corpus"][ch]

    mode_drop = cmf < bmf - 0.005
    no_regress = c_over <= b_over + 0.003
    verdict = "PASS" if (mode_drop and no_regress) else "REVERT"

    print("\n=== GATE ===")
    print(f"  target mode      : {a.target}  (channel: {ch})")
    print(f"  {a.target:14s} share : {bmf*100:5.1f}%  ->  {cmf*100:5.1f}%"
          f"   {'DROP OK' if mode_drop else 'no drop'}")
    print(f"  {ch:14s} dist  : {b_ch:.3f}  ->  {c_ch:.3f}")
    print(f"  overall dist     : {b_over:.3f}  ->  {c_over:.3f}"
          f"   {'ok' if no_regress else 'REGRESSED'}")
    print("  per-channel corpus: "
          + "  ".join(f"{k}={base['corpus'][k]:.3f}->{cand['corpus'][k]:.3f}"
                      for k in ("census", "flow", "color")))
    print(f"  VERDICT: {verdict}")

    # eye-confirm montage on the image most dominated by the target mode
    pick = max(base["per"], key=lambda s: base["per"][s]["mix"].get(a.target, 0))
    out = os.path.join(HERE, "tilecmp_out",
                       f"loop_{a.target}_{pick}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    montage(pick, base, cand, a.tiles, out)
    print(f"  montage ({pick}): {out}")

    rec = {"t": int(time.time()), "engine": a.engine, "target": a.target,
           "params": params, "verdict": verdict,
           "mode_frac": [bmf, cmf], "overall": [b_over, c_over],
           "channel": [ch, b_ch, c_ch], "montage": out}
    with open(LEDGER, "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(f"  ledger += {LEDGER}")


if __name__ == "__main__":
    main()
