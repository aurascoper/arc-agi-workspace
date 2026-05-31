# ARC-AGI-2 synthesis architecture plan — research-to-roadmap (Claude lane)

*Translates the deep-research report (per-task program synthesis) into a concrete plan grounded in THIS
solver's measured design-miss taxonomy. Standalone design doc; no live-solver edits. Every prototype reports
train-exact / LOO / synthetic-invariance / leakage-scan, design-only. 2026-05-30 ~22:35 CDT.*

## 1. Reconciliation: the report's framing vs our measurements

The report's verdict ("mixed wall, representation-limited center, search/repair-limited edge; execution-guided
symbolic synthesis beats TTFT; build an object-graph DSL + shape-first + routing/redraw + bounded CEGIS +
tiny learned proposer") **matches what this lane measured**, but we can replace its generic buckets with exact
task lists (`tmp/claude_relational_locus_all23.json`):

| report bucket | our measured locus | n | exact tasks |
|---|---|---:|---|
| wrong shape / decomposition | **decomposition** | 7 | 5dbc8537, edb79dae, 20a9e565, 2d0172a1, 6ffbe589, e87109e9, 89565ca0 |
| wrong role/anchor binding | **selector** + **parameter** | 2 | dd6b8c4b (fill-panel, marker-select), 3dc255db (apex-ray, host-direction) |
| needs generative primitive | **renderer** | 14 | 88bcf3b4, cb2d8a2c, 142ca369, 195c6913, 36a08778, 4a21e3da, 16b78196, 446ef5d2, 7b0280bc, abc82100, d8e07eb2, 271d71e2, faa9f03d, 35ab12c3 |

**Already done (so the report's "experiment 1" is partly closed):**
- *shape-first* prediction: validated, **16/23** correct (Codex shipped it as a ranking filter). The 7
  decomposition tasks need it to become a **generator**, not just a ranker.
- *pixel/relational cell repair*: **falsified 0/23** under LOO. → skip the report's "bounded pixel repair" hope
  for these misses; it does not flip them.
- *object keep/remove/recolor, symmetry/periodic, line-extension*: **falsified 0/23**. → skip.
- *routing primitive (apex-ray)*: **train-exact on 3dc255db** (first abstraction pinned) but design-test 0/1
  on frame-hosts. → the report's "experiment 2/3" is the live frontier; see §4.

**Net:** our empirical results let us *cut* the report's repair-first track and go straight to the
object-graph relation IR + role-binding sketches + generative renderers — which the report independently
recommends as the higher-value center.

## 2. CRITICAL correction to the report's admission protocol (our hard-won finding)

The report lists "leave-one-train-out exactness as a hard gate." **LOO is VACUOUS for parameter-free
operators.** Twice this project (finite-miss promotions; the apex-ray router) a fixed transform was
train-exact and "LOO-passed" yet did **not** generalize (apex-ray: design-test 0/1). Because refit-on-subset
returns the identical transform, LOO collapses to train-exactness and carries no out-of-sample signal.

**Corrected gate (use this, not the report's):**
1. Train-exact (hard).
2. **Informative-LOO**: the operator must genuinely RE-DERIVE its parameters from the held-out subset
   (`leave_one_out_validates` with a real factory, not `lambda _subset: fixed_transform`). Parameter-free
   transforms get `loo_informative=False` and may NOT be promoted on LOO alone.
3. For parameter-free / fixed operators: require **cross-task firing ≥2 distinct design tasks**
   (`ARC_OPERATOR_FIRING_REGISTRY`) as the generalization evidence instead of (vacuous) LOO. apex-ray fires
   on **1/23** → fails this gate, correctly.
4. Synthetic invariance: SOFT score, narrowed by family (Codex's refinement). Not a universal hard rejector.
5. One frozen calibration exposure per family; design-only tuning; full leakage scan.

This is the single most important delta from the report and is already half-implemented in
`arc2_candidate_solver.py` (`loo_informative`, `cross_task_firing`, `generalization_tier`).

## 3. Minimal object-graph DSL — prioritized by OUR miss coverage

Build only what our 23 misses actually need, ordered by coverage. (Report's primitive table, filtered.)

| primitive bundle | covers (our tasks) | priority |
|---|---|---|
| **output-shape generator** (crop-to-region, new-canvas, serialize-by-count, panelize) | 7 decomposition tasks | P0 — biggest single bucket; shape-pred already 16/23 |
| **marker→host→action relation graph** (contains/inside/bbox, host single-cell apex/pointing-dir, marker-by-role) | dd6b8c4b, 3dc255db (+ generalizes apex-ray to frame-hosts) | P0 — 2 "close" tasks; completes apex-ray |
| **routing/draw** (ray_until, orth_path, bracket, connect_anchors, draw_outline) | 88bcf3b4, abc82100, cb2d8a2c, 36a08778, 446ef5d2, 35ab12c3 (object-extension/routing) | P1 — 6 renderer tasks |
| **redraw/assemble** (extract, normalize, D4+scale, stamp, pack) | 4a21e3da, 142ca369, 271d71e2, d8e07eb2, 16b78196 | P1 — irregular renderer |
| **extend+recolor (multi-op)** | 195c6913, faa9f03d, 7b0280bc | P2 — mixed |

Type system (minimal, per report, validated): `Grid, CanvasSpec, Region, Obj, ObjSet, Mask, Point, PointSet,
Route, Color, Axis, Dir, Int, Bool`. **Separate selection types from drawing types** (so search narrows roles
before painting); **drawing emits overlays composed at the end** (pure, enables equivalence-sharing + clean
LOO).

## 4. First experiments — re-ordered for what we've ALREADY done

The report's 5 experiments, specialized (✅ = done this lane; → = next):

1. ✅ **Shape-first flip** — done: 16/23 shape-pred; pixel repair 0/23. *Conclusion already reached: repair is
   not the tranche; representation is.* Skip further repair.
2. → **marker→host→action relation-graph sketch** (report exp 3, our highest-value). Build an object-graph IR
   with host **pointing-direction** as a first-class relation (apex tip + frame-opening direction). Re-run
   apex-ray as a *sketch* with the richer direction primitive; target dd6b8c4b (marker-select sketch) +
   3dc255db (host-direction sketch). **This directly attacks the apex-ray frame-host gap and the dd6b8c4b
   selector** — the 2 tasks where the abstraction is already pinned. Gate: informative-LOO (§2) — the sketch
   must re-derive bindings per held pair, so LOO is *not* vacuous here.
3. → **output-shape GENERATOR** for the 7 decomposition tasks (crop/new-canvas/serialize-by-count). Shape-pred
   becomes a generator + content-render. Highest-coverage single bucket.
4. → **routing/bracket primitives** (report exp 2) for the 6 routing-renderer tasks. Exact executors on ≤30×30;
   the learned part chooses anchors. (cb2d8a2c = per-bar bracket routing — the concrete spec is in
   arc2_relational_synth_report.md.)
5. → **macro induction** (report exp 5): mine recurring typed subprograms from any design solves; promote only
   on cross-task firing ≥2. (No solves yet → deferred until 2–4 produce some.)

## 5. Synthetic data plan (leak-safe)

Per report: generators teach *which latent relational choices matter*, NOT public-task surface forms.
- Generator families = our miss types: routing (marker→host ray/bracket), redraw (extract→normalize→stamp),
  marker-host binding (select by hole-count/enclosure/nearest), panel/decomposition, symmetry+1-2-edit.
- **Disambiguation discipline:** sample so the simpler shortcut FAILS across the 2–5 train examples (ARC-TGI
  lesson) — directly targets our LOO-vacuity problem (a shortcut that's train-exact must be broken by a
  sibling example).
- Learned targets are STRUCTURAL: shape-family, decomposition-family, object-view, sketch-family, role
  bindings, next-operator-family — never raw pixels.
- **Leakage firewall:** do NOT train competition-facing learned components on ARC-TGI/public-task generators;
  family-level holdouts only; frozen prompts; offline.

## 6. Architecture (target, standalone prototype path)

`parser bank (multi-view) → object-graph IR (nodes: grid/region/obj/marker/panel/route/overlay; edges:
contains/contact/align/order/host-marker) → shape-decomposition predictor → sketch proposer (tiny GNN/heuristic
top-k) → typed enumerator (inverse constraints, state-hash, equivalence-merge) → exact route/redraw executor →
bounded repair (last) → verifier (informative-LOO + cross-task firing + synthetic-soft + diversity top-2)`.
Pure Python/NumPy core; optional tiny PyTorch proposer; deterministic module packaging. Anytime, budget-aware;
rank **task-level** programs (some tasks have 2–4 test pairs); top-2 diverse at the family level.

## 7. Risks (and our status)

- **public-eval overfit** → frozen design/calibration split already enforced; one-shot frozen per family.
- **train-exact but non-general** → THE recurring failure (LOO-vacuity); §2 gate is the fix.
- **task-ID/template leakage** → scrubbed-ns + leakage-scan already standard; Codex re-scans every handoff.
- **runtime blowup** → shape-first + sketch priors + equivalence-sharing (e-graph/tree-automata) before scaling.
- **neural dependency/packaging** → keep proposer tiny + optional; symbolic core must solve without it
  (report: avoid TTFT-style 4×H100 pipelines for a notebook).

## 8. Immediate next standalone probe (this lane)
Experiment #2 above: an **object-graph relation IR + host-pointing-direction primitive**, re-running apex-ray
as a sketch to (a) handle frame-hosts (complete 3dc255db, if a *design-justified* direction rule exists) and
(b) attempt the dd6b8c4b marker-select sketch. Report train-exact / informative-LOO / synthetic / leakage per
the corrected protocol. If informative-LOO holds AND design-test passes → hand to Codex; else falsify with the
precise binding that failed.
