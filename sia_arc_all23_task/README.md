# SIA Custom Task — ARC All-23 Design Misses

This is a quarantined all-23 follow-up to `sia_arc_shape_task/`.

It stages the 23 current genuine design misses for SIA using the same safety discipline:

- `data/public/<tid>.json` contains train pairs plus test inputs only.
- `data/private/<tid>.json` contains held-out outputs for evaluator log-only readout.
- Fitness is delegated to the hardened shape-task evaluator: train exactness, non-vacuous same-name LOO, cross-task firing, and leakage penalties.
- Private readout is never part of fitness.
- Live solver files remain out of scope.

See `RUNBOOK.md` for the exact build, smoke, SIA launch, and promotion-gate
commands.

Build data:

```bash
ARC2_EVAL_DIR=/path/to/arc_agi_2_data/evaluation python3 build_task.py
```

`build_task.py` also writes SIA's required `data/public/task.md` from
`data_public_task_template.md`.

Evaluate the strong seed:

```bash
python3 evaluator.py --agent ../sia_arc_shape_task/strong_seed_agent.py
```

SIA-compatible smoke:

```bash
python3 reference/reference_target_agent.py \
  --dataset_dir "$PWD/data/public" \
  --working_dir /tmp/sia_all23_gen_smoke
python3 evaluate.py --gen-dir /tmp/sia_all23_gen_smoke
```

Expected baseline as of 2026-05-30: one train-exact fixed/vacuous apex-ray candidate on `3dc255db`, zero informative LOO, zero flips, and no integration-ready agent.
