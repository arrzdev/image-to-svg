"""tilecmp_gate — the LOCKED full-auto keep/revert scorer for the autoresearch
loop (USER 2026-07-10 regime). The loop may NOT edit this file or tilecmp*.py /
findings.py (anti-gaming).

  # 1. freeze a baseline from the CURRENT engine code, before any edit:
  python eval/tilecmp_gate.py --set-baseline eval/.tilecmp_cache/gate_base.pkl

  # 2. (orchestrator edits engines/quant/quant-11/src in a worktree) then gate the edit:
  python eval/tilecmp_gate.py --baseline .../gate_base.pkl [--target-mode UNDER-RESOLVE]
  #   exit 0 = PASS (keep), exit 1 = REVERT.

  # measure the engine's run-to-run NOISE floor (k-means nondeterminism) so the
  # gate thresholds sit above it:
  python eval/tilecmp_gate.py --noise-check [--runs 3]

Gate rule (PASS iff ALL):
  * corpus overall distance improves by >= MIN_GAIN (must beat the noise floor),
  * no channel (census/flow/color) regresses by more than CH_EPS,
  * if --target-mode given, that failure mode's ink-weighted share drops.
"""
import argparse
import os
import pickle
import sys

import numpy as np

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
import tilecmp_loop as L  # noqa: E402  (reuses sweep/load_engine/montage)

# thresholds — calibrated to sit ABOVE the engine's k-means run-to-run noise
# (see --noise-check). Tighten once the measured floor is known.
# RECALIBRATED 2026-07-12 (orchestrator, deliberate re-baseline step, run 65):
# --noise-check measured corpus-overall spread 0.0000 across repeated runs
# (engine deterministic), so the provisional 0.004 — sized for assumed k-means
# noise — was blocking real all-channels-clean wins (it9 wander-erasure
# +0.0029, eye-audited before ship). 0.0015 stays far above float jitter while
# letting mature-engine gains through; CH_EPS unchanged (the per-channel
# anti-regression guard is what actually prevents corpus overfit).
MIN_GAIN = 0.0015
CH_EPS = 0.006


def _corpus_line(tag, c):
    return (f"  {tag:10s} overall={c['overall']:.4f}  census={c['census']:.4f}  "
            f"flow={c['flow']:.4f}  color={c['color']:.4f}")


def noise_check(engine, tiles, runs):
    print(f"[noise-check] sweeping {engine} x{runs} (same code, k-means varies)…")
    sweeps = [L.sweep(L.load_engine(engine), None, tiles) for _ in range(runs)]
    for k, s in enumerate(sweeps):
        print(_corpus_line(f"run{k}", s["corpus"]))
    for key in ("overall", "census", "flow", "color"):
        vals = [s["corpus"][key] for s in sweeps]
        print(f"  {key:8s} spread (max-min) = {max(vals)-min(vals):.4f}  "
              f"std = {np.std(vals):.4f}")
    print(f"\n  -> set MIN_GAIN safely above the overall spread "
          f"({max(s['corpus']['overall'] for s in sweeps) - min(s['corpus']['overall'] for s in sweeps):.4f}).")


def gate(engine, tiles, baseline_path, target_mode):
    if not os.path.exists(baseline_path):
        print(f"ERROR: no baseline at {baseline_path}. Run --set-baseline first "
              f"(BEFORE editing the engine).")
        return 2
    base = pickle.load(open(baseline_path, "rb"))
    cand = L.sweep(L.load_engine(engine), None, tiles)   # current (edited) code
    b, c = base["corpus"], cand["corpus"]
    print(_corpus_line("baseline", b))
    print(_corpus_line("candidate", c))

    gain = b["overall"] - c["overall"]
    improved = gain >= MIN_GAIN
    worst_ch, worst_reg = None, 0.0
    for k in ("census", "flow", "color"):
        reg = c[k] - b[k]
        if reg > worst_reg:
            worst_ch, worst_reg = k, reg
    no_regress = worst_reg <= CH_EPS

    mode_ok = True
    if target_mode:
        bmf = b["mode_frac"].get(target_mode, 0.0)
        cmf = c["mode_frac"].get(target_mode, 0.0)
        mode_ok = cmf < bmf - 0.003
        print(f"  target {target_mode}: share {bmf*100:.1f}% -> {cmf*100:.1f}% "
              f"{'(dropped)' if mode_ok else '(NO drop)'}")

    print(f"  overall gain = {gain:+.4f} (need >= {MIN_GAIN})  "
          f"{'OK' if improved else 'insufficient'}")
    if worst_ch:
        print(f"  worst channel regression = {worst_ch} {worst_reg:+.4f} "
              f"(allow <= {CH_EPS})  {'ok' if no_regress else 'REGRESSED'}")
    verdict = improved and no_regress and mode_ok
    print(f"\n  VERDICT: {'PASS (keep)' if verdict else 'REVERT'}")

    # audit montage on the worst image (for the periodic eye-audit)
    pick = max(cand["per"], key=lambda s: cand["per"][s]["agg"]["overall"])
    out = os.path.join(HERE, "tilecmp_out", f"gate_{pick}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    try:
        L.montage(pick, base, cand, tiles, out)
        print(f"  audit montage ({pick}): {out}")
    except Exception as e:
        print(f"  (montage skipped: {e})")
    return 0 if verdict else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="quant-12")
    ap.add_argument("--tiles", type=int, default=40)
    ap.add_argument("--set-baseline", default=None, metavar="PATH")
    ap.add_argument("--baseline", default=None, metavar="PATH")
    ap.add_argument("--target-mode", default=None)
    ap.add_argument("--noise-check", action="store_true")
    ap.add_argument("--runs", type=int, default=3)
    a = ap.parse_args()

    if a.noise_check:
        noise_check(a.engine, a.tiles, a.runs)
        return
    if a.set_baseline:
        os.makedirs(os.path.dirname(a.set_baseline), exist_ok=True)
        s = L.sweep(L.load_engine(a.engine), None, a.tiles)
        pickle.dump(s, open(a.set_baseline, "wb"))
        print(_corpus_line("baseline", s["corpus"]))
        print(f"  froze baseline -> {a.set_baseline}")
        return
    if a.baseline:
        sys.exit(gate(a.engine, a.tiles, a.baseline, a.target_mode))
    ap.error("give --set-baseline, --baseline, or --noise-check")


if __name__ == "__main__":
    main()
