# SIA custom task — ARC shape/decomposition research (QUARANTINED)

A tight, design-only SIA sandbox for evolving ARC shape/decomposition generators. **SIA runs only here.** It
never edits the live solver, and its held-out readout never feeds its fitness — so the self-improvement loop
is pushed toward genuine generalization, not eval-harness exploitation.

## Hard quarantine rules
- SIA may **only** read/write inside `sia_arc_shape_task/`. It mutates `target_agent.py` (seeded from
  `reference_agent.py`); it may add helper files in this dir.
- SIA must **NOT** touch: `arc2_candidate_solver.py`, `submission_helper.py`, `kaggle_modules/*`, the notebooks,
  or `data/private/`.
- Promotion into the live solver is a **separate manual Codex step**, gated on the evaluator's logged evidence.

## Data split
- `data/public/<tid>.json` — `{train, test:[{input}]}` (NO test outputs). The agent sees only this.
- `data/private/<tid>.json` — `{test_outputs}`. Held out; the evaluator uses it for a LOG-ONLY readout.
- Build it: `python3 build_task.py` (7 shape-change misses: 5dbc8537, edb79dae, 20a9e565, 2d0172a1,
  6ffbe589, e87109e9, 89565ca0).

## Agent contract
`target_agent.py` must define:
```python
def propose(train) -> list[(name: str, transform)]   # transform: grid -> grid, learned from TRAIN ONLY
```

## Fitness (what SIA maximizes — hidden-safe signals only)
The evaluator (`evaluator.py`) computes:
- `+1.0` per task with a **train-exact + informative-LOO** candidate (re-`propose()` on each n-1 subset must
  reproduce the held pair → genuine re-derivation, not a fixed/vacuous program),
- `+0.5·|tasks|` per candidate **name** that is train-exact on **≥2** public tasks (cross-task firing),
- `+0.1` per task with any train-exact candidate (weak partial credit),
- `−5.0` per **leakage** hit (task-id dispatch, reads of `data/private`, output templates, signature/replay),
- `−100` if the agent fails to import.

The **private (design-test) match is computed and LOGGED but NEVER added to fitness.** This is the safety
crux: SIA cannot win by exploiting the held-out outputs; it can only win by producing programs that are
train-exact AND re-derivable from subsets (the design-only admission protocol).

## Run
```bash
cd sia_arc_shape_task
python3 build_task.py
python3 evaluator.py --agent reference_agent.py        # baseline fitness + per-task evidence + private log
# then point SIA's evaluator at evaluator.py and its target template at reference_agent.py
```

## Why this is the safe immediate use
The target is **reusable infrastructure** (shape/decomposition generators), not a public-answer patch. The
7 targets currently have NO train-exact candidate (Claude's `arc2_shape_decomposition_synth.py` falsified all
5 baseline families; loci: 5dbc8537 = renderer, other 6 = data-dependent output shape). So a positive fitness
gain here means SIA discovered a genuinely new, re-derivable family — exactly what to promote, after Codex
re-runs the evaluator + strict/public guards.
