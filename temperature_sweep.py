#!/usr/bin/env python3
"""
temperature_sweep.py — Systematic temperature configuration experiment for ARC-AGI solvers.

Tests multiple temperature spreads across a fixed evaluation task set, measuring
pass_rate, mean_pixel_accuracy, best_candidate_rank, reflection_delta, and wall_time.

Usage:
  python temperature_sweep.py                    # full sweep (6 configs × 10 tasks × 3 reps)
  python temperature_sweep.py --validate          # quick validation (1 config × 1 task × 1 rep)
  python temperature_sweep.py --configs B C D     # run specific configs only
  python temperature_sweep.py --build-taskset     # build eval task set from 30 tasks at temp=0.0
"""

import argparse
import gc
import json
import os
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

import numpy as np

WORKSPACE = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKSPACE))

from target_mlx_arc import (
    build_prompt,
    build_reflection_prompt,
    build_task_hints,
    calculate_pixel_accuracy,
    call_model,
    extract_python_code,
    try_code_on_task,
)

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

NUM_CANDIDATES = 5
MAX_REFLECTIONS = 3

TEMP_CONFIGS = {
    "A": {"temps": [0.0, 0.35, 0.75], "label": "baseline (60% at 0.75)"},
    "B": {"temps": [0.0, 0.2, 0.4], "label": "conservative (cap 0.4)"},
    "C": {"temps": [0.0, 0.3, 0.5], "label": "moderate (cap 0.5)"},
    "D": {"temps": [0.0, 0.1, 0.3, 0.5], "label": "fine-grained (4 unique, 2/5 at max)"},
    "E": {"temps": [0.0, 0.15, 0.35, 0.6], "label": "wide-4 (one exploratory)"},
    "F": {"temps": [0.0, 0.1, 0.2], "label": "near-greedy (cap 0.2)"},
}

REFLECTION_MODES = {
    "same": "same as generation temp",
    "greedy": "fixed 0.1",
    "half": "0.5 × generation temp",
}

ARC_DATA_DIR = WORKSPACE / "arc_agi_2_data" / "training"
RESULTS_DIR = WORKSPACE / "evolution_results" / "temp_sweep"
TASKSET_PATH = RESULTS_DIR / "eval_taskset.json"
RESULTS_PATH = RESULTS_DIR / "sweep_results.json"

REPS = 3


# ---------------------------------------------------------------------------
# TASK SET BUILDING
# ---------------------------------------------------------------------------

def build_eval_taskset(num_probe: int = 30) -> dict:
    """Run NUM_PROBE tasks at temp=0.0 and bucket into 3 difficulty tiers."""
    task_files = sorted(ARC_DATA_DIR.glob("*.json"))
    if not task_files:
        print(f"[taskset] No tasks found in {ARC_DATA_DIR}")
        sys.exit(1)

    random.seed(42)
    sample = random.sample(task_files, min(num_probe, len(task_files)))

    results = []
    for tf in sample:
        td = json.loads(tf.read_text())
        prompt = build_prompt(td)
        hints = build_task_hints(td)

        code = extract_python_code(call_model(prompt, temperature=0.0))
        passed, failures = try_code_on_task(code, td)

        if passed:
            passed_test, test_failures = try_code_on_task(code, td, evaluate_on_test=True)
            if passed_test:
                acc = 1.0
            elif test_failures and len(test_failures[0]) >= 3 and test_failures[0][2] is not None:
                acc = calculate_pixel_accuracy(test_failures[0][1], test_failures[0][2])
            else:
                acc = 0.0
        else:
            acc = 0.0

        results.append({"task": tf.stem, "accuracy": acc})
        print(f"  {tf.stem}: {acc:.3f}")

    # Bucket into tiers
    results.sort(key=lambda r: r["accuracy"], reverse=True)
    easy = [r for r in results if r["accuracy"] >= 0.9][:3]
    medium = [r for r in results if 0.1 <= r["accuracy"] < 0.9][:4]
    hard = [r for r in results if r["accuracy"] < 0.1][:3]

    # Pad if tiers are short
    remaining = [r for r in results if r not in easy + medium + hard]
    while len(easy) < 3 and remaining:
        easy.append(remaining.pop(0))
    while len(medium) < 4 and remaining:
        medium.append(remaining.pop(0))
    while len(hard) < 3 and remaining:
        hard.append(remaining.pop(0))

    taskset = {
        "easy": [r["task"] for r in easy],
        "medium": [r["task"] for r in medium],
        "hard": [r["task"] for r in hard],
        "all": [r["task"] for r in easy + medium + hard],
        "baseline_scores": {r["task"]: r["accuracy"] for r in easy + medium + hard},
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    TASKSET_PATH.write_text(json.dumps(taskset, indent=2))
    print(f"\n[taskset] Saved {len(taskset['all'])} tasks to {TASKSET_PATH}")
    print(f"  Easy ({len(easy)}): {[r['task'] for r in easy]}")
    print(f"  Medium ({len(medium)}): {[r['task'] for r in medium]}")
    print(f"  Hard ({len(hard)}): {[r['task'] for r in hard]}")
    return taskset


def load_taskset() -> dict:
    if not TASKSET_PATH.exists():
        print("[sweep] No eval taskset found. Run with --build-taskset first.")
        sys.exit(1)
    return json.loads(TASKSET_PATH.read_text())


# ---------------------------------------------------------------------------
# SINGLE TASK EVALUATION
# ---------------------------------------------------------------------------

@dataclass
class EvalResult:
    config_id: str
    task_id: str
    rep: int
    pass_rate: float = 0.0
    pixel_accuracy: float = 0.0
    best_candidate_rank: int = -1
    reflection_delta: float = 0.0
    wall_time: float = 0.0
    reflection_mode: str = "same"


def get_reflection_temp(gen_temp: float, mode: str) -> float:
    if mode == "greedy":
        return 0.1
    elif mode == "half":
        return max(gen_temp * 0.5, 1e-6)
    else:  # "same"
        return gen_temp


def evaluate_task(
    config_id: str,
    temps: list[float],
    task_id: str,
    rep: int,
    reflection_mode: str = "same",
) -> EvalResult:
    """Evaluate one task with a given temperature config."""
    task_path = ARC_DATA_DIR / f"{task_id}.json"
    td = json.loads(task_path.read_text())
    prompt = build_prompt(td)
    hints = build_task_hints(td)

    start = time.monotonic()
    best_acc = 0.0
    best_rank = -1
    pre_reflection_accs = []
    post_reflection_accs = []

    for ci in range(NUM_CANDIDATES):
        gen_temp = temps[min(ci, len(temps) - 1)]
        ref_temp = get_reflection_temp(gen_temp, reflection_mode)

        code = extract_python_code(call_model(prompt, temperature=gen_temp))
        passed_train, failures = try_code_on_task(code, td)

        # Measure pre-reflection accuracy
        passed_test_pre, test_failures_pre = try_code_on_task(code, td, evaluate_on_test=True)
        if passed_test_pre:
            pre_acc = 1.0
        elif test_failures_pre and len(test_failures_pre[0]) >= 3 and test_failures_pre[0][2] is not None:
            pre_acc = calculate_pixel_accuracy(test_failures_pre[0][1], test_failures_pre[0][2])
        else:
            pre_acc = 0.0
        pre_reflection_accs.append(pre_acc)

        # Reflection loop
        for attempt in range(MAX_REFLECTIONS):
            if passed_train:
                break
            ref_prompt = build_reflection_prompt(td, code, failures, hints)
            code = extract_python_code(call_model(ref_prompt, temperature=ref_temp))
            passed_train, failures = try_code_on_task(code, td)

        # Measure post-reflection accuracy
        passed_test, test_failures = try_code_on_task(code, td, evaluate_on_test=True)
        if passed_test:
            post_acc = 1.0
        elif test_failures and len(test_failures[0]) >= 3 and test_failures[0][2] is not None:
            post_acc = calculate_pixel_accuracy(test_failures[0][1], test_failures[0][2])
        else:
            post_acc = 0.0
        post_reflection_accs.append(post_acc)

        if post_acc > best_acc:
            best_acc = post_acc
            best_rank = ci

    elapsed = time.monotonic() - start

    # Compute reflection delta (mean improvement from reflection)
    deltas = [post - pre for pre, post in zip(pre_reflection_accs, post_reflection_accs)]
    reflection_delta = sum(deltas) / len(deltas) if deltas else 0.0

    return EvalResult(
        config_id=config_id,
        task_id=task_id,
        rep=rep,
        pass_rate=1.0 if best_acc >= 1.0 else 0.0,
        pixel_accuracy=best_acc,
        best_candidate_rank=best_rank,
        reflection_delta=reflection_delta,
        wall_time=elapsed,
        reflection_mode=reflection_mode,
    )


# ---------------------------------------------------------------------------
# SWEEP RUNNER
# ---------------------------------------------------------------------------

def run_sweep(
    config_ids: list[str] | None = None,
    reps: int = REPS,
    reflection_mode: str = "same",
    validate: bool = False,
):
    """Run the full temperature sweep."""
    taskset = load_taskset()
    task_ids = taskset["all"]

    configs = {k: v for k, v in TEMP_CONFIGS.items() if config_ids is None or k in config_ids}

    if validate:
        first_config = next(iter(configs))
        configs = {first_config: configs[first_config]}
        task_ids = task_ids[:1]
        reps = 1
        print(f"[validate] Quick validation: config={first_config}, task={task_ids[0]}, reps=1")

    total = len(configs) * len(task_ids) * reps
    print(f"\n[sweep] {len(configs)} configs × {len(task_ids)} tasks × {reps} reps = {total} evals")
    print(f"[sweep] Reflection mode: {REFLECTION_MODES.get(reflection_mode, reflection_mode)}")

    all_results = []
    idx = 0

    for config_id, config in configs.items():
        temps = config["temps"]
        print(f"\n{'='*60}")
        print(f"Config {config_id}: {config['label']}")
        print(f"  Temps: {temps}")
        spread = [temps[min(i, len(temps) - 1)] for i in range(NUM_CANDIDATES)]
        print(f"  5-candidate spread: {spread}")
        print(f"{'='*60}")

        for task_id in task_ids:
            for rep in range(reps):
                idx += 1
                print(f"\n[{idx}/{total}] Config {config_id} | {task_id} | rep {rep+1}/{reps}")
                result = evaluate_task(config_id, temps, task_id, rep, reflection_mode)
                all_results.append(result)
                print(f"  acc={result.pixel_accuracy:.3f} rank={result.best_candidate_rank} "
                      f"refl_delta={result.reflection_delta:+.3f} time={result.wall_time:.1f}s")

                # Flush Metal cache between evaluations
                try:
                    import mlx.core as mx
                    gc.collect()
                    mx.clear_cache()
                except Exception:
                    pass

    # Save raw results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    raw = [vars(r) for r in all_results]
    RESULTS_PATH.write_text(json.dumps(raw, indent=2))
    print(f"\n[sweep] Raw results saved to {RESULTS_PATH}")

    # Aggregate
    _print_summary(all_results, configs)
    return all_results


def _print_summary(results: list[EvalResult], configs: dict):
    """Print per-config aggregate metrics."""
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"{'Config':<8} {'Label':<30} {'PassRate':>8} {'MeanAcc':>8} {'MedRank':>8} {'ReflDelta':>10} {'AvgTime':>8}")
    print("-" * 70)

    for config_id in configs:
        cr = [r for r in results if r.config_id == config_id]
        if not cr:
            continue
        pass_rate = sum(r.pass_rate for r in cr) / len(cr)
        mean_acc = sum(r.pixel_accuracy for r in cr) / len(cr)
        ranks = [r.best_candidate_rank for r in cr if r.best_candidate_rank >= 0]
        med_rank = median(ranks) if ranks else -1
        refl_delta = sum(r.reflection_delta for r in cr) / len(cr)
        avg_time = sum(r.wall_time for r in cr) / len(cr)

        print(f"{config_id:<8} {configs[config_id]['label'][:30]:<30} "
              f"{pass_rate:>8.3f} {mean_acc:>8.3f} {med_rank:>8.1f} {refl_delta:>+10.3f} {avg_time:>8.1f}s")

    # Per-task breakdown
    print(f"\n{'='*70}")
    print("PER-TASK BREAKDOWN (averaged across reps)")
    print(f"{'='*70}")
    task_ids = sorted(set(r.task_id for r in results))
    for task_id in task_ids:
        tr = [r for r in results if r.task_id == task_id]
        by_config = {}
        for r in tr:
            by_config.setdefault(r.config_id, []).append(r.pixel_accuracy)
        line = f"  {task_id}: "
        for cid in sorted(by_config):
            accs = by_config[cid]
            line += f" {cid}={sum(accs)/len(accs):.3f}"
        print(line)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Temperature sweep for ARC-AGI candidate generation")
    parser.add_argument("--validate", action="store_true", help="Quick 1-config 1-task 1-rep validation")
    parser.add_argument("--build-taskset", action="store_true", help="Build eval task set from 30 tasks")
    parser.add_argument("--configs", nargs="+", choices=list(TEMP_CONFIGS.keys()),
                        help="Run specific configs only (default: all)")
    parser.add_argument("--reps", type=int, default=REPS, help="Repetitions per config-task pair")
    parser.add_argument("--reflection-mode", choices=list(REFLECTION_MODES.keys()), default="same",
                        help="Reflection temperature mode")
    parser.add_argument("--tasks", type=int, help="Limit number of eval tasks")
    args = parser.parse_args()

    if args.build_taskset:
        build_eval_taskset()
    else:
        run_sweep(
            config_ids=args.configs,
            reps=args.reps,
            reflection_mode=args.reflection_mode,
            validate=args.validate,
        )
