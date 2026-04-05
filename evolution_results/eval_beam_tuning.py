#!/usr/bin/env python3
"""
eval_beam_tuning.py — Autoresearch eval script for SOLVE_WEIGHT/SOLVE_TASKS tuning.

Runs beam_search_local.py 3 times with different seeds, reports median blended score.
The autoresearch agent modifies only SOLVE_WEIGHT and SOLVE_TASKS in beam_search_local.py.

DO NOT MODIFY THIS FILE DURING AUTORESEARCH RUNS.

Usage:
  python evolution_results/eval_beam_tuning.py --verbose
"""

import importlib
import json
import os
import sys
import time
from pathlib import Path
from statistics import median

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

SEEDS = [12345, 67890, 24680]
GUARD_THRESHOLD = 0.999


def run_eval(verbose: bool = False, runs: int = 3):
    """Run beam search multiple times and report aggregate metrics."""
    # Re-import to pick up any changes to SOLVE_WEIGHT/SOLVE_TASKS
    if "beam_search_local" in sys.modules:
        importlib.reload(sys.modules["beam_search_local"])
    from beam_search_local import BeamConfig, run_beam_search, SOLVE_TASKS, SOLVE_WEIGHT

    print(f"[eval] SOLVE_WEIGHT={SOLVE_WEIGHT} SOLVE_TASKS={SOLVE_TASKS}")
    print(f"[eval] Running {runs} beam search evaluations...")

    scores = []
    base_scores = []
    times_list = []
    seeds = SEEDS[:runs]

    for i, seed in enumerate(seeds):
        config = BeamConfig()
        config._solve_seed = seed

        start = time.monotonic()
        result = run_beam_search(config)
        elapsed = time.monotonic() - start
        times_list.append(elapsed)

        score = result.score if result and result.score is not None else 0.0
        scores.append(score)

        # Extract base score from metric.json if available
        metric_path = WORKSPACE / config.metric_file
        base = 0.0
        if metric_path.exists():
            try:
                data = json.loads(metric_path.read_text())
                base = float(data.get(config.metric_key, 0.0))
            except Exception:
                pass
        base_scores.append(base)

        status = "PASS" if base >= GUARD_THRESHOLD else "FAIL"
        if verbose:
            print(f"  Run {i+1}/{runs}: score={score:.4f} base={base:.4f} "
                  f"guard={status} time={elapsed:.1f}s")

    # Aggregate
    median_score = median(scores)
    mean_score = sum(scores) / len(scores)
    min_base = min(base_scores) if base_scores else 0.0
    guard_pass = min_base >= GUARD_THRESHOLD
    avg_time = sum(times_list) / len(times_list)

    print()
    print("=== EVAL RESULTS ===")
    print(f"  SOLVE_WEIGHT:   {SOLVE_WEIGHT}")
    print(f"  SOLVE_TASKS:    {SOLVE_TASKS}")
    print(f"  Median score:   {median_score:.4f}")
    print(f"  Mean score:     {mean_score:.4f}")
    print(f"  Scores:         {[f'{s:.4f}' for s in scores]}")
    print(f"  Min base score: {min_base:.4f}")
    print(f"  Guard pass:     {guard_pass}")
    print(f"  Avg time/run:   {avg_time:.1f}s")
    print("========================")
    print(f"\nSCORE: {median_score:.4f}")
    print(f"GUARD: {min_base:.4f}")

    if not guard_pass:
        print(f"  WARNING: base score {min_base:.4f} below guard threshold {GUARD_THRESHOLD}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Eval for SOLVE_WEIGHT/SOLVE_TASKS beam search tuning")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--runs", type=int, default=3, help="Number of beam search runs")
    args = parser.parse_args()
    run_eval(args.verbose, args.runs)
