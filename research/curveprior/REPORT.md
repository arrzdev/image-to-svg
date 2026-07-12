# Curve Idealizer v0 — train + honest holdout evaluation

**Verdict: NOT worth integrating.** On held-out images the learned model is
*worse than doing nothing* (clean-subset m1 +14% vs identity, m2 +26%), and
worse than oracle geometric smoothing. The failure is not the trainer (a
memorization control passes); it is the supervision: given only our curve's
shape, Recraft's redraw is mostly irreducible per-curve noise, so the learned
conditional mean degenerates into shrinkage that actively damages the cleanest
matches. Details and receipts below.

Everything here: `research/curveprior/` — `train_idealizer.py` (self-contained),
`model_v0.pt`, `results_v0.json` (headline), `results_v0b.json` (hyperparam
variant), `overlays_v0.png`, `training_curve_v0.png`, `train_full.log`.

Reproduce: `.venv/bin/python research/curveprior/train_idealizer.py --epochs 300 --tag v0`

---

## 1. Dataset actually used — and the alignment surgery it needed

`pairs.jsonl`: 1,311 pairs, 11 stems, 77.9% closed, our-curve RMS radius
p10/p50/p90 = 8.8 / 38.6 / 116.6 px.

| stem | pairs | | stem | pairs |
|---|---|---|---|---|
| crystals | 399 | | shield (HOLD) | 70 |
| chopchop | 358 | | elephant (HOLD) | 65 |
| mountain | 112 | | app-asset | 59 |
| fox (HOLD) | 108 | | pizza-box | 47 |
| rabbit | 88 | | logo-geometric + monster | 5 |

**Finding during setup: the stored `their_pts` are NOT canonicalized.** The
task brief said orientation/roll were already applied; empirically they are
not, and worse, the pairs are not positionally registered either — the mining
gate (turning distance) is translation/scale-blind, so small repeated shapes
(crystals, spots) matched *other instances* elsewhere on the canvas.
Correlation of raw per-point L2 with centroid offset = **0.995**.

Fix applied in `load_pairs()` (documented in the code):

- theirs re-centered on **its own** centroid (position is not something an
  idealizer should learn), scaled/rotated by **our** transform;
- orientation (2) x cyclic roll (64) nuisance resolved by min point-L2 at N=64;
- residual `align_l2` (normalized units) kept per pair: p50 0.364, p90 1.08,
  p99 3.31. Median residual in px terms ~9.5 px on holdout.

Training pairs gated at `align_l2 <= 1.0` (drops 121/1,068 train-stem pairs =
shape-mismatched instances). Holdout is reported both **ungated (all 243)**
and on the **same-gated clean subset (213)** — the gate uses only supervision
quality, identically for baselines and model.

The number to keep in mind: even "clean" matched pairs sit a median ~0.2-0.36
normalized L2 apart. The supervision delta is dominated by Recraft
*redrawing*, not by removable tracing noise — an order of magnitude above the
1-3 px idealization deltas we actually want to learn.

## 2. Task setup (as specified, v0-simple)

- Resample both polylines to **N=64**, arc-length uniform; closed curves keep
  index-0 correspondence, open curves keep endpoints.
- Per-pair normalization: our centroid, our RMS radius, PCA rotation
  canonicalization (sign fixed by x-skewness); same transform on theirs.
  (Note: m1 is rotation-invariant; the rotation only gives the net a stable
  canonical frame.)
- **Model**: 142,466-param dilated 1D CNN over the 64-point sequence — kernel
  5, channels 96, dilations [1,2,4,8,1] (receptive field covers the whole
  curve), GELU. Per-sample padding: circular for closed, replicate for open.
  Input features computed from the (augmented) polyline: xy, unit tangent,
  signed turn angle, closed flag. Output: per-point offsets added to the
  input (residual).
- **Loss**: point MSE + 1.0 x MSE on second differences (curvature-profile
  match). **Augmentation**: random cyclic roll (closed, applied to both),
  mirror flip (both), rotation +-15 deg (both), input-only jitter sigma=0.015
  (~0.6 px at median scale). Rotation canonicalization was kept and
  augmentation layered on top with small angles: the canonical frame carries
  real information (dominant-axis alignment) and the +-15 deg jitter covers
  PCA-axis instability without discarding it.
- **Split (image-holdout, mandatory)**: fox + shield + elephant fully held out
  (243 pairs — no influence on training or model selection). Remaining 8
  stems, gated: 947 pairs -> 805 train / 142 val (random 15%, seed 0). Early
  stop on val mean point-L2, patience 40.
- Trained on Apple MPS (torch 2.8.0), 57 s to early stop (ep 49, best ep 8).

## 3. Holdout results — the go/no-go table

Metrics in the normalized frame (our-RMS-radius units): **m1** = mean
point-L2 to theirs; **m2** = aligned turning distance (ported from
`research/design/pathflow.py`, applied to the 64-pt polylines, closed curves
closed before measuring). B1 = box-smooth + leash sweep mirroring
`models/edge-10/src/arcfit.py::smooth_closed` (windows 3/5/9/13/17, leash
1.25/2.0/3.0 px in original scale), **best window picked per metric on the
holdout itself** (oracle, generous on purpose).

### All holdout pairs (n=243)

| candidate | m1 | m2 | ~px |
|---|---|---|---|
| B0 identity | **0.4225** | 0.5979 | 26.2 |
| B1 oracle, best-m1 (w3, leash 3.0) | **0.4224** | 0.5849 | 26.2 |
| B1 oracle, best-m2 (w5, leash 2.0) | 0.4227 | **0.5783** | — |
| **model v0** | 0.4504 | 0.7108 | 29.3 |

### Clean-supervision subset (align_l2 <= 1.0, n=213)

| candidate | m1 | m2 | ~px |
|---|---|---|---|
| B0 identity | **0.2471** | 0.4738 | 17.5 |
| B1 oracle, best-m1 (w3, leash 3.0) | **0.2469** | 0.4617 | 17.5 |
| B1 oracle, best-m2 (w5, leash 2.0) | 0.2473 | **0.4550** | — |
| **model v0** | 0.2824 | 0.5968 | 21.5 |

The model **loses to B0 and B1 on both metrics, on both subsets.** Note also
how little headroom B1 finds: oracle smoothing improves m1 by 0.08% and m2 by
~4%. At this pairing's noise level there is nearly nothing for *any*
point-wise mapping to gain.

### Per-holdout-image breakdown (clean subset, m1 / m2)

| image | n | B0 | B1 best-m1 | model v0 |
|---|---|---|---|---|
| elephant | 63 | **0.113** / **0.226** | 0.115 / 0.233 | 0.190 / 0.424 |
| fox | 91 | 0.336 / 0.672 | **0.335** / **0.652** | 0.347 / 0.844 |
| shield | 59 | 0.253 / 0.433 | **0.252** / 0.412 | 0.280 / **0.401** |

The pattern is diagnostic: the model does the most damage on **elephant** —
the image whose matches were already the cleanest (+68% m1). A learned
shrinkage prior hurts most exactly where our curves were already right.
(Shield m2 is the model's single bright spot, -7% turning distance — far too
little to matter.)

## 4. Why it fails — training behavior, controls, ablation

- **Training curve is flat** (`training_curve_v0.png`): best val 0.3660 at
  epoch 8; identity on the same val slice scores 0.3733. In-distribution, the
  model learns a ~2% relative improvement — and even that fails to transfer.
- **Memorization control (pipeline sanity)**: augmentation off, 256 training
  pairs, 400 full-batch steps -> point-L2 0.414 -> 0.27 and still falling.
  Gradients, capacity, and the data path are fine; the model *can* fit the
  mapping when allowed to memorize. The problem is that what it memorizes
  does not generalize — there is no shared systematic structure to extract.
- **Hyperparameter variant v0b** (`results_v0b.json`: lambda 0.25, lr 5e-4,
  jitter 0.005, rotation +-5 deg): best val 0.3659, holdout-clean m1 0.2876 /
  m2 0.5341. Same verdict; the result is not an artifact of one setting.
- **Mechanism** (see `overlays_v0.png`, grey=ours, green=Recraft, red=model):
  - *fail panels*: on smooth open curves where ours already lies on Recraft,
    the model drags the curve inward/away — classic regression-to-the-mean
    shrinkage (up to -44 px on a shield fragment).
  - *tie panels*: model stays near the input; harmless, useless.
  - *"win" panels*: the L2 "wins" are pairs where Recraft genuinely redrew a
    different shape (fox tile[2,3]: a different lobe entirely); the model
    hedges toward the middle, which reduces L2 without producing anything
    cleaner. Even the wins are not idealization.

  In other words: the model learned exactly what the data contains — "Recraft
  is somewhere vaguely near your curve but you can't know where" — whose
  point-estimate answer is shrinkage. That is a property of the supervision,
  not of the architecture.

## 5. Runtime (non-issue)

| mode | ms/curve |
|---|---|
| MPS, batch 512 | **0.014** (500 curves ~= 7 ms) |
| MPS, single curve | 3.86 (dispatch overhead dominates) |
| CPU, single curve | 0.96 |

Batched inference for a full image (~500 curves) costs ~7 ms on MPS or
~0.5 s naively one-at-a-time on CPU. Speed would never have been the blocker.

## 6. Honest verdict

**Does learning beat geometry on unseen images? No — it loses to both the
identity and the oracle geometric baseline on both metrics.** And the deeper
lesson is that the *task formulation* is what failed: `pairs.jsonl`
supervision deltas are dominated by Recraft's unpredictable per-curve redraw
(median aligned residual ~0.2-0.36 normalized), which a shape-only regressor
cannot predict; the best it can do is shrink. Meanwhile the entire measurable
headroom of point-wise smoothing on these pairs (B1 oracle) is under 4% even
on the metric it is best at. Integration into the engine: **no**. quant-13
should keep its geometric smoothing (edge-10 `smooth_closed` semantics
already capture what B1 shows is available).

What could change the answer (out of v0's scope, recorded for the ledger):

1. **Synthetic corruption pairs** — take clean vector curves (Recraft outputs,
   font glyphs, primitives), corrupt them with *our pipeline's* characteristic
   noise (staircase, boundary wander, over-fragmented arcs), and learn the
   inverse map. Supervision then contains exactly the removable noise, with
   pixel-perfect correspondence — the thing this dataset lacks.
2. **Image-conditioned idealization** — let the model see the raster under the
   curve, not just the polyline; "where should this edge be" stops being
   unknowable. Substantially bigger build.
3. More strict pairs (only 96/1,311 here) would not fix (1)-(2)'s core issue
   and is too small to train on.
