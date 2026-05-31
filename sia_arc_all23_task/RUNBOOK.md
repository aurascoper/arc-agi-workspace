# ARC2 All-23 SIA Runbook

This task is a quarantined SIA target for the 23 current ARC2 design misses.
It must not edit the live Kaggle solver, notebooks, `kaggle_modules/`, or
submission helpers. Generated agents are evidence sources only.

## Build The Public/Private Split

From the workspace root:

```bash
ARC2_EVAL_DIR=/Users/aurascoper/Developer/arc_agi/workspace/arc_agi_2_data/evaluation \
  python3 sia_arc_all23_task/build_task.py
```

Public JSON files contain train pairs plus test inputs only. Private outputs are
for evaluator log-only readout and are never part of fitness.

## Smoke The Reference Agent

```bash
rm -rf /tmp/sia_all23_gen_smoke
mkdir -p /tmp/sia_all23_gen_smoke
cp sia_arc_all23_task/reference/reference_target_agent.py /tmp/sia_all23_gen_smoke/target_agent.py
python3 /tmp/sia_all23_gen_smoke/target_agent.py \
  --dataset_dir "$PWD/sia_arc_all23_task/data/public" \
  --working_dir /tmp/sia_all23_gen_smoke
python3 sia_arc_all23_task/evaluate.py --gen-dir /tmp/sia_all23_gen_smoke
python3 arc2_sia_all23_sentinel.py
```

Expected baseline: leakage clean, `fitness=0.1`, two train-exact fixed/vacuous
apex-ray candidates on `3dc255db`, `loo_tasks=0`, `cross=0`, and
`integration_ready=[]`.

## Run SIA

Install SIA in an isolated environment. Pick exactly one backend.

```bash
python3 -m venv /tmp/arc2_sia_venv
. /tmp/arc2_sia_venv/bin/activate
pip install 'sia-agent[openhands]'
```

OpenHands backend example:

```bash
sia \
  --task_dir ./sia_arc_all23_task \
  --max_gen 10 \
  --run_id arc2_all23_001 \
  --backend openhands \
  --meta_model "openai/gpt-4" \
  --task_model "openai/gpt-4"
```

Claude backend example:

```bash
pip install 'sia-agent[claude]'
sia \
  --task_dir ./sia_arc_all23_task \
  --max_gen 10 \
  --run_id arc2_all23_001 \
  --backend claude \
  --meta_model sonnet
```

SIA writes generations to `runs/run_<run_id>/gen_<n>/` relative to the launch
directory. The Codex sentinel scans both workspace-root `runs/` and
task-local `sia_arc_all23_task/runs/`.

## Run SIA-Lite

If the full SIA/OpenHands backend is unavailable, use the local SIA-lite harness.
It calls the OpenAI Chat Completions API directly, writes the same
`runs/<run_id>/gen_<n>/target_agent.py` layout, gates with `py_compile` and the
existing leakage scan, then scores with `evaluate.py`.

Dry-run the seed without making an API call:

```bash
python3 sia_arc_all23_task/sia_lite_harness.py \
  --run-id sia_lite_smoke \
  --dry-run
```

Run a bounded mutation loop:

```bash
python3 sia_arc_all23_task/sia_lite_harness.py \
  --run-id sia_lite_arc2_001 \
  --model gpt-4.1-mini \
  --temperature 0.8 \
  --max-gen 8
```

If the OpenAI key returns `insufficient_quota`, the harness records a
`generation_error` result and leaves the seed score intact.

## Promotion Contract

A generated agent is only worth Codex integration work if the sentinel reports:

- `loo_tasks >= 1`, meaning a fold-varying informative-LOO family exists; or
- `cross >= 1`, meaning at least one candidate name is train-exact on two or more
  public tasks.

If that happens, port only that one family into `arc2_candidate_solver.py` behind
a disabled flag, then run frozen design/calibration plus the public 120/120
guard before enabling it. Weak train-exact credit alone is not promotion
evidence.
