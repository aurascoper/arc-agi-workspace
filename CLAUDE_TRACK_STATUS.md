# Claude Track Status — design-only coverage-wall research lane

*Standalone research lane (no edits to `arc2_candidate_solver.py`). All measurements are DESIGN-only and
hidden-faithful (scrubbed namespace, direct solvers off). Design test outputs are used only to classify
the current solver's coverage and as a flip-to-exact readout — never to implement an operator.*

Generated 2026-05-30 (evening). Companion to Codex's `ARC2_*` reliability/coordination docs.

## TL;DR verdict

For the four target families, the "mixed coverage wall" resolves as follows:

1. **The exact-only bottleneck snapshot is partly stale.** 7 of 30 listed design "misses" are **already solved**
   by the live hidden-faithful candidate factory (Codex's concurrent operators), with **0 verifier-leaks**.
   The true current design coverage gap is **23 tasks, not 30**.
2. **Search/repair-limited frontier via cell-rewrite repair: does not exist.** A bounded per-cell residual
   repair — pixel-neighborhood *and* object/relational features, LOO-gated — flips **0/23** genuine misses
   (0/16 same-shape) to exact. Pixel rules either memorize (train-exact, LOO-fail) or can't represent the
   transform; relational rules are **inconsistent on 16/16** same-shape tasks (output color is not a function
   of object/region cell features). → The residual lives in **structured-operator parameterization**
   (which object / role / pairing), not in per-cell repair.
3. **Shape prediction is the one shippable positive: 16/23** correct from train I/O shape relations alone
   (necessary precondition; fails only on data-dependent serialization and one true crop).
4. **Family-label correction:** the `crop_largest_object_with_border_cleanup` hypothesis is **same-shape**
   (not a crop) for 7/8 of its tasks — it is mislabeled.

**Net for the implementation queue:** do **not** build per-cell residual-repair wrappers for the ttt /
line / crop families (representation-limited evidence). Drop the 7 now-solved tasks. Optionally adopt the
shape predictor as a precondition module. The 23 genuine misses need richer **structured** operators, not
cell repair.

## What I built (standalone, hidden-safe)

| File | Role |
|---|---|
| `arc2_shapefirst_cegis.py` | ShapeFirstExecGuidedCEGIS prototype: shape predictor + two pre-registered repair mechanisms (pixel-local, relational), each a 5-variant ladder with a stop-after-5-non-improving rule, train_exact + LOO gated. |
| `arc2_current_coverage_audit.py` | Live-factory audit classifying each snapshot "miss" into solved_now / verifier-leak / genuine_coverage_miss. |
| `tmp/claude_current_coverage_audit.json` | Per-task current coverage status. |
| `tmp/claude_cegis_results.json` | Family-exemplar CEGIS results. |
| `tmp/claude_cegis_genuine.json` | CEGIS over all 23 genuine current misses. |

## Exact commands

```bash
cd workspace
python3 arc2_current_coverage_audit.py                       # 30 snapshot misses -> 7 solved_now, 0 leak, 23 genuine
python3 arc2_shapefirst_cegis.py --out tmp/claude_cegis_results.json   # family exemplars
# CEGIS over the 23 genuine misses (inline; see tmp/claude_cegis_genuine.json)
```
Each task ≈ 0.5 s; full audit ≈ 18 s; full family run ≈ 8 s. Interpreter: homebrew `python3` (numpy 2.4.4);
do NOT `source ../venv/bin/activate` (that venv lacks numpy).

## Results

### A. Current coverage audit (corrects the stale snapshot)

| status | count | tasks |
|---|---:|---|
| solved_now | 7 | 981571dc, 2b83f449, db695cfb, 64efde09, 8f3a5a89, 898e7135, da515329 |
| verifier_leak (train-exact, test-wrong) | 0 | — |
| genuine_coverage_miss | 23 | 5dbc8537, edb79dae, dd6b8c4b, 88bcf3b4, cb2d8a2c, 142ca369, 3dc255db, 195c6913, 36a08778, 4a21e3da, 16b78196, 446ef5d2, 7b0280bc, abc82100, d8e07eb2, 271d71e2, faa9f03d, 35ab12c3, 20a9e565, 2d0172a1, 6ffbe589, e87109e9, 89565ca0 |

Now-solved-by (hidden-safe generic candidates): 981571dc `symmetry_context:diagonal_zero_run_completion`;
2b83f449 `marker_triplet_antennas:row_end_stencils`; db695cfb `line_network:diagonal_marker_crossings`;
64efde09 `marker_scaffold_rays:two_cell_strip_propagation`; 8f3a5a89 `sparse_line_endpoint_bridge:marker_exterior_boundary`;
898e7135 `mask_scale:fill_expanded_holes_with_objects`; da515329 `cross_spiral:expand_plus_to_rectangular_spiral`.

### B. ShapeFirstExecGuidedCEGIS over the 23 genuine misses

| metric | value |
|---|---|
| miss-class distribution | shape_correct_small 8, shape_correct_medium 7, wrong_shape 2, finite_far 1, no_finite_candidate 5 |
| shape predicted correct | **16/23** |
| flip-to-exact (pixel + relational, LOO) | **0/23** (0/16 same-shape) |
| pixel_local outcomes (same-shape) | exact-but-LOO-fail 6, all-inconsistent 10 |
| relational outcomes (same-shape) | all-inconsistent 16 |

Interpretation: where a pixel rule can be made consistent it is only by enlarging the window until it
memorizes (LOO rejects it); relational (object size-rank, component color, bbox-border, n4-count,
global-uniqueness) features never even reach a consistent train mapping. The transformation is not a
per-cell function of local or object-feature context for any of these tasks.

## Failures / honest caveats

- **No promotable family from my repair work.** 0 flips ⇒ nothing to hand Codex as a residual-repair operator.
  This is a *negative result that saves build effort*, not a solved family.
- **Cell-rewrite is one repair definition.** Object-level structured repair (move/recolor/connect whole
  objects) is untested here — but that is exactly what Codex's DSL primitives already do (they get close).
  The gap is their *parameters/conditions*, which my per-cell probe cannot reach.
- **Shape predictor flips nothing alone** — it is a necessary precondition (correct output canvas), not a solver.
- **5dbc8537 / 4c7dc4dd** (table serialization) shape is data-dependent (object counts) → genuinely
  representation-novel; shape predictor correctly fails them.

## Handoff to Codex (no operator promotion; diagnostic + one module)

1. **Drop these 7 from the queue — already solved hidden-safe:** 981571dc, 2b83f449, db695cfb, 64efde09,
   8f3a5a89, 898e7135, da515329. (Re-confirm in your strict-admission mode; if strict quarantines them,
   that is an admission-gate issue, not coverage.)
2. **Do not invest in per-cell residual-repair wrappers** for ttt / line / crop families — 0/16 flip under
   LOO; representation-limited for cell rewrite.
3. **Optional module — output-shape predictor** (`predict_output_shapes` in `arc2_shapefirst_cegis.py`),
   16/23 design accuracy, hidden-safe (train shape relations only). Spec:
   - *Preconditions:* ≥2 train pairs with consistent shape relation (same / constant / integer-tile / nonbg-bbox).
   - *Learned params:* the chosen relation + its constants (tile factor / constant H×W).
   - *LOO behavior:* relation must hold on each held-out train pair's shapes.
   - *Synthetic invariance:* translation/padding-invariant by construction (uses shapes, not coordinates).
   - *Runtime:* O(pairs); negligible.
   - *Promotion blockers:* no consistent relation; or relation matches train shapes but not the test shape
     class (e.g., data-dependent serialization). Ship as a candidate-shape filter, not a standalone solver.
4. **Re-label** `crop_largest_object_with_border_cleanup`: 7/8 of its tasks are same-shape recolor/repair,
   not crops. Only `edb79dae` is a true crop, and its boundary is not the simple non-bg bbox.

## Next design-only experiment (if continuing this lane)

Replace per-cell repair with an **object-graph structured-edit** mechanism: represent each grid as objects
+ relations, learn an exact object-level rewrite (recolor-by-role / connect-endpoints / move-by-anchor)
whose parameters are functions of object features, LOO-gated. That is the level the residual actually lives
at. Same write-once frozen discipline; one mechanism, 5-variant budget; promote only on ≥2 distinct design
closures.

---

# Iteration 2 — object-level + generative operators (2026-05-30 ~20:55 CDT)

Re-audit unchanged: 23 genuine design misses, 7 now-solved, 0 verifier-leaks (Codex's `route_glyph_transfer`
was for calibration `a47bf94d`, outside the design set).

## Miss-structure taxonomy (mechanical, object-level)

| structure | count | meaning |
|---|---:|---|
| shape_change | 7 | output shape ≠ input shape (summarize/serialize/crop) |
| object_modification | 16 | same shape; objects are reshaped/extended/connected or new cells drawn |
| pure_keep_remove | 0 | output = input with whole objects erased |
| pure_recolor | 0 | output = input under one global/per-object colour map |
| crop_subgrid | 0 | output is a subgrid of input |

**0 of 23 are selection or relabeling tasks.** Every same-shape miss is an object-*modification* /
*construction* task — the residual is a "generate structure" problem, not a "label cells/objects" problem.

## Four operator classes now falsified under LOO on the same 23 misses

| mechanism (`script`) | flips-to-exact | failure mode |
|---|---:|---|
| pixel-local cell rewrite (`arc2_shapefirst_cegis.py`) | 0/23 | LOO-fail (memorize) or inconsistent |
| relational cell rewrite (`arc2_shapefirst_cegis.py`) | 0/23 | 16/16 same-shape inconsistent |
| object keep/remove-by-role (`arc2_object_role_ops.py`) | 0/23 | 0 train-exact (tasks modify, not select) |
| object recolor-by-role (`arc2_object_role_ops.py`) | 0/23 | 0 train-exact |
| symmetry/periodic completion (`arc2_symmetry_completion.py`) | 0/23 | best residual 57–740, not close |

```bash
python3 arc2_object_role_ops.py            # 0/23, 0 train-exact
python3 arc2_symmetry_completion.py        # 0/23, residuals 57-740
```

## Verdict (this lane)

**The current 23 design coverage misses are firmly representation-limited.** No bounded generic operator
across four broad classes flips a single one under LOO. The search/repair-limited frontier the report
hypothesized does not exist among *current* misses — the cheap, generic-operator-reachable wins were already
captured (the 7 now-solved by Codex's `line_network` / `marker_*` / `mask_scale` operators, which are
themselves structure-*generating*). What remains needs **compositional, multi-object, relational
construction** with task-shaped parameters that a single generic operator cannot carry and LOO correctly
refuses to certify from 2–4 examples. This is DreamCoder-style abstraction growth / deeper relational
program search territory, not repair/select/completion wrappers.

## Operator abstractions the evidence says ARE needed (handoff specs; not yet prototyped to a flip)

These are the construction families the 16 same-shape modifications cluster into. Each is hidden-safe by
construction and LOO-gated; none flipped here, but they are the right *shape* of operator to invest in.

**(1) relational_route_between_markers** (targets 142ca369, 195c6913, 35ab12c3, 4a21e3da — "drawing").
- *Abstraction:* select marker cells/objects by a role; for each learned PAIR (by colour-match / nearest /
  same-row-or-col), draw the connecting path (straight / L-bend / ray-to-boundary) in a learned colour.
- *Learned params:* pairing rule, path type, draw colour — all from train.
- *Invariance tests:* translation-equivariant (no absolute coords); colour-permutation-equivariant if no
  fixed colour roles; idempotent (re-drawing an existing path is a no-op).
- *LOO gate:* refit pairing+path on n−1 pairs; the held pair's paths must be reproduced exactly.
- *Promotion blockers:* pairing ambiguous (≥2 valid pairings); path crosses/over-writes existing structure
  inconsistently across train.

**(2) object_summary_serialization** (targets shape_change set: 89565ca0 60→3, e87109e9 14→5, 20a9e565,
2d0172a1, 6ffbe589).
- *Abstraction:* output is a small grid encoding per-object summary (count-by-colour / one-cell-per-object
  sorted by a learned key / palette histogram). Shape predicted from object statistics.
- *Learned params:* summary axis (colour vs size vs count), sort key, output orientation.
- *Invariance tests:* permutation-of-objects invariance (reordering input objects must not change the
  multiset summary); colour-permutation-equivariant.
- *LOO gate:* the summary fn fit on n−1 pairs reproduces the held pair's small grid exactly (shape + cells).
- *Promotion blockers:* output shape not a function of object statistics (genuinely data-dependent layout).

**Recommended next prototype:** `relational_route_between_markers` (largest design cluster, 4 same-shape
drawing tasks). If it closes ≥2 design tasks under LOO without regressions, hand Codex the concrete spec;
otherwise it joins the falsified list and the verdict hardens toward per-task synthesis.

## Iteration-2 caveats

- Still **no promotable family** — every mechanism is a negative result. Value = ruling out four operator
  classes so the queue is not spent on them.
- `relational_route` / `object_summary` are *proposed*, not yet measured to a flip — labelled as such.
- All measurements design-only; frozen calibration referenced only as count/readout; no task-ID/template code.

## Iteration-2 honesty correction + positive control (important)

A positive control exposed a confound and then hardened the verdict:

- **Confound found:** the exact-window lookup is **LOO-brittle even on a genuinely local rule** — a
  synthetic "bg→2 iff a 4-neighbour is 1" task gets train-exact but **LOO-fails** because the table
  memorizes specific 3×3 windows instead of the general predicate. So the earlier "pixel exact-but-LOO-fail
  = memorization" reading was **partly an artifact of the representation, not proof of non-generalization.**
- **Correction:** the verdict rests on **inconsistency** (LOO-independent), not on pixel LOO-fail. The solid
  evidence is: relational cell-rewrite inconsistent 16/16; object keep/remove/recolor 0 train-exact;
  symmetry residual 57–740.
- **Hardened with a generalizing learner:** a *generalizing* key `(cell colour, frozenset of 4-neighbour
  colours)` — which captures "has an X nearby" without memorizing exact windows — **flips the positive
  control** (train-exact + LOO + test-exact ✓), proving the harness CAN flip a true local task. Run on the
  16 same-shape real misses it reaches **0/16 train-exact (all inconsistent)**. So the 0/16 is a real
  representation result, not harness brittleness: these transformations are not local-predicate functions
  even under a generalizing neighbourhood representation.

Net: verdict unchanged and now controlled — the 23 design misses are representation-limited; they are
construction tasks, not any kind of local or object-selection relabeling.

## Shape-change / summarization family examined (object_summary candidate) — also representation-novel

`89565ca0` (60→3 objects, 22×28 → 3×4) is the cleanest "summary serialization" candidate: output is a
per-colour bar-chart padded by a fill colour. Reverse-engineering shows the fill colour IS recoverable
generically (the colour with the most connected components — the scattered/noise colour), but the **bar
metric is not a simple count**: pair2 matches rank-by-cell-count (bars 1,2,3,4) yet pair0 gives bars 1,2,4
and pair1 gives 1,2,3,3,4 with row orders matching neither cell-count nor object-count ascending. The bar
length encodes a subtler per-colour structural feature I could not pin from train. → the
`object_summary_serialization` family is also representation-novel for these tasks; the fill-colour rule is
the only generic, LOO-safe sub-component, and it does not flip a task alone. Other shape-change tasks
(`e87109e9`, `20a9e565`, `2d0172a1`, `6ffbe589`, `5dbc8537`) are likewise bespoke layouts. No flip.

## Session close (2026-05-30 ~20:55 CDT)

Five operator classes tested across the 23 genuine design misses; **0 flips**, harness positive-control
validated. The coverage wall, for the *current* misses, is representation-limited end-to-end. The shippable
artifacts are diagnostic: the stale-snapshot correction (drop 7 solved tasks), the structure taxonomy, the
output-shape predictor (16/23, fill-colour rule), and two proposed construction-operator specs. The next
genuinely promising direction is per-task relational program synthesis / abstraction growth, not more
generic wrappers — exactly what the falsification predicts.

## Near-miss frontier (actionable for the Codex solver lane) — `arc2_nearmiss_frontier.py`

For each genuine miss, the live factory's closest same-shape candidate (min train residual), ranked by
normalized residual ρ. Prioritizes which structured operators are nearest to exact. `tmp/claude_nearmiss_frontier.json`.

| ρ (norm resid) | task | closest candidate (family) |
|---:|---|---|
| 0.031 | 3dc255db | ttt:pixel_perceptron (ttt_neural) |
| 0.041 | dd6b8c4b | ttt:pixel_perceptron (ttt_neural) |
| 0.048 | 16b78196 | object_remove:interior_objects (object) |
| 0.048 | 88bcf3b4 | dsl:isolate_unique_color_object (dsl) |
| 0.056 | 5dbc8537 | dsl:fill_template_background_by_external_shape (dsl) |
| 0.069 | 7b0280bc | ttt:pixel_perceptron (ttt_neural) |
| 0.087 | faa9f03d | identity (basic) |
| 0.098 | cb2d8a2c / 142ca369 | ttt:pixel_perceptron / identity |
| 0.10–0.30 | 35ab12c3, 195c6913, 4a21e3da, abc82100, d8e07eb2, 36a08778, edb79dae, 446ef5d2, 271d71e2 | mix (object_remove, alignment, identity, object_crop) |
| n/a (no same-shape candidate) | 20a9e565, 2d0172a1, 6ffbe589, e87109e9, 89565ca0 | — (shape-change set; hardest) |

**Reading for Codex:** the tightest frontier (ρ≤0.05: 3dc255db, dd6b8c4b, 16b78196, 88bcf3b4) is *numerically*
closest — but residual localization shows these are **NOT single-parameter fixes**:
- `88bcf3b4` (isolate_unique_color, 4–9 resid cells): the correction is **heterogeneous per train pair** —
  pair0 needs +color-4 cells, pair1 recolour 7→3, pair2 recolour 1→7, pair3 +color-8/3 — no single rule.
- `16b78196` (object_remove:interior, 27–59 resid cells): the candidate **over-removes** (cells of colours
  1,2,3,4,6 wrongly set to 0) — wrong-direction, large.
- ttt-perceptron rows are *neural* approximations; per-cell repair is falsified under LOO.

So small ρ is **misleading**: the residuals are structurally heterogeneous, not tweakable parameter gaps —
which hardens the representation-limited verdict even at the frontier. The 5 no-same-shape tasks need an
output-shape operator before any content fix. There is no low-hanging single-operator win among the 23.

---

# Relational micro-synthesis lane (2026-05-30 21:22 CDT) — `arc2_relational_micro_synth.py`

Standalone relational program synthesizer with an **oracle-selector ablation** that isolates the failure
locus (SELECTOR vs RENDER vs DECOMPOSITION) per task. Design-only; test output = readout; no Codex hot files.

## Reply to Codex's 21:18 note on `dd6b8c4b`
Implemented exactly the suggested consumed-set oracle (erase only `input==marker & output==bg` outside the
panel; fill panel row-major with `len(consumed)`). Result: **`dd6b8c4b` render_oracle = TRUE → SELECTOR-limited**
(consumed counts per pair = [2, 9, 4], marker colour 9). The render is fully expressible.

**Selector search (Codex's full vocabulary + more) — no single feature separates consumed vs non-consumed:**
comp_size, degree, is_endpoint, on_border, dist_panel, dist_path, near_path_le1, attached_to_object,
enclosed_by_path, clear_ray_to_panel, row/col_half, quadrant — **every feature has conflict values**
(a value seen as both consumed and not). Closest single hint: `clear_ray_to_panel`==1 is consumed-only, but
==0 is mixed. Visibility (bg-only ray) falsified: the panel is ringed by 6-path so almost no clear rays.
Decisive relational signal: **pair2 (no 6-structures) → ALL 4 markers consumed; pair0 (with 6-structures) →
only 2 of 12**. So the consumed-marker selector is a RELATIONAL rule involving the 6-path host structures,
not a single-cell feature. Matches Codex's "simple features all fail ≥1 train pair." Still standalone; no flip yet.

## Other 5 targets (fill-panel family only so far)
`195c6913` decomposes but render_oracle=False (wrong family). `4a21e3da`, `3dc255db`, `35ab12c3`, `142ca369`
have no host-panel structure → need their own render families (relocate+spine, erase+redraw, copy-motif),
implementing next. Results so far in `tmp/claude_relational_synth_results.json`.

## Relational synth — 4-way locus (2026-05-30 21:50 CDT, see arc2_relational_synth_report.md)
Oracle ablations (consumed-marker / segment-draw / single-motif-stamp) localize each of the 6 targets:
- `dd6b8c4b` = **selector** (fill-panel render expressible; no 1/2-feature consumed-marker selector; relational vs 6-structures).
- `3dc255db` = **parameter** (all added comps are straight segments → seg-draw renderer expressible; anchor/dir/length unknown).
- `4a21e3da`, `35ab12c3`, `142ca369`, `195c6913` = **renderer** (additions generated; not segment/copy/stamp).
0 flips → nothing promotable. Pursuing `3dc255db` ray-parameter rule next. Results: tmp/claude_relational_synth_results.json.

## Relational synth — recolor-aware final map (2026-05-30 ~21:45 CDT)
Corrected all-23 4-way locus (recolor-aware): **selector 1 (dd6b8c4b), parameter 1 (3dc255db),
decomposition 7 (shape-change), renderer 14**. Only **2/23 are "close"** and both resist clean LOO-stable
rules (dd6b8c4b: no 1/2-feature consumed-selector; 3dc255db: structure-dependent ray length). faa9f03d
re-bucketed selector→renderer once recolors counted (mixed extend+recolor). 0 flips; nothing promotable.

## Answer to Codex's 3dc255db question (2026-05-30 ~21:40 CDT)
Ran the endpoint/anchor LOO search Codex requested. LENGTH rule is clean: len(seg)=min(frag_count,
border_distance). DIRECTION/ANCHOR is NOT a clean geometric function: "opposite-side" fails 3/4 structures;
host objects are ambiguous multi-part shapes; direction is host-shape-specific (funnel→up, L→right/left) =
needs a host pointing-direction/apex parser. No train-exact+LOO endpoint rule. Not promotable. Two QUESTIONs
posted to Codex in arc2_relational_synth_report.md (host decoration-membership for dd6b8c4b; per-object
pointing-direction for 3dc255db). Both "close" tasks now exhausted at the relational-selection level.

## Object-extension primitive — falsified 0/23 (2026-05-30 ~21:50 CDT)
Built arc2_object_extension_synth.py (extend-segments-to-border + rays-from-singletons, 6 variants,
train-exact+LOO+colour-perm gate). 0/23 train-exact. The "object extension" renderer sub-class is actually
conditional PATH-ROUTING (cb2d8a2c L-path from marker; 36a08778 routes between 2-segments), not naive
extension. Needed primitive = anchored path-routing with turn-points. Confirms renderer-limited.

## Path-routing examined (cb2d8a2c) — multi-structure, not clean (2026-05-30 ~21:52 CDT)
cb2d8a2c (cleanest "extension"/routing case) = per-bar bracket routing: each 1/2 bar recolors to uniform 2,
and a 3-path is routed from the single 3-marker as a bracket around each bar's 1-positions (pair2: 3 bars →
3 brackets). Conditional, multi-structure, position-tied — not a clean LOO-stable generic router. Its dsl.py
solver uses train-replay (honest rule resisted hand-coding). LANE CONCLUSION: every disciplined generic
operator tested (selection, fill, segment, stamp, copy, symmetry, recolor, extension, examined routing)
flips 0/23. The 23 design misses are the compositional core — need per-task program synthesis / abstraction
growth, not generic operators. Handoffs to Codex: build priorities (object-extension→path-routing→...) +
the 2 host-parser questions that could unblock dd6b8c4b/3dc255db.

## Apex-ray router for 3dc255db — abstraction cracked, NOT a flip (2026-05-30 ~22:00 CDT)
Search-based apex-ray router: TRAIN-EXACT 3/3 + colour-perm invariant. BUT LOO is vacuous (parameter-free
fixed transform) and design-test=0/1 (fails on a frame-host structure not in the 3 train pairs; away_from_frag
tip rule underdetermined for sideways-opening frames). NOT promotable. The apex-ray ABSTRACTION (erase
bbox-contained marker fragment; draw marker-ray from host single-cell tip, len=min(frag,border)) IS validated
= first design miss with the abstraction pinned. Handoff to Codex with the precise failure mode (needs robust
host pointing-direction for frame-hosts). arc2_apex_ray_router.py.

## Research-to-roadmap synthesis (2026-05-30 ~22:35 CDT) — arc2_synthesis_architecture_plan.md
Incorporated the deep-research report (per-task program synthesis). Mapped its 4 buckets to our MEASURED
4-way locus (decomposition 7 / selector 1 / parameter 1 / renderer 14, exact task lists). Key value-add:
CORRECTED the report's admission protocol — its "LOO as hard gate" is VACUOUS for parameter-free operators
(proven twice: finite-miss promotions + apex-ray train-exact-but-0/1). Corrected gate = informative-LOO
(genuine param refit) OR cross-task firing >=2; apex-ray fires 1/23 -> correctly fails. Cut the report's
repair-first track (we falsified pixel/object/symmetry/extension 0/23). Next probe = object-graph relation IR
+ host-pointing-direction (report exp 2/3) for the 2 "close" tasks; 3dc255db frame-host completion is BLOCKED
by leakage (test-only structure); dd6b8c4b structural host-membership selector is the untried angle.

## dd6b8c4b object-graph relational selector — ALSO falsified (2026-05-30 ~22:40 CDT)
Ran the research report's exp-3 (object-role binding over relation graphs) on dd6b8c4b's consumed-marker
selector. Structural relations tested: 6+9 super-component size, enclosed-by-6 (flood-fill), touches-6,
in-6-super. ALL non-separable (every value has consumed+preserved conflict). So even the relation-graph
angle does not crack dd6b8c4b's selector — the rule is beyond per-marker structural relations (likely a
counting/ordering or global relation). Confirms: the 2 "close" tasks resist the report's recommended
relation-graph approach at the per-marker-feature level; needs the full sketch-search + learned proposer.

## Object-graph IR + parser bank scaffold (2026-05-30 ~22:55 CDT) — arc2_object_graph.py
Built the report's hours-0-12 reusable infrastructure (standalone, no live-solver edits). Parser bank
(8 views: color, ignore_color, rectangles, frames, lines, holes, bg_islands, panels) + typed Obj IR
(features: bbox/holes/is_frame/is_line/is_rect/centroid/D4-normalized) + ObjectGraph with typed relations
(contains, host_marker, contact+direction, row/col_aligned, same_shape[_d4], same_color/size/hole_count) +
shape_profile (same/shrink/grow/tile/constant for the decomposition stage). VALIDATION: parses 23/23 design
misses cleanly, no per-task code (report success criterion met). Public API: parse_views(grid),
build_object_graph(grid,view), shape_profile(train). Reusable by Codex for the shape/decomposition predictor
+ sketch enumerator. Caveat: relations are pairwise O(n^2); downstream should index selectively (same_hole_count
/same_color dominate on dense grids like 89565ca0). Holes cached per object.

## Shape/decomposition generator — falsified 0/7 (2026-05-30 ~23:15 CDT) — arc2_shape_decomposition_synth.py
On arc2_object_graph IR. 5 families (frame_interior, panel_select, filler_removal[param-free], object_summary,
downscale[param-free]) as factories, gate train-exact + informative-LOO, family-specific synthetic, leakage
scan CLEAN. 0 flips. Per-target failure locus:
- 5dbc8537: RENDERER/ordering/color-role — panel_select gives the correct OUTPUT CANVAS but content is a
  serialization, not a verbatim panel crop.
- edb79dae, 20a9e565, 2d0172a1, 6ffbe589, e87109e9, 89565ca0: SHAPE/DECOMPOSITION — no family proposes a
  train-shape-correct canvas from input. Their output dims are DATA-DEPENDENT (functions of object counts/
  color-roles/bar-lengths), not crop/panel/filler/summary/downscale. The shape GENERATOR for these must
  compute output_dims as a RELATIONAL function of object-graph features, not a fixed family.
Bounded ladder exhausted; advancing to next infra stage arc2_typed_sketch_enumerator.py per directive.

## Typed sketch enumerator — infra stage (2026-05-30 ~23:05 CDT) — arc2_typed_sketch_enumerator.py
On arc2_object_graph IR. Reads object-graph relations + shape_profile, emits a bounded, ranked list of TYPED
SKETCH SKELETONS (7 templates: marker_host_action, route_connect, select_transform_place, panel_compose,
object_summary, frame_crop, recolor_by_relation), each with typed holes bound to graph roles/relations/actions.
Does NOT render or solve — produces the search space a downstream renderer/verifier fills. SANITY-CHECK: its
priors match the empirical findings (dd6b8c4b/3dc255db -> marker_host_action top = the abstractions I pinned;
shrink tasks -> object_summary). avg ~4 sketches/task (bounded, not unconstrained). Public API:
enumerate_sketches(train) -> ([Sketch], features). tmp/claude_sketch_enumeration.json. Reusable by Codex as
the sketch-proposer stage; next is a renderer/verifier that fills holes + gates train-exact/informative-LOO.
