# ARC2 SIA Shape/Decomposition Task Spec

Purpose: run SIA as an outer, quarantined autoresearch loop for the ARC2 shape/decomposition bottleneck. This is a standalone research target, not a Kaggle attempt lane.

## Allowed Goal

Improve the standalone shape/decomposition research prototype beyond `arc2_shape_decomposition_synth.py` by discovering relational output-shape and rendering programs for the 7 measured shape-change misses:

- `5dbc8537`
- `edb79dae`
- `20a9e565`
- `2d0172a1`
- `6ffbe589`
- `e87109e9`
- `89565ca0`

The desired deliverable is a standalone prototype, for example:

- `arc2_shape_decomposition_synth_vN.py`
- `tmp/sia_shape_decomposition_results.json`
- `SIA_SHAPE_IMPROVEMENT_NOTES.md`

## Hard Boundaries

Do not edit:

- `arc2_candidate_solver.py`
- `submission_helper.py`
- `kaggle_modules/`
- notebooks
- public/private/frozen data files

Do not use:

- ARC test/private answers
- pseudo-private/frozen calibration answers during synthesis
- public signature renderers
- task-ID dispatch
- coordinate replay
- output template replay
- `solve_<taskid>` or scrubbed-solver replay

The target agent may read the allowed public/design train pairs for the 7 tasks and may run evaluation readouts, but test/readout performance is not a promotion signal by itself.

## Required Evaluation Contract

Every generation should run:

```bash
python3 -m py_compile arc2_object_graph.py arc2_shape_decomposition_synth.py arc2_typed_sketch_enumerator.py
python3 arc2_codex_research_artifact_verifier.py
```

If the task directory is outside the full ARC workspace, set:

```bash
export ARC2_EVAL_DIR=/path/to/arc_agi_2_data/evaluation
```

The SIA evaluator should score and log:

- compile success
- static leakage scan success
- number of target tasks with a proposed transform
- number of train-exact transforms
- informative LOO pass count, only where the factory refits per held-out pair
- cross-task firing count for fixed/parameter-free transforms
- synthetic invariance pass count
- design/readout exact count
- shape-correct-but-content-wrong count
- wrong-shape-to-finite-diff transitions

## Promotion Bar

SIA output is only a handoff candidate if it has:

- no leakage/static-scan hits
- a concrete transform, not just a sketch
- train exactness
- informative LOO for learned/refit parameters, or cross-task firing `>=2` for fixed transforms
- family-appropriate synthetic invariance
- no public/design regression in the local readout

If these are met, Codex will independently port and verify it. Until then, the live solver remains untouched.

## Useful Starting Point

The current fixed-family probe is falsified:

- `arc2_shape_decomposition_synth.py`: `flips=[]`, `train_exact_rows=0`, `loo_rows=0`
- `5dbc8537`: output canvas can be found, but content requires serialization/order/color-role rendering
- the other six targets need output dimensions as relational functions of object-graph features such as object counts, color-role counts, holes, bar lengths, and panel structure

The current reusable inputs are:

- `arc2_object_graph.py`: parser bank and object graph IR
- `arc2_typed_sketch_enumerator.py`: bounded typed sketch skeletons
- `arc2_codex_research_artifact_verifier.py`: compile/run/leakage/readiness verifier

## Best Next Search Space

Prioritize relational dimension programs and renderer sketches:

- `dims = f(object_count_by_role, color_count_by_role, hole_count, line/bar lengths)`
- object summary canvas with learned row/column ordering
- compact glyph/table rendering
- panel serialization with per-panel local rules
- legend-driven crop/serialization
- shape-normalization followed by role-dependent recolor/render

Avoid another crop/filler/frame-only ladder; that family has already returned 0/7.
