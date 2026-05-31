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

The remaining misses are mostly construction problems, not object classification
problems. Favor small reusable renderer/decomposition families over per-task
patches:

- overlay/draw programs: stamp, ray, bracket routing, endpoint bridging,
  flood-fill region, scale-blit, symmetry completion;
- decomposition programs: panel serialization, separator-driven crop/stack,
  object-summary rendering, compact glyph extraction;
- relational programs: bind marker/host/anchor roles from train pairs, then draw
  or move structure using those roles.

Known walls to avoid over-spending on:

- `dd6b8c4b`: local component-graph marker selection is not separable with the
  current parser-bank features.
- `3dc255db`: the apex-ray abstraction is train-exact but fixed/vacuous; it needs
  a genuinely re-derived host direction/endpoint parser or cross-task evidence.

Positive fitness requires either a fold-varying informative-LOO family on at
least one task or a candidate name that is train-exact on at least two tasks.
Weak train-exact credit alone is not enough for promotion.

Do not touch files outside the SIA generation working directory.
