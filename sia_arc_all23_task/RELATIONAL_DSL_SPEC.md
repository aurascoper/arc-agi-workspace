# Relational DSL spec — design-only (Claude-owned), the high-ceiling SIA-lite escalation

Motivation (evidence, 2026-05-31): task-conditioned free-form-Python LLM mutation (gpt-4.1-mini/4.1, one-shot +
hill-climb) FAILED to fit any renderer-14 task — diffs stayed flat (51/50/71/110/745) across 7 runs/6 tasks; the
single residual nudge was cb2d8a2c 131->127. Hand-probes confirmed every characterized task has a RELATIONAL/global
core (7b0280bc template-recolor, d8e07eb2 per-pair band trigger, 88bcf3b4 move-along-rail, cb2d8a2c 115-cell
relational fill). Conclusion: the bottleneck is REPRESENTATION — arbitrary Python is too unconstrained for a weak
model to hit the relational target. This DSL constrains generation to the primitive space these tasks inhabit, so
the mutator searches op-compositions + learned params instead of free code. Programs gate IDENTICALLY through the
existing `evaluator.py` (train-exact + name-stable fold-varying LOO; readout log-only; leakage scan).

## 1. Typed values
`Grid` · `ObjSet` (connected components under a view) · `Obj` · `Region` (cell set, e.g. enclosed/panel/band) ·
`Marker` (isolated cell / line endpoint) · `Color` · `Dir` (4/8) · `Int` · `Bool`. Every op is typed; ill-typed
compositions are rejected at compile time (shrinks the search).

## 2. Parser primitives  (Grid -> values; pure, no params)
- `objects(view)` view ∈ {color, ignore_color, rectangles, frames, lines, holes, panels} -> ObjSet
- `markers()` -> ObjSet (degree<=1 cells)
- `enclosed_regions()` -> [Region] (bg regions not touching border + their enclosing colors)
- `panels()` / `bands(sep_color)` -> [Region]   (full-line-delimited bands; sep learned)
- `rails(color)` -> [Region]   (full-width/height single-color lines)
- `background()` -> Color

## 3. Selection / filter  (value -> value; params LEARNED from train)
- `filter(objset, pred)` pred ∈ {size==k, size_rank==r, color==c, shape==template, touches(role),
  los_to(role), unique_shape, in_region(R)}   — k/r/c/template are HOLES fit on train
- `select(objset, role)` role ∈ {largest, smallest, unique_color, by_count_rank=r}
- `anchor(objset)` -> Marker/Obj   (a single distinguished element)

## 4. Relational draw / transform ops  (the generative core; each has learned-param HOLES)
- `recolor_map(grid, {c_in: c_out,...})`     — global colour substitution (map learned from train diff)
- `route(grid, A, B, color, mode)`           — connect markers/objs A,B sharing row/col/diag; color, mode learned
- `fill_enclosed(grid, regions, color|rule)` — fill enclosed regions; color constant OR = enclosing-color rule
- `project_ray(grid, src, dir, color, stop)` — rays from src markers; dir/color/stop(=border|first_nonbg|len=k)
- `bbox_fill(grid, objset, color)`           — fill bounding box of selected objects
- `symmetry_complete(grid, axis)`            — mirror/rotate-complete; axis learned (h|v|d|point)
- `recolor_by_template(grid, objset, map)`   — objects matching a learned template-shape -> learned color
- `move_to_anchor(grid, objset, anchor, along=rail)` — translate objects toward anchor along a guide line
- `stamp(grid, markers, template)`           — paint a learned NxN template at each marker
Each op is a pure `Grid -> Grid`; a program is a PIPELINE of these (left-to-right).

## 5. Program format (what the mutator EMITS — not Python)
A JSON pipeline of typed op-calls; HOLES marked `{"learn": "<fit-key>"}` are filled by the interpreter from train:
```json
{"name":"recolor+enclosed_fill",
 "pipeline":[
   {"op":"recolor_map","args":{"map":{"learn":"color_bijection"}}},
   {"op":"fill_enclosed","args":{"regions":{"op":"enclosed_regions"},
                                 "color":{"learn":"enclosing_or_const"}}}]}
```
- `name` = the op-STRUCTURE signature with params ABSTRACTED OUT (so it is identical across train folds).
- Each `{"learn": key}` is fit by a registered fitter that reads ONLY train pairs and returns a concrete value;
  if the fit is inconsistent across train pairs the program is rejected (returns no candidate).

## 6. Compilation + gate contract (identical to today)
- A reference interpreter (`sia_arc_all23_task/dsl_interpreter.py`, design-only, stdlib-only, lives in the
  quarantine dir — NOT in any Codex hot file) compiles a pipeline+fitted-params into `propose(train)->[(name,t)]`.
- `name` = op-structure signature -> NAME-STABLE: dropping a train pair re-fits params but yields the SAME name.
- FOLD-VARYING by construction: the learned params (`color_bijection`, ray length, template, axis…) are re-fit per
  fold, so the transform fingerprint differs across folds -> earns `informative_loo`, NOT
  `train_exact_fixed_loo_vacuous`. (A program whose only op is a param-free fixed transform is still vacuous — the
  grammar should prefer ops with at least one learned hole.)
- LEAKAGE-IMPOSSIBLE BY CONSTRUCTION: the mutator emits op-names + learn-keys only — no file access, no grid
  literals, no task-ids are representable in the format. The existing leakage scan still runs as defense-in-depth.
- Readout stays LOG-ONLY; the tripwire (loo_tasks>=1 OR cross>=2) is unchanged.

## 7. Why the renderer-14 become expressible (search target, not free code)
- `cb2d8a2c` = `recolor_map(1->2)` ; then a fill/route op for the 115 `3`-cells (search the op + its region pred).
- `d8e07eb2` = `bands(6)` -> `filter(per-pair trigger)` -> `recolor_map(bg->3)` on selected bands.
- `7b0280bc` = `recolor_by_template(objset, learned_template -> 5/3)`.
- `88bcf3b4` = `move_to_anchor(objset, anchor=same_col_marker, along=rail(8))`.
The mutator's job shrinks from "write a correct relational Python program" to "pick a short op-pipeline + let the
fitters learn the params" — a bounded, typed search where a weak model is far likelier to hit train-exact.

## 8. Suggested wiring (Codex lane, when ready)
1. `dsl_interpreter.py` (quarantine dir): registry of ops + fitters + `compile(program, train) -> transform`.
2. SIA-lite `--mode dsl`: mutator system prompt emits the JSON pipeline (this format); harness compiles + scores
   through the SAME `evaluate.py`. Start the op-set small (recolor_map, route, fill_enclosed, project_ray) and grow.
3. Same tripwire/promotion contract: a DSL program train-exact + fold-varying-LOO on a renderer-14 -> HALT for joint
   verification -> port the compiled transform behind a disabled flag -> frozen + 120/120 public guard -> enable iff
   green. Claude never touches the live solver.
