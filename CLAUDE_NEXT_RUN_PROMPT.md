# Claude Next Run Prompt

Continue until 2:08 AM CST as a standalone research lane.

Codex verified and pushed the object-graph scaffold to the lightweight handoff branch:

`research/deep-research-handoff-2026-05-30`

Important verification notes from Codex:

- `arc2_object_graph.py` compiles and parses `23/23` current design misses.
- Static scan is clean: no task-ID string constants and no test/pseudo-private/public-signature/template/solver-replay references.
- Codex fixed two scaffold issues after the initial Claude commit:
  - object IDs are now deterministic and compact per parser call;
  - `line_segments` now includes diagonal and anti-diagonal runs, matching its documentation.
- Dense tasks can produce relation explosions (`89565ca0`: 60 color objects, 5080 relations), so downstream search must index/filter relations by sketch.

## Next Build

Build a standalone shape/decomposition generator on top of `arc2_object_graph.py`.

Create:

- `arc2_shape_decomposition_synth.py`
- `tmp/claude_shape_decomposition_results.json`

Do not edit:

- `arc2_candidate_solver.py`
- `submission_helper.py`
- `kaggle_modules`
- notebooks

## Target Bucket

The 7 shape-change design misses:

- `5dbc8537`
- `edb79dae`
- `20a9e565`
- `2d0172a1`
- `6ffbe589`
- `e87109e9`
- `89565ca0`

## Candidate Families

Implement bounded ladders for:

1. frame/interior extraction:
   - detect frame/rectangle/panel candidates,
   - crop or summarize interior,
   - preserve/recolor selected content.
2. compact glyph/table rendering:
   - map selected objects or holes to a smaller output grid,
   - order by row/col/reading order,
   - render dominant colors or role colors.
3. separator/panel crop-stack:
   - split by full separator rows/cols,
   - solve/serialize panels into a new canvas.
4. object-summary canvas:
   - output shape from object counts, bbox sizes, color roles, hole counts,
   - render one cell/mini-glyph per selected object.
5. dominant-filler removal:
   - crop non-filler bands or remove repeated filler rows/cols.

## Admission Protocol

- Train exact is required for any candidate.
- Informative LOO is required if the family learns parameters.
- If a transform is effectively fixed/parameter-free, mark `loo_informative=false` and require cross-task firing >=2 before calling it promotable.
- Synthetic invariance is a family-specific soft score:
  - color permutation where color roles are symbolic,
  - padding/translation where the output frame is not absolute,
  - panel-size variation for panel operators,
  - object relocation/count variation for object-summary operators.
- Local design test output may be used only as readout, never for synthesis.
- No task IDs, coordinate signatures, public templates, or train/test replay in core logic.

## Reporting

For each target, report:

- best family,
- train exact yes/no,
- informative LOO yes/no,
- synthetic invariance score/status,
- design-test readout,
- failure locus if not solved: shape, selector, renderer, ordering, color-role, decomposition,
- static leakage scan result.

Append the summary to `CLAUDE_TRACK_STATUS.md`.

If useful, append a concise handoff to `ARC2_AGENT_COORDINATION_STATUS.md`.

## Stop / Continue Rules

If no flips:

- Do not grind variants endlessly.
- Stop after the bounded ladder per family.
- Write the falsification clearly.
- Then move to the next infrastructure stage: `arc2_typed_sketch_enumerator.py`, using object graph relations to enumerate sketch skeletons without rendering public/test-specific rules.

If any train-exact + informative-LOO or cross-task-firing>=2 candidate appears:

- Stop and hand off to Codex with:
  - exact transform description,
  - train/LOO evidence,
  - synthetic evidence,
  - design readout,
  - leakage scan,
  - how to port into `arc2_candidate_solver.py` behind a feature flag.
