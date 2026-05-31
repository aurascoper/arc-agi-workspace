# Claude SIA Next Prompt — Choose A First

Recommendation: do **A first**, not B.

Reason: the 7-task shape/decomposition SIA sandbox is already tight, validated, and low-blast-radius. Enriching `reference_agent.py` with more re-derivable seed families improves SIA's search gradient without expanding the evaluator surface. Generalizing to all 23 should wait until the narrow sandbox either produces a positive train-exact/informative-LOO signal or cleanly falsifies the stronger seed family set.

## Immediate Task

Inside `sia_arc_shape_task/`, enrich `reference_agent.py` with general, train-derived families only. Do not touch live solver files.

Candidate seed families:

- `object_summary_by_count`: render compact row/column/table summaries where dimensions derive from object counts, color-role counts, or component counts.
- `separator_serialize`: detect separator/panel structures, serialize panel-local glyphs or color roles into an output canvas.
- `color_histogram_table`: render counts or ordered color roles into a compact table when train output dimensions match.
- `compact_glyph_table`: extract non-background glyphs, normalize bbox, and pack them by reading order or learned train-derived ordering.
- `panel_local_summary`: summarize each panel into one cell/row/glyph using train-derived panel roles.
- `bar_length_shape`: infer output height/width from bar/line lengths or counts of same-color runs.

## Gates

After every change:

```bash
python3 -m py_compile sia_arc_shape_task/reference_agent.py sia_arc_shape_task/evaluator.py
python3 sia_arc_shape_task/evaluator.py --agent reference_agent.py --json
```

Also re-run an adversarial check if evaluator code changes.

The evaluator now requires same-name/family informative LOO: a candidate only receives LOO credit if the same candidate name is re-derived on every leave-one-out fold. Do not weaken that.

## Promotion Criteria

Report any positive result with:

- candidate name/family
- which tasks are train-exact
- same-name informative LOO status
- cross-task firing count
- synthetic invariance status if applicable
- private readout, explicitly log-only
- leakage hits

Do not edit or request edits to:

- `arc2_candidate_solver.py`
- `submission_helper.py`
- `kaggle_modules/`
- notebooks

Codex will independently port and verify only if a family clears the evidence gates.

## When To Do B

Only after A:

- if A gets a positive signal, port the same evaluator discipline to all 23;
- if A cleanly returns zero again, generalize to all 23 only to evolve marker-host/routing/render families, with the same private-log-only rule and same-family LOO.
