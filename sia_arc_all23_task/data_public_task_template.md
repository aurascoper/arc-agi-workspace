# ARC2 All-23 Quarantined Program-Synthesis Task

You are improving a Python target agent for a quarantined ARC-AGI-2 research
task. The target agent must propose deterministic grid transforms from training
pairs only.

## Data

At runtime SIA passes:

- `--dataset_dir`: a read-only directory containing public JSON task files.
- `--working_dir`: a writable generation directory.

Each public task JSON contains:

```json
{
  "train": [{"input": [[...]], "output": [[...]]}],
  "test": [{"input": [[...]]}]
}
```

The public files do not contain test outputs.

## Agent Contract

Your `target_agent.py` must:

1. Define `propose(train) -> list[(name, transform)]`.
2. Each `transform(grid)` returns a grid.
3. Learn only from the `train` pairs passed to `propose`.
4. Accept SIA CLI arguments:
   `--dataset_dir <path> --working_dir <path>`.
5. Write a valid `agent_execution.json` in the working directory.

## Fitness

The evaluator imports `target_agent.py` and scores hidden-safe evidence:

- train-exact candidates;
- non-vacuous same-name informative LOO, where the re-derived transform changes
  across folds;
- cross-task firing where the same candidate name is train-exact on at least two
  tasks;
- leakage penalties for task-ID dispatch, private-data reads, output templates,
  raw evaluation-tree access, and public-signature replay.

Held-out private test matches are logged for humans but never added to fitness.

## Current Baseline

The strong seed has two train-exact apex-ray candidates on `3dc255db`, but both
are fixed/vacuous and fail held-out readout. They are not promotion evidence.

The highest-value search direction is the renderer cluster: richer overlay/draw
vocabulary such as stamp, ray, bracket routing, flood-fill region, scale-blit,
symmetry completion, panel serialization, and relational shape generation.

Do not touch files outside the SIA generation working directory.
