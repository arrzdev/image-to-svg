"""findings — turn tilecmp + pathflow signal into a ranked list of DEFECTS that
a coding LLM can read and fix from. This is the piece that closes the auto-loop:

    findings.py  ->  (LLM reads defects, edits the converter)  ->
    tilecmp_loop.py  (gates the edit: keep/revert)  ->  repeat.

A DEFECT is a spatial cluster of same-mode hot tiles (not a raw tile dump). Each
carries: the subsystem to touch, the region, a severity rank, the channel split,
concrete phase-2 geometry evidence (matched cubic ratios, omitted / spurious
strokes, ACTUAL SVG path snippets ours-vs-target), colour dE vs the source, and
an evidence-derived fix direction (with the loop's learned constraints baked in).

    python research/design/findings.py OURS.svg THEIRS.svg \
        --input data/inputs/chopchop.png [--tiles 48] [--md] [--out DIR]

Emits DIR/findings.json (machine) and, with --md, a bug-report markdown to stdout
/ DIR/findings.md that you can hand straight to a coding model.
"""
import argparse
import json
import os
import sys
from collections import deque

import numpy as np

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "models", "quant-11", "src"))
import tilecmp  # noqa: E402
import pathflow  # noqa: E402

SUBSYS = {
    "census": "segmentation / colour-quantisation (how regions are split & how "
              "many paths)",
    "flow": "curve fitting / contour smoothing (how each stroke is drawn)",
    "color": "colour quantisation / palette (fill values)",
    "overall": "mixed — inspect the channel split",
}
MODE_CHANNEL = {"UNDER-RESOLVE": "census", "OVER-FRAGMENT": "census",
                "FITTER": "flow", "COLOR": "color", "MIXED": "overall"}


def _clip(d, n=220):
    d = " ".join(d.split())
    return d if len(d) <= n else d[:n] + " …"


def cluster(res, hot_thr=0.5):
    """8-connected components of hot tiles that share a failure label."""
    n, lab, ov, w = res["n"], res["labels"], res["overall"], res["weight"]
    hot = (ov > hot_thr) & (w > 0)
    seen = np.zeros((n, n), bool)
    out = []
    for i in range(n):
        for j in range(n):
            if not hot[i, j] or seen[i, j]:
                continue
            L = lab[i, j]
            comp, q = [], deque([(i, j)])
            seen[i, j] = True
            while q:
                a, b = q.popleft()
                comp.append((a, b))
                for da in (-1, 0, 1):
                    for db in (-1, 0, 1):
                        x, y = a + da, b + db
                        if (0 <= x < n and 0 <= y < n and not seen[x, y]
                                and hot[x, y] and lab[x, y] == L):
                            seen[x, y] = True
                            q.append((x, y))
            out.append({"mode": L, "tiles": comp})
    return out


def region_evidence(ours_svg, theirs_svg, bbox_px, sample_px, native):
    """Phase-2 evidence for a defect. Structural COUNTS (paths, omissions,
    spurious) come from the whole bbox; the matched-stroke SAMPLE comes from the
    single example tile (`sample_px`) where correspondence is clean (bbox-scale
    matching is fuzzy and inflates turn-dist)."""
    step = (bbox_px[2] - bbox_px[0]) / 8.0 or 4.0
    ours = pathflow.polylines_in_region(ours_svg, bbox_px, native, step)
    theirs = pathflow.polylines_in_region(theirs_svg, bbox_px, native, step)
    tile_px = max(bbox_px[2] - bbox_px[0], bbox_px[3] - bbox_px[1]) or native
    pairs = pathflow.match(ours, theirs, tile_px)
    used_t = {tj for _, tj, _ in pairs}
    used_o = {oi for oi, _, _ in pairs}
    omitted = sorted([t for k, t in enumerate(theirs) if k not in used_t],
                     key=lambda t: -t["length"])
    spurious = [o for k, o in enumerate(ours) if k not in used_o]

    # clean matched-stroke sample from the single example tile
    sstep = (sample_px[2] - sample_px[0]) / 8.0 or 4.0
    so = pathflow.polylines_in_region(ours_svg, sample_px, native, sstep)
    st = pathflow.polylines_in_region(theirs_svg, sample_px, native, sstep)
    spx = max(sample_px[2] - sample_px[0], sample_px[3] - sample_px[1]) or native
    matched = []
    for oi, tj, _ in pathflow.match(so, st, spx):
        o, t = so[oi], st[tj]
        matched.append({"turn_dist": round(pathflow.turning_dist(o["pts"],
                                                                 t["pts"]), 3),
                        "cubic_ours": o["ncubic"], "cubic_theirs": t["ncubic"],
                        "len_ours": round(o["length"]),
                        "len_theirs": round(t["length"]),
                        "ours_d": _clip(o["d"]), "ours_fill": o["fill"],
                        "theirs_d": _clip(t["d"]), "theirs_fill": t["fill"]})
    matched.sort(key=lambda m: -m["turn_dist"])
    return {
        "paths_ours": len(ours), "paths_theirs": len(theirs),
        "matched": matched[:2],
        "omitted_count": len(omitted), "spurious_count": len(spurious),
        "omitted_example": ({"len": round(omitted[0]["length"]),
                             "fill": omitted[0]["fill"],
                             "d": _clip(omitted[0]["d"])} if omitted else None),
    }


def direction(mode, ch, ev):
    """Evidence-derived, cautious fix direction — with loop-learned constraints.
    Always a CANDIDATE; the loop gate decides keep/revert."""
    if mode == "UNDER-RESOLVE":
        return ("Recraft draws strokes here that ours omits "
                f"({ev['omitted_count']} target paths unmatched). Recover them — "
                "but preserve THIN/ELONGATED shapes specifically; do NOT lower "
                "min_area globally (loop iter 1 showed that regresses census).")
    if mode == "OVER-FRAGMENT":
        return ("Ours emits more/smaller paths than Recraft here "
                f"({ev['spurious_count']} spurious ours strokes). Merge adjacent "
                "same-colour regions / raise merge tolerance LOCALLY in this "
                "content, not globally.")
    if mode == "FITTER":
        worst = ev["matched"][0] if ev["matched"] else None
        c = (f" (e.g. a matched stroke: ours {worst['cubic_ours']} cubics vs "
             f"Recraft {worst['cubic_theirs']}, turn-dist {worst['turn_dist']})"
             if worst else "")
        return ("Ours' stroke shape diverges from Recraft's" + c + ". NOTE: the "
                "loop showed cubic COUNT (opttolerance) is NOT the fix and the "
                "straighten post-process is NOT the cause — the faceting is "
                "upstream in the contour polyline. Look at contour extraction / "
                "pre-fit smoothing, not the fitter tolerance.")
    if mode == "COLOR":
        return ("Ours' fill is farther from the source than Recraft's here. "
                "Adjust colour quantisation / palette toward the source in this "
                "region; check gradient flattening (a smooth ramp posterised to "
                "one flat band reads as COLOR).")
    return ("Mixed signal — inspect the channel split and the example tile crop "
            "before acting.")


def analyze(ours_svg, theirs_svg, input_img, n=48, native=2048, hot_thr=0.5,
            min_tiles=3):
    res = tilecmp.compare(ours_svg, theirs_svg, n=n, native=native,
                          input_img=input_img)
    tw = native / n
    ov, w = res["overall"], res["weight"]
    ex = res["extra"]
    ovb = tilecmp._viewbox(ours_svg)
    tvb = tilecmp._viewbox(theirs_svg)
    clusters = cluster(res, hot_thr)
    # a DEFECT is a real spatial region (>= min_tiles); smaller hot specks are
    # summarised, not enumerated, so the report stays actionable.
    minor = [c for c in clusters if len(c["tiles"]) < min_tiles]
    minor_mix = {}
    for c in minor:
        minor_mix[c["mode"]] = minor_mix.get(c["mode"], 0) + len(c["tiles"])
    clusters = [c for c in clusters if len(c["tiles"]) >= min_tiles]
    defects = []
    for c in clusters:
        tiles = c["tiles"]
        sev = float(sum(ov[i, j] * w[i, j] for i, j in tiles))
        ii = [i for i, j in tiles]
        jj = [j for i, j in tiles]
        bbox_px = (min(jj) * tw, min(ii) * tw, (max(jj) + 1) * tw,
                   (max(ii) + 1) * tw)
        rep = max(tiles, key=lambda t: ov[t])
        sample_px = (rep[1] * tw, rep[0] * tw, (rep[1] + 1) * tw,
                     (rep[0] + 1) * tw)
        ch_scores = {k: round(float(np.mean([res[k][i, j] for i, j in tiles])), 3)
                     for k in ("census", "flow", "color")}
        de_o = ex["dE_ours_src"]
        de_t = ex["dE_theirs_src"]
        color_ev = None
        if de_o is not None:
            color_ev = {"dE_ours_vs_source":
                        round(float(np.mean([de_o[i, j] for i, j in tiles])), 1),
                        "dE_recraft_vs_source":
                        round(float(np.mean([de_t[i, j] for i, j in tiles])), 1)}
        ev = region_evidence(ours_svg, theirs_svg, bbox_px, sample_px, native)
        defects.append({
            "mode": c["mode"], "subsystem": SUBSYS[MODE_CHANNEL[c["mode"]]],
            "severity": round(sev, 1), "n_tiles": len(tiles),
            "region_tiles": {"rows": [min(ii), max(ii)],
                             "cols": [min(jj), max(jj)]},
            "region_frac": [round(min(jj) / n, 2), round(min(ii) / n, 2),
                            round((max(jj) + 1) / n, 2),
                            round((max(ii) + 1) / n, 2)],
            "example_tile": [int(rep[0]), int(rep[1])],
            "channel_scores": ch_scores,
            "color_evidence": color_ev,
            "geometry_evidence": ev,
            "direction": direction(c["mode"], MODE_CHANNEL[c["mode"]], ev),
        })
    defects.sort(key=lambda d: -d["severity"])
    tot = sum(d["severity"] for d in defects) + 1e-9
    for k, d in enumerate(defects):
        d["rank"] = k + 1
        d["severity_pct"] = round(100 * d["severity"] / tot, 1)
    return {"agg": res["agg"], "n_defects": len(defects), "defects": defects,
            "minor_hotspots": {"count": len(minor), "mix": minor_mix},
            "viewbox": {"ours": f"{ovb[2]:.0f}x{ovb[3]:.0f}",
                        "recraft": f"{tvb[2]:.0f}x{tvb[3]:.0f}"}}


def to_markdown(rep, meta):
    mh = rep["minor_hotspots"]
    vb = rep["viewbox"]
    L = [f"# Conversion defects — {meta}",
         f"overall distance to Recraft: **{rep['agg']['overall']:.3f}**  "
         f"(census {rep['agg']['census']:.3f} · flow {rep['agg']['flow']:.3f} · "
         f"color {rep['agg']['color']:.3f})",
         f"{rep['n_defects']} region defects (+ {mh['count']} minor scattered "
         f"hotspots: {mh['mix']}), ranked by severity. Fix the top ones; re-run "
         f"the loop to gate each change.",
         f"**coordinate note:** ours `d` is in a {vb['ours']} viewBox, Recraft "
         f"`d` in {vb['recraft']} — compare stroke SHAPE/counts, not raw numbers."
         f"\n"]
    for d in rep["defects"][:8]:
        L.append(f"## #{d['rank']} {d['mode']} — {d['severity_pct']}% of defect "
                 f"weight  ·  {d['n_tiles']} tiles")
        L.append(f"- **subsystem:** {d['subsystem']}")
        r = d["region_frac"]
        L.append(f"- **where:** normalised region x[{r[0]}–{r[2]}] "
                 f"y[{r[1]}–{r[3]}]  (example tile {d['example_tile']})")
        L.append(f"- **channels:** census {d['channel_scores']['census']} · "
                 f"flow {d['channel_scores']['flow']} · "
                 f"color {d['channel_scores']['color']}")
        if d["color_evidence"]:
            ce = d["color_evidence"]
            L.append(f"- **colour:** ours ΔE {ce['dE_ours_vs_source']} vs source, "
                     f"Recraft ΔE {ce['dE_recraft_vs_source']} vs source")
        g = d["geometry_evidence"]
        L.append(f"- **geometry:** {g['paths_ours']} ours vs {g['paths_theirs']} "
                 f"Recraft paths in region; {g['omitted_count']} target strokes "
                 f"omitted, {g['spurious_count']} spurious ours strokes")
        if g["matched"]:
            m = g["matched"][0]
            L.append(f"- **worst matched stroke:** ours {m['cubic_ours']} cubics "
                     f"vs Recraft {m['cubic_theirs']}, turn-dist {m['turn_dist']}")
            L.append(f"  - ours: `{m['ours_d']}` fill `{m['ours_fill']}`")
            L.append(f"  - Recraft: `{m['theirs_d']}` fill `{m['theirs_fill']}`")
        if g["omitted_example"]:
            oe = g["omitted_example"]
            L.append(f"- **omitted target stroke:** len {oe['len']}px "
                     f"fill `{oe['fill']}` — `{oe['d']}`")
        L.append(f"- **direction:** {d['direction']}\n")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ours"); ap.add_argument("theirs")
    ap.add_argument("--input", default=None)
    ap.add_argument("--tiles", type=int, default=48)
    ap.add_argument("--native", type=int, default=2048)
    ap.add_argument("--hot", type=float, default=0.5)
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rep = analyze(open(a.ours).read(), open(a.theirs).read(), a.input,
                  n=a.tiles, native=a.native, hot_thr=a.hot)
    meta = f"{os.path.basename(a.ours)} vs {os.path.basename(a.theirs)}"
    md = to_markdown(rep, meta)
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        json.dump(rep, open(os.path.join(a.out, "findings.json"), "w"), indent=2)
        open(os.path.join(a.out, "findings.md"), "w").write(md)
        print(f"wrote {a.out}/findings.json and findings.md "
              f"({rep['n_defects']} defects)")
    if a.md or not a.out:
        print(md)


if __name__ == "__main__":
    main()
