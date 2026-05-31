# Relational DSL spec v0.2 — design-only (Claude-owned), revised after expert review + branch inventory

## What changed in v0.2 (and why)
Review + the `search-comparison` benchmark forced one HEADLINE change and six fixes.
- HEADLINE — GENERATOR PIVOT: `search-comparison` found **enumerative BFS + library-learning** had the best mean
  performance on the 14 tasks, beating LLM-emits-DSL-program. So the LLM is NOT the program author. The engine is
  ENUMERATION over the typed DSL + `param-refit` (LOO grid-search/CMA-ES) + DreamCoder-style library learning; the
  LLM (if used at all) is only a neural-guided PRIORITY function over the BFS frontier. This also explains our own
  result: free-form-Python LLM mutation failed, and per the benchmark even LLM-emit-DSL underperforms enumeration.
- Six fixes from review: (1) add a variable-template COPY op; (2) draw ops are strict no-ops on empty targets;
  (3) richer relational selection predicates; (4) richer parser views; (5) constrain the filter/trigger fitter
  language (no arbitrary predicates); (6) start the op-set at 4 and grow.

Evidence recap: task-conditioned free-form-Python LLM (one-shot + hill-climb, gpt-4.1-mini/4.1) fit 0/14 renderer
tasks to train-exact (flat diffs 51/50/71/110/745). Bottleneck = REPRESENTATION + SEARCH METHOD, not model strength.
Programs gate IDENTICALLY through the existing `evaluator.py` (train-exact + name-stable fold-varying LOO; readout
log-only; leakage scan).

## 1. Typed values
`Grid`(=Image) · `ObjSet` · `Obj` · `Region` · `Marker` · `Color` · `Dir`(4/8) · `Int` · `Bool` ·
`RelationGraph` · `AnchorPath`. (Aligns with the `dsl-v0.2-relational` branch types Image/Object/RelationGraph/
AnchorPath.) Every op is typed; ill-typed compositions rejected at compile time.

## 2. Parser primitives  (Grid -> values; pure, no params)
- `objects(view)` view ∈ {color, ignore_color, **connected**, **multicolor**, rectangles, frames, lines, holes,
  panels} — added `connected` (4-conn ignoring a learned colour set) and `multicolor` (all non-bg as one object) per
  review #4, for multicolour-template tasks.
- `markers()` · `enclosed_regions()` · `panels()` · `bands(sep_color)` · `rails(color)` · `background()`
- `relation_graph(objset)` -> RelationGraph (RCC-8 / distance / containment / alignment edges — REUSE the
  `object-selectors` branch extractors; do NOT reimplement).

## 3. Selection / filter  (value -> value; params LEARNED from train)
- `filter(objset, pred)` pred ∈ {size==k, size_rank==r, color==c, shape==template, touches(role), los_to(role),
  unique_shape, in_region(R), **symmetry_partner_of(obj)**, **connected_component_with(marker)**, **on_rail(rail)**}
  — the three bold predicates added per review #3; all sourced from the `object-selectors` branch (symmetry-partner
  matcher, LOS path membership, RCC-8). HOLES (k/r/c/template/obj) fit on train.
- `select(objset, role)` role ∈ {largest, smallest, unique_color, by_count_rank=r}
- `anchor(objset)` -> Marker/Obj (distinguished element; centroid if no degree<=1 cell exists)

## 4. Generative / draw ops  (each pure `Grid -> Grid`; STRICT NO-OP on empty target set, per review #2)
- `recolor_map(grid, {c_in:c_out})`            — global colour map (may be many-to-one; learned)
- `route(grid, A, B, color, mode)`             — connect A,B (markers/objs/centroids) sharing row/col/diag
- `fill_enclosed(grid, regions, color|rule)`   — fill enclosed regions; const or enclosing-colour rule
- `project_ray(grid, src, dir, color, stop)`   — rays; stop ∈ {border, first_nonbg, **until_color(c)**, len=k}
  (added `until_color` per review #5b)
- `bbox_fill(grid, objset, color)`             — fill bounding box of selected objects
- `symmetry_complete(grid, axis)`              — mirror/rotate-complete; axis learned
- `recolor_by_template(grid, objset, map)`     — objects matching a learned (D4-canonical polyomino) template -> colour
- `move_to_anchor(grid, objset, anchor, along=rail)` — translate objects toward anchor along a guide line
- `stamp(grid, markers, template)`             — paint a learned FIXED NxN template at each marker
- **`copy_object(grid, src_region_or_obj, [markers])`** — extract the CURRENT-GRID content of a selected
  source object/region and paint it at each marker. This is the variable-template primitive from review #1
  (= MindsAI `copyObject` / the `dsl-v0.2-relational` `place_n_cells_by_rule` family). `stamp` = constant template;
  `copy_object` = input-dependent template. BOTH are needed.
A program is a PIPELINE of these (left-to-right). Empty-target no-op makes unconditional pipelines emulate
"if object exists then act" without an explicit conditional (review #2).

## 5. Program format + fitters
A JSON pipeline of typed op-calls; HOLES `{"learn": key}` fit ONLY from train; inconsistent fit across pairs ->
program rejected (prevents overfit). Example:
```json
{"name":"recolor+place_cells",
 "pipeline":[{"op":"recolor_map","args":{"map":{"learn":"color_bijection"}}},
             {"op":"fill_enclosed","args":{"regions":{"op":"enclosed_regions"},
                                           "color":{"learn":"enclosing_or_const"}}}]}
```
- `name` = op-STRUCTURE signature with params abstracted -> NAME-STABLE across folds.
- Fitters (REUSE the `param-refit` branch: LOO grid-search / CMA-ES over colour constants, coordinates, ints):
  `color_bijection`, `enclosing_or_const`, ray-`len/until_color`, template (D4-canonical polyomino), axis, anchor.
- CONSTRAINED TRIGGER FITTERS (review #5): a learned filter/trigger predicate is NOT arbitrary code — it is chosen
  from a fixed parametric family, e.g. `band/region contains exactly N cells of colour C`, `count(objset)==k`,
  `non_empty`, `has_color(c)`. The fitter outputs (family_id, params); anything outside the family is unrepresentable.

## 6. Gate contract (identical to today)
- A reference interpreter (`sia_arc_all23_task/dsl_interpreter.py`, design-only, stdlib-only, quarantine dir, NEVER
  imported by live solver) compiles pipeline+fitted-params -> `propose(train) -> [(name, transform)]`.
- NAME-STABLE: drop a train pair -> re-fit -> SAME name. FOLD-VARYING: learned params re-fit per fold so the
  fingerprint differs -> earns `informative_loo`, not `train_exact_fixed_loo_vacuous`. (A perfectly fold-invariant
  param-free program scores loo=0 and is NOT promoted — accepted: we'd rather miss a trivial recolor than risk a
  leak. Such a program may still earn promotion via cross>=2.)
- LEAKAGE IMPOSSIBLE BY CONSTRUCTION: emission is op-names + learn-keys only; no file/grid-literal/task-id is
  representable. Existing leakage scan still runs (defense-in-depth). Strict JSON parse: unknown keys -> reject.
- Readout LOG-ONLY; tripwire (loo_tasks>=1 OR cross>=2) unchanged.

## 7. GENERATOR STRATEGY (the v0.2 headline — per `search-comparison`)
Ranked by the benchmark's mean performance on the 14 tasks:
1. **Enumerative BFS + library-learning (PRIMARY).** Iterative-deepening over typed op-pipelines (depth 1->3),
   type-directed so only well-typed continuations are expanded; after each train-exact skeleton, run `param-refit`
   (LOO) to instantiate constants; DreamCoder-style: abstract recurring 2-3-op sub-pipelines into named library ops
   and re-enumerate with the grown library (this is what won).
2. **Neural-guided priority queue (SECONDARY).** A small LM scorer orders the BFS frontier (which op to try next
   given the train diff). The LLM's role is PRIORITY, not authorship.
3. **LLM-emits-DSL-program (TERTIARY / ablation).** Keep as a baseline only; the benchmark says it underperforms (1).
4. **CEGIS** as a fallback for tasks where a counterexample-guided constraint loop fits param-heavy skeletons.
START SMALL (review #6): op-set = {recolor_map, route, fill_enclosed, project_ray}; verify the enumerator hits
2-3-step pipelines on the easiest residual before growing the op-set.

## 8. Reconciliation with existing branches (do NOT duplicate)
- `dsl-v0.2-relational`: this spec's ops map onto its primitives (match_template≈recolor_by_template,
  flood_trigger≈fill_enclosed+trigger, move_object_to_anchor_along_rail≈move_to_anchor, place_n_cells_by_rule≈
  copy_object/fill, select_by_symmetry_partner≈filter symmetry_partner_of). Treat `dsl-v0.2-relational` as the impl
  home; this file is the contract/spec it should satisfy.
- `object-selectors`: provides §3's relational predicates (RCC-8, distance, containment, LOS, symmetry-partner,
  key-template). The DSL `filter`/`relation_graph` CALL these — no reimplementation.
- `param-refit`: provides §5's fitters (LOO grid-search / CMA-ES). The interpreter's `{"learn"}` keys dispatch here.
- `search-comparison`: dictates §7 ranking (enumerate+library-learn primary). Re-run it after any op-set change.

## 9. Wiring + tripwire (Codex lane, when ready)
1. `dsl_interpreter.py` (Claude, quarantine): op registry + fitter dispatch (-> `param-refit`) + `compile`.
2. `enumerate_dsl.py` (Codex or Claude): type-directed BFS + library learning over the op registry; scores each
   compiled program through the SAME `evaluate.py`; optional LM frontier scorer.
3. Same promotion contract: a DSL program train-exact + fold-varying-LOO (or cross>=2) on a renderer-14 -> HALT for
   joint verification -> port the compiled transform behind a disabled flag -> frozen + 120/120 public guard ->
   enable iff green. Claude never touches the live solver.
