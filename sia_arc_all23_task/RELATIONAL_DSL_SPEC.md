# Relational DSL spec v0.3 — design-only (Claude-owned)

## v0.3 changelog — RETRACTION + hardening
v0.2 was contaminated by a fabricated "branch inventory + literature survey" that arrived as text. RETRACTED here:
- The claim that a `search-comparison` branch BENCHMARKED enumerate-BFS > LLM-emit-DSL (9/14 etc.). No such measured
  result exists. The "generator pivot" must NOT cite it.
- The "branch reconciliation" to `object-selectors` / `param-refit` / `dsl-v0.2-relational` as verified existing code.
  Treat those as components TO BUILD, not assume-existing.
- The "MindsAI example-parameter refinement" provenance (paper/repo/arXiv do not exist). The technique (abstract
  params out of the program name, refit per fold, reject if inconsistent) is REAL and is what this spec already does;
  it just has no such named source.
What survives unchanged: our OWN measured evidence (task-conditioned free-form-Python LLM fit 0/14 renderer tasks,
flat diffs) and our hand-probes of the real grids `7b0280bc`/`cb2d8a2c`/`d8e07eb2`/`88bcf3b4` (all relational/global
cores). Those were run locally on `arc_agi_2_data/evaluation` and are trustworthy.
NEW in v0.3 (from independent review): fitter-as-leak-surface contract (§5b), derived-integer hole family (§5c),
`extract`/`stamp_dynamic` instead of a hole-breaking `transfer_pattern` (§4), empty-selection vs inconsistent-fit
distinction (§6), and "spend op budget on SELECTORS before generative ops" (§3).

## Real grounding (to be verified by the planned research run — do NOT treat as settled)
- Our measured result: free-form-Python LLM mutation = 0/14 train-exact (one-shot + hill-climb). This is real.
- Direction supported by genuine literature (verify exact claims/IDs before quoting): BARC "Combining Induction and
  Transduction for Abstract Reasoning" (induction track) ~arXiv:2411.02272; DreamCoder (wake-sleep LIBRARY LEARNING +
  enumeration); CEGIS (counterexample-guided hole-filling); Hodel `github.com/michaelhodel/arc-dsl` whose REAL
  primitives are fill/paint/underfill/recolor/connect/shoot/gravitate over Grid/Object/Patch/Indices.
- OPEN QUESTION (do not assert): does enumeration+library-learning beat LLM-emit-DSL on OUR residual? We have NOT
  measured this. Plan: build both and run our OWN comparison before committing. The only thing our data licenses is
  "free-form-Python LLM author is insufficient" — not "enumeration wins."

## 1. Typed values
`Grid` · `ObjSet` · `Obj` · `Region` · `Marker` · `Color` · `Dir`(4/8) · `Int` · `Bool` · `RelationGraph` ·
`Template` (a concrete cell-mask + colours, possibly produced at runtime — see §4). Every op typed; ill-typed
compositions rejected at compile time.

## 2. Parser primitives (Grid -> values; pure, no params)
`objects(view)` view ∈ {color, ignore_color, connected, multicolor, rectangles, frames, lines, holes, panels} ·
`markers()` · `enclosed_regions()` · `panels()` · `bands(sep_color)` · `rails(color)` · `background()` ·
`relation_graph(objset)` (RCC-8 / distance / containment / alignment edges).

## 3. Selection / filter (value -> value)  — PRIORITIZE THESE over new generative ops
Our hand-probes say the hard part is WHICH object/region is acted on, not HOW it's drawn. Spend the op budget here.
- `filter(objset, pred)` pred ∈ {size==k, size_rank==r, color==c, shape==template, touches(role), los_to(role),
  unique_shape, in_region(R), symmetry_partner_of(obj), connected_component_with(marker), on_rail(rail)}
- `select(objset, role)` role ∈ {largest, smallest, unique_color, by_count_rank=r}
- `anchor(objset)` -> Marker/Obj (centroid if no degree<=1 cell)

## 4. Generative / draw ops (each pure `Grid -> Grid`; STRICT NO-OP on empty target set)
- `recolor_map(grid, {c_in:c_out})` · `route(grid, A, B, color, mode)` · `fill_enclosed(grid, regions, color|rule)` ·
  `project_ray(grid, src, dir, color, stop)` stop ∈ {border, first_nonbg, until_color(c), len=k} ·
  `bbox_fill(grid, objset, color)` · `symmetry_complete(grid, axis)` ·
  `recolor_by_template(grid, objset, map)` · `move_to_anchor(grid, objset, anchor, along=rail)` ·
  `stamp(grid, markers, template)` — `template` is a LEARNED CONSTANT mask (a value-hole; same across all examples).
- VARIABLE-TEMPLATE (input-dependent) — split into two ops so "holes are VALUES" stays invariant (review override of
  attachment-5's `transfer_pattern`, whose source-region selector is NOT a value):
  - `extract(grid, region_or_obj) -> Template`  — pure runtime dataflow; NO hole. The region/obj is produced by §3
    selection ops upstream in the pipeline.
  - `stamp_dynamic(grid, template, objset) -> Grid` — paints the dataflow `Template` at each target; NO learned
    template hole. The template arrives by dataflow, not by fitting.
  This keeps every `{"learn": key}` a concrete typed VALUE; a runtime-selected source is expressed by op composition.

## 5. Holes, fitters, and the fitter contract
A program is a JSON pipeline; HOLES `{"learn": key}` are fit ONLY from train; inconsistent fit -> REJECT candidate.
`name` = op-structure with params abstracted -> NAME-STABLE; learned params re-fit per fold -> FOLD-VARYING.

### 5a. Hole value types
`Color`, `Int`, `Dir`, `Template`(constant mask), `colour-map`, `axis`, `predicate-from-fixed-enum`.

### 5b. FITTER CONTRACT (the real leak surface — review's key catch)
The JSON can't encode grid literals/task-ids, but each fitter is code with full read access to train pairs, so a
SLOPPY fitter is the leak. Hard contract for the closed, audited fitter registry:
- INPUT: the list of train pairs only. OUTPUT: a single typed value (§5a) — never arbitrary code, never a closure
  over a specific task.
- FORBIDDEN: hashing grids, branching on grid-size constants, any per-task lookup table, anything that could encode
  task identity. A fitter that is train-exact + fold-stable by MEMORIZING must be impossible to write within the
  contract.
- TESTS (per fitter): (i) recovers known params on synthetic pairs; (ii) rejects inconsistent pairs; (iii)
  ADVERSARIAL — two DIFFERENT synthetic tasks that share a rule must yield the SAME `name` and the fitter must return
  the correct (different) param for each. Test (iii) is what catches a memorizing fitter.

### 5c. DERIVED-INTEGER hole family (review's second catch — most likely silent failure on redraw tasks)
An `Int` hole (cells-to-place N, ray length, band count) is often a FUNCTION of the input, not a constant. A
grid-search over constant ints will overfit train then fail LOO/test. So an `Int` hole's fitter output space is:
`const=k` OR a DERIVED integer ∈ {count(objset), size(obj), width(obj), height(obj), n_colors(region),
distance(a,b)}. This is the integer analogue of `fill_enclosed`'s `enclosing_or_const` colour rule. The fitter
prefers a derived form that holds across ALL pairs over a constant that only fits by luck.

## 6. Gate contract (identical to today, with one sharpening)
- Reference interpreter `sia_arc_all23_task/dsl_interpreter.py` (design-only, stdlib-only, quarantine, NEVER imported
  by the live solver) compiles pipeline+fitted-params -> `propose(train) -> [(name, transform)]`.
- SHARPEN (review): distinguish two empty/inconsistent cases that the spec previously blurred —
  - EMPTY primary selection at RUNTIME -> the op is IDENTITY (no-op) for that grid. (Lets unconditional pipelines
    emulate "if exists then act".)
  - INCONSISTENT FIT across train folds -> the whole candidate is REJECTED (no candidate emitted). NOT a no-op.
    (Prevents a program looking train-exact-by-accident on folds where the selection happened to be empty.)
- NAME-STABLE + FOLD-VARYING as above -> `informative_loo`, not `train_exact_fixed_loo_vacuous`. Param-free
  fold-invariant programs score loo=0 and are not promoted unless cross>=2 (accepted).
- LEAKAGE: emission is op-names + learn-keys only (no file/grid-literal/task-id representable); the fitter contract
  (§5b) closes the second leak surface; existing leakage scan runs as defense-in-depth; readout LOG-ONLY; tripwire
  (loo_tasks>=1 OR cross>=2) unchanged.

## 7. Generator strategy (re-grounded — NO fabricated benchmark)
What our data licenses: free-form-Python LLM authorship is insufficient (measured). What it does NOT license: that
enumeration wins (unmeasured). So:
- BUILD a type-directed enumerator (iterative-deepening BFS over typed pipelines depth 1->3, well-typed
  continuations only) + `param-refit` fitters + DreamCoder-style library learning (abstract recurring sub-pipelines).
  Add an MDL / shortest-pipeline prior so a long pipeline can't win by memorization (pairs with the fold-varying gate
  to block overfit). [Direction supported by DreamCoder/CEGIS/BARC-induction — verify before quoting.]
- KEEP the LLM only as an optional neural-guided PRIORITY over the enumerator frontier, AND as an honest ABLATION
  baseline (LLM-emits-DSL) — so WE measure enumerate vs LLM-emit on our residual instead of asserting it.
- START at 4 ops {recolor_map, route, fill_enclosed, project_ray}; grow only after the enumerator hits a 2-3-step
  train-exact pipeline on the easiest residual task.

## 8. Components to BUILD (not assume-existing) + what the research run should verify
- BUILD: `dsl_interpreter.py` (Claude, quarantine) op registry + fitter dispatch + compile; `enumerate_dsl.py`
  (type-directed BFS + library learning) scoring via the SAME `evaluate.py`; the closed fitter registry (§5b);
  the param-refit fitters (LOO grid-search over §5a value spaces).
- VERIFY VIA RESEARCH (replace the fabricated survey): real primitive sets (Hodel's actual DSL), the actual 2024 ARC
  Prize results (BARC paper-award; verify arXiv:2411.02272), whether any published method actually compares
  enumeration vs LLM-program-emission on ARC, and DreamCoder/CEGIS as cited. Ground the survey against the REAL grids
  of `7b0280bc`/`cb2d8a2c`/`d8e07eb2` (available locally in `arc_agi_2_data/evaluation`).

## 9. Promotion (unchanged)
A DSL program train-exact + fold-varying-LOO (or cross>=2) on a renderer-14 -> HALT for joint verification -> port the
compiled transform behind a disabled flag -> frozen + 120/120 public guard -> enable iff green. Claude never touches
the live solver.

## 10. OP-GENERALITY CRITERION (added after the cb2d8a2c tripwire, 2026-05-31)
Observed failure mode: a complex op (`bar_marker_bracket_route`) hand-shaped to one task's geometry was TRAIN-EXACT on
cb2d8a2c but vacuous-LOO, cross=1, and structurally wrong on hidden (64-cell miss). This is the §5b leak-surface risk
realized in the OP layer — a disguised per-task solver. The gate (fold-varying-LOO OR cross>=2) rejected it, but the
DSL must not accumulate such ops. Criteria for an op to enter the PROMOTABLE search:
- NO MAGIC CONSTANTS: every integer/coordinate an op uses at runtime must be either a structural constant of the
  primitive (e.g. the 4 orthogonal directions) or a §5c learned/derived value — NOT a tuned offset like `min(3, ...)`.
  `enumerate_dsl.py` should statically flag ops whose source contains unexplained int literals and EXCLUDE them from
  the promotable frontier (they may stay as ablation/baseline only).
- GENERALITY GATE: an op contributes to promotion evidence only if a program using it is train-exact AND
  (fold-varying-LOO OR cross>=2). Train-exact-on-exactly-one-task via a task-shaped op counts as ZERO promotion
  evidence (same status as `train_exact_fixed_loo_vacuous`).
- PREFERENCE: decompose task-shaped renderers into GENERAL composable primitives (route, turn, project-to-rail,
  derived-margin) so the SEARCH—not the op author—discovers the task-specific composition. If no magic-constant-free
  composition is train-exact on a task, that task is representation-limited under the current op-set (park it; grow the
  primitive set deliberately, re-running the gate).
