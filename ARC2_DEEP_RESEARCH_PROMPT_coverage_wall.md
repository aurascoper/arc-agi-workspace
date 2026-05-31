# ARC-AGI-2 Deep Research Prompt — Is the coverage wall search/repair-limited or representation-limited?

*Companion to Codex's `ARC2_NEXT_RESEARCH_PROMPT.md` (an implementation queue). This file poses the
research-level question one level up: it tells you **whether** that queue can work before you build it.*

*Synthesized 2026-05-30 from two independent lanes (Claude solver/eval + Codex reliability/provenance)
that cross-validated every number below. See `ARC2_OPERATOR_PROMOTION_RESEARCH_POSE.md`,
`ARC2_OPERATOR_RELIABILITY_FIXED_REPORT.md`, `ARC2_AGENT_COORDINATION_STATUS.md`.*

---

## What is now established (do not re-litigate)

1. **The engine is IID-calibrated.** Non-strict frozen split: design 0.70 == calibration 0.70 (0.0 pp
   gap; corrected-strict +1.3 pp). The 0.70 is a fair estimate of the *engine's* hidden transfer.
2. **The engine, not the operator library, is load-bearing.** ~79% of frozen solves are the general
   pipeline (DSL under narrow-TTA; TTA wraps ~67%). The finite-miss operator library is a ~21%
   *memorized* margin (0/28 fixed operators fire on ≥2 design tasks).
3. **Reliability gate:** `train_exact` is the load-bearing predictor (logistic +1.18; rejected 0/9,
   learned 4/13, fixed-train-exact 45/45). LOO/synthetic add ~nothing on top; the synthetic hard-gate
   is net-harmful.
4. **The bottleneck is coverage/shape, not ranking.** Across 80+40 tasks only **1** exact-in-top-k
   candidate was mis-ranked; **41 design + 26 calibration** misses are coverage/shape failures.
5. **The "last-mile residual" signature.** For many misses the best top-k candidate is the
   structurally correct family within a small pixel residual, yet no exact program is enumerated:
   `dd6b8c4b` 23→7 (`highlight_kth_longest_bar`), `28a6681f` 12→6 (`frame_minority_cells`),
   `b6f77b65` 14→8 (`connect_cells_via_key_sequence`), `3dc255db` 17→16, `88bcf3b4` 27→14. A distinct
   sub-class is **wrong-shape** (`4c7dc4dd`: best-attempt None, top-k diff 20).

## The research question

> **Is the ARC-AGI-2 coverage wall *search/repair-limited* or *representation-limited*? Concretely:
> for what fraction of frozen near-misses can a hidden-safe operator — specified on the design split
> only — recover an *exactly-train-correct* program by (a) deeper composition of existing DSL
> primitives and/or (b) a bounded, parameter-free residual-repair step, after (c) predicting the
> output shape?**

- **High flip-to-exact rate ⇒ search/repair-limited (A).** The right program is expressible; we are
  under-searching. Response: residual-repair + deeper composition + shape prediction. *Engineering.*
- **Low flip-to-exact rate ⇒ representation-limited (B).** The target is not expressible in the DSL;
  small residuals are coincidental. Response: grow the primitive set (DreamCoder-style abstraction)
  — this is Chollet's compositional-generalization wall, the documented 2–3× AGI-1→2 drop.

This converts "improve coverage" into a falsifiable measurement of **where the wall is**, so the
implementation queue is only built if (A) is true for a meaningful fraction.

## Measurement protocol (hidden-safe by construction)

1. **Shape-first.** For each miss, run an output-shape predictor (from train I/O shape relations).
   Partition misses into shape-correct vs wrong-shape; residual-repair is only defined on the former.
2. **Design-only synthesis attempt.** For each *design-split* near-miss, attempt an exact program via:
   (i) deeper/looped composition of existing primitives; (ii) a bounded local-repair operator
   conditioned ONLY on `(input, candidate_output, train_residual_structure)` — never on task id, public
   output, or the frozen split. Gate by `train_exact` + LOO (the load-bearing signals; ignore the
   net-harmful synthetic gate).
3. **Count, then evaluate once.** Report the design flip-to-exact rate per family. Evaluate each
   *pre-specified* family on the frozen split **exactly once** (Generic Holdout, Nakkiran–Błasiok
   2018). The frozen near-miss list may be COUNTED but never INSPECTED to design a fix.
4. **Cross-task promotion only.** A new operator ships as `general` only if train-exact on ≥2 distinct
   design tasks (`ARC_OPERATOR_FIRING_REGISTRY`); else it is tagged `memorized` (points, not evidence).

## Reason explicitly through

1. Of the 67 coverage/shape misses, how many are shape-correct-with-small-residual vs wrong-shape vs
   finite-far (>50 px, likely wrong primitive)? Which class dominates, and what does that imply about
   A vs B?
2. Does a single generic residual-repair operator (e.g. "snap candidate to nearest train-consistent
   local rewrite") close multiple design near-misses, or does each need a bespoke repair? Multi-task
   closure is the abstraction signal; bespoke closure is memorization in disguise.
3. For the wrong-shape class, is output shape a learnable function of train I/O shapes alone (tile,
   crop-to-object, transpose, fixed)? Shape-prediction accuracy on design upper-bounds repair value.
4. Where does execution-guided synthesis (Ouellette 2507.15877, which beats TTFT on ARC compositional
   generalization) fit vs the current beam+TTA — is the gap search policy or primitive set?
5. The one experiment that moves the posterior most while preserving the frozen budget.

## Deliverables

- A **Search-vs-Representation verdict** with the design flip-to-exact rate and a CI.
- A ranked, hidden-safe operator-family queue (only families that closed ≥2 *design* near-misses).
- For each family: a no-leak promotion rule and a **pre-registered stop condition** — halt a family
  after K design-derived variants fail to add design coverage, BEFORE spending any frozen budget.
- A statement of which near-misses are representation-limited (need new primitives) vs reachable.

## Literature anchors

- Execution-guided neural program synthesis vs TTFT — Ouellette, arXiv:2507.15877 (exec-guided wins on
  compositional generalization; argues for search/repair over weight adaptation).
- CEGIS — counterexample-guided inductive synthesis; the train residual is the counterexample.
- DreamCoder library growth — Ellis et al., arXiv:2006.08381 (recurring repairs → new primitives = the
  bridge from problem A to a principled answer to problem B).
- Generic / Reusable Holdout — Nakkiran & Błasiok arXiv:1809.05596; Dwork et al. arXiv:1506.02629
  (the write-once frozen-budget discipline this protocol enforces).
- ARC-AGI-2 compositional wall — Chollet et al. arXiv:2505.11831; Living Survey arXiv:2603.13372
  ("reasoning remains knowledge-bound"; 2–3× AGI-1→2 drop).

## Stop condition (anti-adaptive-overfitting)

The frozen calibration split is a write-once budget. No operator family may be tuned against it; the
named calibration near-misses (`28a6681f`, `b6f77b65`, `62593bfd`, `a47bf94d`, `8b7bacbf`, …) are
COUNT-ONLY. A family is abandoned on the design split before any frozen evaluation if K design variants
fail to add design coverage. One frozen evaluation per family, Bonferroni/Generic-Holdout-adjusted.
