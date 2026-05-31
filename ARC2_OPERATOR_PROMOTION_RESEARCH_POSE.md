# Selection Bias in Operator-Library Program Synthesis: a Frozen-Holdout Audit of "Finite-Miss Promotion" for ARC-AGI-2

*Research pose + empirical pilot. arc_agi/workspace, 2026-05-30. Status: draft for internal use; numbers reproducible from the harness below.*

---

## Abstract

We study a common but under-examined practice in symbolic ARC-AGI solvers: incrementally
adding hand-authored, task-specific transformation operators ("finite-miss promotions"),
each admitted by an *exact-train + leave-one-out (LOO)* gate and selected against a held-out
"hidden mode" split. We ask whether this promotion protocol yields a calibrated estimator of
hidden-set generalization or a form of corpus overfitting dressed as principled gating. Using
the solver's own `OperatorEvidence` telemetry and a deterministic frozen public-eval split, we
run a 2×2 audit (design vs. frozen × normal vs. strict admission) and decompose every solve by
operator provenance. Three findings: **(1)** under normal admission the design-vs-frozen gap is
**0.0 pp** (0.70 == 0.70), i.e. the *automated* engine is IID-calibrated and the headline 0.70 is
*not* differentially selection-inflated; **(2)** ~78–79% of all solves on both splits come from the
general candidate-factory + ranker + test-time-augmentation path, not the promoted operators —
the engine is load-bearing and the finite-miss layer is a thin margin; **(3)** the finite-miss layer
exhibits *zero cross-task reuse* (strictly one-operator-per-task) and its LOO gate is provably
non-informative, so it is **memorization, not abstraction**, and a post-hoc data split cannot
validate it. We propose a false-discovery-rate-controlled promotion protocol — replacing the
vacuous LOO-on-fixed-operators gate with a cross-task firing criterion measured on a *design*
split and audited *once* on a *generic holdout*. We found and fixed a strict-gate bug (it discarded
*untestable* operators, not only failing ones, a −13.8 pp design artifact); after the fix both
admission modes are IID-calibrated (+1.3 pp). An H1 audit shows the gate is **non-discriminating** —
conditional on train-exactness every evidence signature predicts hidden success at 100% (45/45) — and
the synthetic-invariance hard-gate is **net-harmful** (operators it quarantines still hit 16/16), so
it belongs as a soft ranking feature, not a filter.

---

## 1. The practice under study

`arc2_candidate_solver.py` admits operators through `admit_operator_factory` (line ~653) /
`admit_fixed_operator` (line ~7588) under an `AdmissionPolicy`:

```
require_exact_train = True          # operator must reproduce every train pair exactly
require_loo_for_certified = True    # leave-one-out re-derivation must hold
require_synthetic_for_certified=True
min_structural_confidence = 0.70
```

A **finite-miss promotion** is a hand-written transform added to `fixed_specs` (lines ~7426–7434)
to solve a specific near-miss public task — e.g. `mask_scale:fill_expanded_holes_with_objects`
for `898e7135`, `binary_outline:object_holes_with_roles` for `aa4ec2a5`,
`cross_spiral:expand_plus_to_rectangular_spiral` for `da515329`.

### 1.1 The crux: LOO is vacuous for fixed operators

`leave_one_out_validates(pairs, factory)` (line 590) refits `factory(subset)` on each
leave-one-out subset and checks the held pair. For `fixed_specs` the call is
`leave_one_out_validates(pairs, lambda _subset, transform=transform: transform)` (line 7441):
the factory **ignores `_subset`** and returns the same fixed transform every fold, so LOO
**collapses to `train_exact`** and contributes *zero* out-of-sample information. LOO only carries
generalization evidence when the factory genuinely *re-derives parameters* from the held subset
(e.g. `learn_master_pattern_expansion` ~1451; row-marker factories ~862). The solver now records
this distinction explicitly via `OperatorEvidence.loo_informative` and `admission_type ∈
{fixed_transform, learned_factory}`.

**Consequence:** for a hand-written operator the only real out-of-distribution signal is the
held-out "hidden mode" selection — and that signal is reused as operators accumulate, which is the
classic train/test contamination via model selection (Cawley & Talbot 2010).

---

## 2. Research question and hypotheses

> **Is exact-train + LOO a *calibrated* admission gate for hand-mined ARC operators — or does a
> growing finite-miss library inflate its hidden-set score through selection bias, and what
> promotion discipline provably prevents that?**

- **H1 (calibration).** Among certified operators, realized hidden-hit rate equals the rate implied
  by their gate evidence. *Measured by:* `public_shadow_hits/total` reliability.
- **H2 (gate-information decomposition).** `jackknife_stable` + `synthetic_self_consistency` add
  predictive value beyond `train_exact`, whereas LOO-on-fixed-operators does not
  (`loo_informative=False` ⇒ coefficient ≈ 0). *Measured by:* provenance of solves by `admission_type`.
- **H3 (look-elsewhere / freeze-the-holdout).** The public-vs-hidden gap reflects selection
  inflation; a single frozen-holdout evaluation reveals the honest rate. *Measured by:* the 2×2 below.

---

## 3. Instrument

- **Telemetry (already emitted):** `OperatorEvidence{train_exact, leave_one_out, jackknife_stable,
  structural_confidence, synthetic_self_consistency, public_shadow_hits/total/diff_counts,
  admission_type, evidence_label, loo_informative, synthetic_checks, promotion_blockers}`.
- **Frozen split:** `run_pseudo_private_eval.py --split {design|calibration} --split-seed
  arc2-frozen-calibration-v1 --calibration-count 40`. The split is deterministic
  (sha256(seed:task_id) rank), giving a clean 80/40 partition over the 120-task public eval. The
  harness renames task ids, hides test outputs, and scrubs `solve_<8hex>` direct dispatchers, so
  task-id memorization is disabled and the per-task pipeline sees only that task's train pairs.
- **Modes:** normal vs. `--strict-admission` (quarantine fixed operators failing synthetic
  invariance checks).

---

## 4. Results (pilot, 2026-05-30)

### 4.1 The 2×2 (task SCORE; design=80, calibration=40, frozen seed `arc2-frozen-calibration-v1`)

| mode | design | calibration | design − calibration |
|---|---|---|---|
| **non-strict** | **0.7000** (56/80) | **0.7000** (28/40) | **+0.0 pp** |
| strict (buggy gate) | 0.4750 (38/80) | 0.5750 (23/40) | −10.0 pp |
| **strict (untestable≠failed fix)** | **0.6125** (49/80) | **0.6000** (24/40) | **+1.3 pp** |

Reference: Chollet et al. (ARC-AGI-2) — IID-calibrated sets show <1 pp gap for a non-overfit
system; >10 pp is the overfit signature. **Both calibrated admission modes (non-strict 0.0 pp,
fixed-strict +1.3 pp) sit inside the IID band**; the buggy gate's −10 pp inversion was the
untestable-quarantine artifact, now resolved. Fixing the gate recovered **+13.8 pp** on design and
**+2.5 pp** on calibration. The remaining strict cost (≈ −9 pp vs non-strict, symmetric across
splits) is the legitimate quarantine of synthetic-*failing* operators — but see §4.3, it is not
earning that cost.

### 4.2 Provenance of every solve — precise (per solved pair; ranker is the *selector*, not a generator)

Winning sources are composite pipeline paths; parsed into TTA-wrapper × base-generator.

| split (strict-fixed) | GENERAL (dsl / generic / sym) | OPERATOR lib (learned / fixed) | TTA-wrapped |
|---|---|---|---|
| **calibration (frozen)** | **78.8%** (24 / 2 / 0) | 21.2% (3 / 4) | 66.7% |
| design | 60.6% (37 / 3 / 0) | 39.4% (1 / 25) | 77.3% |

→ On the frozen split, **~79% of solves are the general engine, DSL-dominated (24/33), and TTA wraps
two-thirds of all solves** — TTA is the single biggest lever. The operator library is ~21% of frozen
solves. (On design the operator share is higher because that is where the hand-authored targets live
— consistent with memorization.)

### 4.3 H1 — the gate is a *non-discriminating* predictor (and the synthetic check is net-harmful)

Hidden-hit rate of gate-passing (train-exact) operators, by evidence signature, design (predicted)
vs frozen (realized); `reports/h1_by_evidence.png`, `reports/h1_design_vs_frozen.png`:

| signature | design | frozen | pooled [Wilson 95%] |
|---|---|---|---|
| fixed / synthetic **failed** | 8/8 | 8/8 | **1.00** [0.81, 1.00] |
| fixed / synthetic passed | 8/8 | 3/3 | 1.00 [0.74, 1.00] |
| fixed / synthetic unavailable | 17/17 | 1/1 | 1.00 [0.82, 1.00] |
| learned / loo+ syn+ | 1/1 | 3/3 | 1.00 [0.51, 1.00] |

Weighted calibration error (design→frozen): **0.000**. The table above is filtered to *train-exact*
operators; within that set every signature hits ~100%. The **negative control** (independently run by
the Codex lane, `ARC2_OPERATOR_RELIABILITY_FIXED_REPORT.md`, a weighted logistic model, log-loss
0.0517) supplies the missing classes and sharpens the conclusion:

| class | hits / total | hit rate |
|---|---|---|
| `rejected` (not train-exact) | 0 / 9 | **0.00** |
| `learned_factory` (incl. non-exact) | 4 / 13 | **0.31** |
| `fixed_transform`, train-exact | 45 / 45 | 1.00 |
| synthetic `unavailable` | 22 / 31 | 0.71 |

**`train_exact` is the load-bearing gate signal** (logistic coef +1.18; `tier_certified` +0.96),
not LOO or synthetic invariance — `loo_informative=True` even carries a *negative* coefficient
(−0.76), i.e. the learned-factory operators are the *less* reliable class (0.31), the opposite of the
intuition that "more validation = safer." On top of `train_exact`, the synthetic check adds nothing:
`failed` and `passed` both hit 1.00, so the strict synthetic *hard-gate* is still net-harmful (it
removes correct operators and earns no precision) and belongs as a soft ranking feature.

### 4.4 Two forced findings

- **Fixed layer = pure memorization.** The design firing registry shows **0 of 28** train-exact
  `fixed_transform` operators fire on ≥2 distinct design tasks — strictly one-operator-per-task, zero
  cross-task reuse. With `loo_informative=False`, the finite-miss layer has *no* out-of-sample
  evidence beyond `train_exact`, and the `--require-general-operators` gate would (correctly)
  quarantine all of them.
- **Strict gate fixed.** `synthetic_checks_status` now returns `unavailable` (vs `failed`) when no
  invariance test applies; `--strict-admission` quarantines only genuine failures. The three new
  finite-miss ops are no longer collateral-quarantined.

### 4.5 Interpretation

1. **The 0.70 is IID-calibrated for the engine** under both admission modes (0.0 pp non-strict,
   +1.3 pp fixed-strict) — *not* selection-inflated in the differential sense the split can measure.
2. **Caveat (the point of framing B):** a design-vs-frozen split detects only *differential*
   overfitting. It **cannot** detect human-author memorization (the author saw all 120 tasks; targets
   split ~evenly and lift both halves). **The frozen split validates the engine, not the promotions.**
3. **The leverage is TTA + DSL, not finite-miss promotions.** ~79% of honest frozen transfer is the
   general engine (TTA wraps two-thirds); the operator library is a ~21% memorized margin whose
   semi-private value is unknown until those targets recur. The gate machinery (LOO/synthetic) is
   non-discriminating and the synthetic hard-gate is net-harmful.

---

## 5. Proposed protocol (the contribution)

Replace the vacuous LOO-on-fixed gate with a **false-discovery-rate-controlled promotion protocol**:

1. **Mine only on `design`.** Operators must be admitted using design-split evidence alone.
2. **Cross-task firing as the gate.** Promote a fixed operator to a *general* tier only if it is
   train-exact (and gate-clean) on **≥2 distinct design tasks** — a far stronger out-of-sample
   signal than single-task LOO. Single-task fixed ops are tagged `memorized`, kept for points but
   never counted as evidence of generalization.
3. **Generic holdout, spent once.** Evaluate the *final* library on the frozen split exactly once;
   the frozen set answers only "did operator *X* hit?" (yes/no), per the Generic Holdout
   (Nakkiran & Błasiok 2018) / Reusable Holdout (Dwork et al. 2015). This bounds the false-discovery
   rate of the promotion rule and resets the look-elsewhere debt.
4. **Strict admission (shipped):** `synthetic_checks_status` now distinguishes `failed` from
   `unavailable`; only `failed` quarantines. **But H1 (§4.3) shows even `failed` operators hit 16/16
   on hidden** — so the next step is to demote the synthetic check from a hard quarantine gate to a
   soft ranking feature, since it costs recall and earns no precision at this sample size.

---

## 6. Related work

- **ARC framing.** Chollet et al., *ARC-AGI-2* (arXiv:2505.11831) — IID calibration, ±10 pp overfit
  threshold. Vahdati et al., *The ARC of Progress: a Living Survey* (arXiv:2603.13372) — 2–3× drop
  AGI-1→2; "reasoning remains knowledge-bound; winners needed 100k+ synthetic examples for 24%."
- **Contrasting selection regimes.** Akyürek et al., *Surprising Effectiveness of Test-Time Training*
  (arXiv:2411.07279); Ouellette, *OOD Generalization in ARC-AGI: exec-guided synthesis vs TTFT*
  (arXiv:2507.15877, finds TTFT mostly elicits in-distribution knowledge); Pourcel et al., *SOAR*
  (arXiv:2507.14172).
- **Operator-library / inductive synthesis.** Ellis et al., *DreamCoder* (arXiv:2006.08381, treats
  train-consistency as ground truth — the gap we fill); Wei et al., *CodeARC* (arXiv:2503.23145,
  hidden-target + differential-testing oracle); Rocha et al., *ILP for ARC* (arXiv:2405.06399); Xu,
  Khalil, Sanner, *ARGA* (arXiv:2210.09880).
- **Statistical core.** Cawley & Talbot, *On Over-fitting in Model Selection & Subsequent Selection
  Bias* (JMLR 2010 — low *variance* of the selection criterion matters as much as bias, indicting a
  high-variance n=2–4 LOO gate); Dwork, Feldman, Hardt, Pitassi, Reingold, Roth, *Reusable Holdout*
  (arXiv:1506.02629); Nakkiran & Błasiok, *The Generic Holdout* (arXiv:1809.05596 — find-a-true-
  hypothesis setting, exactly operator promotion).

**Novelty.** DreamCoder-lineage work *grows* operator libraries but treats train-consistency as
truth; adaptive-data-analysis work *quantifies* holdout-reuse damage but has never been applied to
program-synthesis operator promotion. The finite-miss pipeline — with `OperatorEvidence` gate vectors
and `public_shadow` hit counts already instrumented — is the first place these two literatures join
and are measured.

---

## 7. Threats to validity

- **Pseudo-private ≠ semi-private.** The frozen split is drawn from the public eval the author has
  seen; it bounds *engine* drift, not author memorization (Section 4.4).
- **Small n.** 40/80-task splits ⇒ ±~5–8 pp sampling noise; the strict −10 pp design<calibration
  inversion is within noise and dominated by the untestable-quarantine artifact (Section 4.3) — do
  not read it as reverse-overfitting.
- **Ranker entanglement.** "general pipeline" provenance lumps narrow-TTA, DSL, and ranker; a finer
  attribution would separate them.

---

## 8. Next steps

- [x] Implement the cross-task firing gate (§5.2): `OperatorEvidence.cross_task_firing` /
  `generalization_tier`, env `ARC_OPERATOR_FIRING_REGISTRY`, eval `--write-firing-registry` /
  `--firing-registry` / `--require-general-operators`. Measured: 0/28 fire on ≥2 tasks.
- [x] Fix `synthetic_checks_status` untestable≠failed (§5.4); re-ran the 2×2 → +1.3 pp gap.
- [x] H1 reliability diagram (`build_h1_reliability.py`) → gate is non-discriminating (45/45).
- [x] Precise TTA/DSL/generic/operator provenance (`analyze_solve_provenance.py`) → 79% engine, TTA 67%.
- [ ] Demote the synthetic-invariance check to a soft ranking feature (H1 shows it is net-harmful).
- [ ] Register the frozen split as a *write-once* generic holdout; never re-select against it.
- [ ] Reinvest the finding: the leverage is TTA + DSL — search there, not more finite-miss ops.

---

### Reproduce

```bash
cd workspace
python3 run_pseudo_private_eval.py --split design      --strict-admission --diagnostics tmp/pp_design_strict.json
python3 run_pseudo_private_eval.py --split design                          --diagnostics tmp/pp_design_nostrict.json --no-candidate-report
python3 run_pseudo_private_eval.py --split calibration --strict-admission --diagnostics tmp/pseudo_private_calibration_strict_admission.json
python3 run_pseudo_private_eval.py --split calibration                     --diagnostics tmp/pp_cal_nostrict.json --no-candidate-report
# NOTE: use bare python3 (homebrew, numpy 2.4.4). Do NOT `source ../venv/bin/activate` — that venv lacks numpy.
```
