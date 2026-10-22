"""autoresearch_loop — deterministic glue for the FULL-AUTO tilecmp loop
(USER 2026-07-10 regime). This is the loop WRAPPER: it does everything except the
coding, which a coding agent does in an isolated git worktree.

One iteration:
    python research/loop/autoresearch_loop.py --brief
        -> picks the top actionable defect across the corpus, prints a complete
           coding-agent brief, and records the target mode in .loop_state.json
    # <orchestrator spawns a coding agent in a git worktree with that brief>
    python research/loop/autoresearch_loop.py --gate <WORKTREE_PATH>
        -> INDEPENDENT gate of the worktree engine vs the frozen baseline; refuses
           any diff touching the locked scorer; on PASS applies the diff to the
           live tree, commits, re-freezes the baseline, logs KEEP; on REVERT logs
           DISCARD. (Anti-gaming: the wrapper gates, not the editor.)
Setup once:
    python research/loop/autoresearch_loop.py --freeze   # baseline := live engine

Design notes: the engine is deterministic at the tilecmp corpus level, so the gate
is reliable. FITTER is excluded from targeting by default (loop proved it's an
upstream contour problem, not a quick win). Locked files (may never be edited by
the loop): everything under eval/ (tilecmp*.py, findings.py, pathflow.py, ...).
"""
import argparse
import glob
import json
import os
import pickle
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
EVAL = os.path.join(ROOT, "eval")
VENV = os.path.join(ROOT, ".venv", "bin", "python")
BASELINE = os.path.join(EVAL, ".tilecmp_cache", "gate_base.pkl")
STATE = os.path.join(HERE, ".loop_state.json")
LEDGER = os.path.join(HERE, "autoresearch_loop_ledger.jsonl")
sys.path.insert(0, EVAL)
import tilecmp_loop as L  # noqa: E402
import findings as F      # noqa: E402

# images used to source concrete defect evidence for the brief (hard ones)
EVIDENCE_IMAGES = ["crystals", "app-asset", "fox", "pizza-box", "rabbit"]
LOCKED = ("eval/", "ar_eval")

BOILERPLATE = """
## HARD CONSTRAINTS
- Edit ONLY files under `engines/quant/quant-11/src/`. Keep the `run(path, params)->svg` contract.
- DO NOT modify `eval/tilecmp*.py`, `findings.py`, `pathflow.py`, or any
  `*ar_eval*`/scorer — that is the LOCKED gate; editing it = automatic failure.
- Do NOT lower `min_area` globally (a prior iteration proved it regresses census/overall).
- Make ONE focused, well-reasoned change. Not scattershot.

## Environment
- Interpreter: `{venv}` (the main repo venv; your worktree has no `.venv`). Run all
  commands FROM your worktree root so scripts load YOUR edited engine. Sanity-check
  the engine runs (generate one SVG) BEFORE editing.

## Gate protocol (decides keep/revert — corpus-wide, deterministic)
1. BEFORE editing, freeze the pristine baseline:
   `{venv} eval/tilecmp_gate.py --set-baseline eval/.tilecmp_cache/gate_base.pkl --tiles 40`
2. Make your focused edit under `engines/quant/quant-11/src/`.
3. Gate it:
   `{venv} eval/tilecmp_gate.py --baseline eval/.tilecmp_cache/gate_base.pkl --tiles 40 --target-mode {mode}`
   Exit 0 = PASS (keep). Exit 1 = REVERT.

## Report back (raw data, not fluff)
- File(s) changed + 2-3 line description + `git diff`.
- Full gate output (baseline vs candidate overall/census/flow/color, {mode} share, VERDICT, exit code).
- Honest read on why it passed/reverted.
- LEAVE your change in the worktree — do NOT `git revert`/`checkout` it and do NOT
  commit, EVEN IF your own self-gate reverts. The orchestrator re-gates you
  independently (anti-gaming) and decides keep/discard; if you self-revert it has
  nothing to verify. Only exception: if your edit crashes the engine, revert to a
  running state.
"""


def input_for(stem):
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = os.path.join(ROOT, "data", "inputs", stem + ext)
        if os.path.exists(p):
            return p


def freeze(tiles):
    os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
    s = L.sweep(L.load_engine("quant-12"), None, tiles)
    pickle.dump(s, open(BASELINE, "wb"))
    c = s["corpus"]
    print(f"  baseline frozen: overall={c['overall']:.4f} census={c['census']:.4f} "
          f"flow={c['flow']:.4f} color={c['color']:.4f}")
    print(f"  fingerprint: " + "  ".join(f"{k}={v*100:.0f}%" for k, v in
          sorted(c["mode_frac"].items(), key=lambda x: -x[1])))


def brief(tiles, exclude):
    eng = L.load_engine("quant-12")
    cand = []
    for stem in EVIDENCE_IMAGES[:3]:
        inp = input_for(stem)
        if not inp:
            continue
        theirs = open(os.path.join(ROOT, "data", "targets", stem + ".svg")).read()
        rep = F.analyze(eng.run(inp), theirs, inp, n=48)
        for d in rep["defects"][:3]:
            if d["mode"] not in exclude:
                cand.append((d["severity"], stem, d))
    if not cand:
        print("no actionable defect found (all excluded?)")
        return
    cand.sort(key=lambda x: -x[0])
    sev, stem, d = cand[0]
    json.dump({"mode": d["mode"], "stem": stem, "ts": int(time.time())},
              open(STATE, "w"))
    g = d["geometry_evidence"]
    ce = d.get("color_evidence")
    print(f"# Auto-loop iteration brief — target: {d['mode']}\n")
    print(f"You are ONE iteration of an automatic image→SVG improvement loop. Make "
          f"ONE focused change to `engines/quant/quant-11/src/` that reduces **{d['mode']}** "
          f"defects (subsystem: {d['subsystem']}), then gate it. You are in an "
          f"isolated git worktree.\n")
    print(f"## Concrete example ({stem}, region {d['region_frac']})")
    print(f"- channels: census {d['channel_scores']['census']} · flow "
          f"{d['channel_scores']['flow']} · color {d['channel_scores']['color']}")
    if ce:
        print(f"- colour: ours ΔE {ce['dE_ours_vs_source']} vs source, Recraft "
              f"ΔE {ce['dE_recraft_vs_source']}")
    print(f"- geometry: {g['paths_ours']} ours vs {g['paths_theirs']} Recraft paths; "
          f"{g['omitted_count']} target strokes omitted, {g['spurious_count']} spurious")
    print(f"- direction: {d['direction']}")
    print(f"\nGather more evidence yourself with `findings.py` on other images. "
          f"Then find the responsible code in `engines/quant/quant-11/src/` and fix it.")
    print(BOILERPLATE.format(venv=VENV, mode=d["mode"]))
    print(f"\n(target mode recorded in {STATE}; run `--gate <worktree>` after the edit.)")


def _diff_names(worktree):
    # Normalize the index first: a worktree whose conflicts were resolved by
    # editing files (index still unmerged) makes plain `git diff` emit
    # combined-diff format that `git apply` rejects (bit us on composite-it8).
    # Staging everything turns both clean and conflict-resolved worktrees into
    # ordinary --cached diffs.
    subprocess.run(["git", "-C", worktree, "add", "-A"],
                   capture_output=True, text=True)
    r = subprocess.run(["git", "-C", worktree, "diff", "--cached",
                        "--name-only"], capture_output=True, text=True)
    return [x for x in r.stdout.splitlines() if x.strip()]


def gate(worktree, tiles):
    if not os.path.exists(BASELINE):
        print("no frozen baseline — run --freeze first"); return 2
    st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    mode = st.get("mode", "")
    names = _diff_names(worktree)
    if not names:
        print("worktree has no changes"); return 2
    tampered = [n for n in names if any(k in n for k in LOCKED)]
    if tampered:
        print(f"GAMING GUARD: worktree touched LOCKED files {tampered} -> DISCARD")
        _log({"verdict": "DISCARD", "reason": "locked-file-edit", "files": tampered,
              "mode": mode})
        return 1
    # independent gate: run the LOCKED scorer on the WORKTREE engine vs baseline
    r = subprocess.run(
        [VENV, os.path.join("eval", "tilecmp_gate.py"),
         "--baseline", BASELINE, "--tiles", str(tiles), "--target-mode", mode],
        cwd=worktree, capture_output=True, text=True)
    print(r.stdout.strip())
    passed = r.returncode == 0
    if passed:
        patch = subprocess.run(["git", "-C", worktree, "diff", "--cached",
                                "--", "engines/"],
                               capture_output=True, text=True).stdout
        pf = os.path.join(HERE, ".loop_patch.diff")
        open(pf, "w").write(patch)
        subprocess.run(["git", "apply", pf], cwd=ROOT, check=True)
        subprocess.run(["git", "add"] + [n for n in names if n.startswith("engines/")],
                       cwd=ROOT, check=True)
        msg = (f"engine: auto-loop KEEP (target {mode})\n\nCandidate from worktree "
               f"{os.path.basename(worktree)} passed the tilecmp gate. Files: "
               f"{', '.join(names)}.")
        subprocess.run(["git", "commit", "-q", "-m", msg], cwd=ROOT, check=True)
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True).stdout.strip()
        print(f"  KEEP -> merged + committed {sha}; re-freezing baseline…")
        freeze(tiles)
        _log({"verdict": "KEEP", "mode": mode, "files": names, "sha": sha})
    else:
        print("  REVERT -> worktree discarded (not merged)")
        _log({"verdict": "DISCARD", "reason": "gate-fail", "mode": mode, "files": names})
    return 0 if passed else 1


def _log(rec):
    rec["t"] = int(time.time())
    with open(LEDGER, "a") as f:
        f.write(json.dumps(rec) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--brief", action="store_true")
    ap.add_argument("--gate", metavar="WORKTREE", default=None)
    ap.add_argument("--tiles", type=int, default=40)
    ap.add_argument("--exclude", default="FITTER",
                    help="comma-list of modes to skip when picking a target")
    a = ap.parse_args()
    exclude = set(x for x in a.exclude.split(",") if x)
    if a.freeze:
        freeze(a.tiles)
    elif a.brief:
        brief(a.tiles, exclude)
    elif a.gate:
        sys.exit(gate(a.gate, a.tiles))
    else:
        ap.error("give --freeze, --brief, or --gate <worktree>")


if __name__ == "__main__":
    main()
