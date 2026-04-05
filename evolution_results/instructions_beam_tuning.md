# Autoresearch Instructions — Beam Search Blending Parameter Tuning

> The evolution loop is at ceiling on tier 1+2 (base_score ≥ 0.999). Selection pressure now comes from tier 3 solve accuracy via blending. The blending formula and task count were never empirically validated — this round finds the optimal configuration.

## Goal

You are an autonomous research agent. Your job is to **maximize the blended beam search score by tuning SOLVE_WEIGHT and SOLVE_TASKS**. You will:

1. Read the current state of `beam_search_local.py`
2. Form a hypothesis about which parameter values might improve the blended score
3. Change ONLY `SOLVE_WEIGHT` and `SOLVE_TASKS` in `beam_search_local.py`
4. Run the eval script
5. If the score improved by ≥ 0.005: **keep the change and commit**
6. If the score did not improve: **revert and try something different**
7. Repeat

## System Context

`beam_search_local.py` optimizes `dsl.py` (822 helper functions) by generating mutant DSL functions via LLM, evaluating them via `benchmark_dsl.py` (tier 1+2), and when base_score ≥ 0.999, blending in a tier 3 mini-solve score. The blending formula (line 531):
```
blended = base_score * (1 - SOLVE_WEIGHT) + solve_score * SOLVE_WEIGHT
```
`_mini_solve_eval()` samples SOLVE_TASKS random training tasks, generates solutions at temp=0.4, and returns average pixel accuracy.

## Rules — READ THESE FIRST

### What you CAN modify
- `beam_search_local.py` — this is the ONLY file you may edit.

Specifically, these are the tunable levers:
1. Line 411: `SOLVE_TASKS = 3` — try values in {2, 3, 5, 8}. Each extra task adds ~40s to beam search eval time.
2. Line 412: `SOLVE_WEIGHT = 0.3` — try values in {0.1, 0.2, 0.3, 0.4, 0.5}. Controls how much tier 3 solve accuracy influences candidate selection.

Do NOT modify any other lines in beam_search_local.py. Do NOT modify the `_mini_solve_eval()` function body, the `evaluate_candidate()` function body, or the `BeamConfig` class.

### What you CANNOT modify
- `eval_beam_tuning.py` — the evaluation script is sacred. Never touch it.
- `dsl.py` — the DSL being evolved. Never touch it.
- `target_mlx_arc.py` — the inference backend. Never touch it.
- `evolve_qwen_arc.py` — the outer evolution loop (currently running as PID 71133).
- `benchmark_dsl.py` — the tier 1+2 benchmark. Never touch it.
- Do NOT change `config.temperature` (that's a separate experiment).
- Do NOT set SOLVE_TASKS > 10 (each task costs ~40s in LLM generation).

### Guard metric
- **Guard metric:** base_score (benchmark tier 1+2 score)
- **Guard threshold:** ≥ 0.999
- **Rule:** If the primary score improves but any beam search run produces base_score < 0.999, **discard the change**. Log it as `guard_fail`.

### Min-delta threshold
- Only count a change as an improvement if the SCORE increases by more than **0.005**.
- Changes within 0.005 are noise from random task sampling in `_mini_solve_eval()`. Discard them.

### Commit discipline
- **Commit after every improvement** with a message: `autoresearch: SOLVE_WEIGHT=X SOLVE_TASKS=Y | score: X.XXX -> Y.YYY | +Z.ZZZ`
- **Revert failed experiments** cleanly: `git checkout -- beam_search_local.py`
- **Log every iteration** to `autoresearch.jsonl`
- **Update `autoresearch_dashboard.md`** after every iteration

### Iteration budget
- Run **30 iterations** unless told otherwise.
- Each iteration takes ~6 minutes (3 beam search runs × ~2 minutes each). If an iteration exceeds 15 minutes, something is wrong — stop and report.
- After every 10 iterations, write a progress summary to `autoresearch_dashboard.md`.

### State tracking

Log every iteration to `autoresearch.jsonl`. Format:
```json
{"type": "result", "iteration": 0, "commit": "sha", "score": 0.8650, "delta": "+0.000", "guard_score": 1.0, "guard_pass": true, "status": "baseline", "description": "SOLVE_WEIGHT=0.3 SOLVE_TASKS=3", "timestamp": "ISO8601"}
```

## Eval

```bash
python evolution_results/eval_beam_tuning.py --verbose
```

**SCORE = median blended score across 3 beam search runs**

- Primary: median of `result.score` from 3 `run_beam_search()` calls with different seeds
- Guard: minimum `base_score` across all runs must be ≥ 0.999
- Baseline (current): approximately **0.865** (depends on which random tasks are sampled)

## The Blending System (what you're optimizing)

1. **Step 1** (frozen): Benchmark DSL → `base_score` (0.0–1.0, tier 1+2)
2. **Step 2** (frozen): Run correctness tests → pass/fail
3. **Step 3** (frozen): Check ceiling: `if base_score >= 0.999:`
4. **Step 4** (tunable): Sample SOLVE_TASKS random training tasks
5. **Step 5** (tunable): Compute `solve_score` = average pixel accuracy on sampled tasks
6. **Step 6** (tunable): Blend: `blended = base_score * (1 - SOLVE_WEIGHT) + solve_score * SOLVE_WEIGHT`

## Strategy Guidance

### Quick wins (iterations 1-5)
- Establish baseline: run eval with current SOLVE_WEIGHT=0.3, SOLVE_TASKS=3
- Test SOLVE_TASKS=5 (keeps weight same, reduces variance with more samples)
- Test SOLVE_WEIGHT=0.4 (keeps tasks same, stronger selection pressure)

### Main optimization (iterations 6-20)
- If more tasks helped → try SOLVE_TASKS=8 (most representative, but slower)
- If higher weight helped → try SOLVE_WEIGHT=0.5 (equal weight to base and solve)
- Test best weight × tasks combination
- Consider: SOLVE_WEIGHT=0.2 + SOLVE_TASKS=5 (lighter pressure but more signal)
- The tradeoff: more tasks = less noise but more time. Higher weight = more tier 3 pressure but less stability.

### Experimental (iterations 21-30)
- Test extremes: SOLVE_WEIGHT=0.1 (minimal pressure) vs SOLVE_WEIGHT=0.5 (maximum)
- SOLVE_TASKS=2 vs SOLVE_TASKS=8 — is the noise floor dominated by task count or LLM variance?
- If plateaued, document the optimal configuration and why

### Do NOT:
- Change the `_mini_solve_eval()` or `evaluate_candidate()` function body
- Change `config.temperature` (separate experiment)
- Set SOLVE_TASKS > 10 (makes beam search too slow for the evolution loop's ~120s time budget)
- Spend more than 3 consecutive iterations on the same parameter combination — if it's noisy, the signal isn't there

## When You're Done

Write a final summary to `autoresearch_dashboard.md`:

1. **Starting score** and **final score**
2. **Top 3 changes** that had the biggest impact (with specific numbers)
3. **What didn't work** and why
4. **Diminishing returns:** where did the score plateau? What's the likely ceiling?
5. **Recommended configuration** — the SOLVE_WEIGHT and SOLVE_TASKS to commit permanently

Then stop. Do not start a new round without human review.
