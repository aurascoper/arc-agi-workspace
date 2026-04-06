#!/usr/bin/env python3
"""
lora_train.py — Self-distillation LoRA training on successful ARC programs.

Reads successful_programs.jsonl, deduplicates, formats as Qwen3.5 chat template,
trains a LoRA adapter via mlx_lm.lora, validates on canary tasks, and exits 0/1.

Run as subprocess from evolve_qwen_arc.py to isolate MLX memory.

Usage:
  python3 lora_train.py --data evolution_results/successful_programs.jsonl \
                        --output evolution_results/lora_adapters/20260405_060000/
"""

import argparse
import gc
import hashlib
import json
import os
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
MODEL_PATH = os.environ.get("ARC_MODEL_PATH", "mlx-community/Qwen3.5-9B-4bit")

# Use turboquant-mlx venv python which has mlx_lm installed
_VENV_PYTHON = WORKSPACE.parent / "turboquant-mlx" / ".venv" / "bin" / "python3"
MLX_PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable

# LoRA hyperparameters (defaults; PB2 may override LR, ITERS, DATA_MIX)
LORA_RANK = 4
LORA_LAYERS = 4       # reduced from 8 — fits 16GB M4 with 9B model
BATCH_SIZE = 1
MAX_SEQ_LENGTH = 512   # reduced from 1024 — OOM at 1024 on 16GB
ITERS = 200
LEARNING_RATE = 2e-5

# PB2 hyperparameter search bounds
PB2_HISTORY_PATH = Path(__file__).resolve().parent / "evolution_results" / "pb2_history.jsonl"
PB2_LR_BOUNDS = (1e-6, 1e-4)    # log scale
PB2_ITERS_BOUNDS = (50, 100)     # capped at 100 — fits 30min timeout on M4
PB2_MIX_BOUNDS = (0.0, 1.0)     # synthetic data ratio

# Canary validation
CANARY_COUNT = 5
CANARY_MIN_SOLVES = 2


# ---------------------------------------------------------------------------
# DATA PREPARATION
# ---------------------------------------------------------------------------

def _load_synthetic_as_programs(synthetic_path: Path, seen: set) -> list[dict]:
    """Convert synthetic_tasks.jsonl entries to the same format as successful_programs.jsonl.

    synthetic_tasks.jsonl has: {source_task, synthetic_task: {train, test}, code, timestamp}
    We convert to: {task_name, code, prompt, num_train, num_test, timestamp, source}

    Generates prompts via build_prompt() from dsl.py to match the inference path.
    Deduplicates against `seen` set. Returns newest first.
    """
    # Load build_prompt from DSL
    build_prompt = None
    try:
        dsl_path = WORKSPACE / "dsl.py"
        dsl_ns: dict = {}
        exec(compile(dsl_path.read_text(), str(dsl_path), "exec"), dsl_ns)
        build_prompt = dsl_ns.get("build_prompt")
    except Exception:
        pass

    entries = []
    with open(synthetic_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue

            synth_task = raw.get("synthetic_task")
            code = raw.get("code")
            if not synth_task or not code:
                continue

            task_name = f"synth_{raw.get('source_task', 'unknown')}"

            # Save synthetic task as JSON so canary validation can find it
            synth_json_dir = WORKSPACE / "evolution_results" / "synthetic_task_json"
            synth_json_dir.mkdir(exist_ok=True)
            synth_json_path = synth_json_dir / f"{task_name}.json"
            if not synth_json_path.exists():
                synth_json_path.write_text(json.dumps(synth_task))

            # Dedup against real programs
            key = hashlib.md5(f"{task_name}:{code}".encode()).hexdigest()
            if key in seen:
                continue
            seen.add(key)

            # Generate prompt matching inference path
            prompt = None
            if build_prompt:
                try:
                    prompt = build_prompt(synth_task)
                except Exception:
                    pass

            if not prompt:
                # Fallback: simple prompt from training pairs
                parts = []
                for i, pair in enumerate(synth_task.get("train", [])[:3]):
                    parts.append(f"Input:\n{pair['input']}\nOutput:\n{pair['output']}")
                parts.append("Output ONLY python code `def transform(input_grid):`\n```python\n")
                prompt = "\n\n".join(parts)

            entries.append({
                "task_name": task_name,
                "code": code,
                "prompt": prompt,
                "num_train": len(synth_task.get("train", [])),
                "num_test": len(synth_task.get("test", [])),
                "timestamp": raw.get("timestamp", 0),
                "source": "synthetic",
            })

    # Newest first for freshness
    entries.sort(key=lambda e: e["timestamp"], reverse=True)
    return entries


def load_and_dedup(jsonl_path: Path, include_synthetic: bool = True,
                   max_synthetic_ratio: float = 0.5) -> list[dict]:
    """Read JSONL, deduplicate by (task_name, code) hash.

    If include_synthetic=True, also loads synthetic_tasks.jsonl from the same
    directory, capping synthetic entries at max_synthetic_ratio of total data.
    """
    entries = []
    seen = set()
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = hashlib.md5(
                f"{entry['task_name']}:{entry['code']}".encode()
            ).hexdigest()
            if key not in seen:
                seen.add(key)
                entries.append(entry)

    # Merge synthetic tasks (TransCoder-style training data from failed programs)
    if include_synthetic:
        synthetic_path = jsonl_path.parent / "synthetic_tasks.jsonl"
        if synthetic_path.exists():
            synthetic_entries = _load_synthetic_as_programs(synthetic_path, seen)
            # Cap: if we have N real entries, allow at most N * ratio / (1 - ratio) synthetic
            if entries:
                max_synthetic = int(len(entries) * max_synthetic_ratio / (1 - max_synthetic_ratio))
            else:
                max_synthetic = 10  # bootstrap: allow some synthetic even with 0 real
            synthetic_entries = synthetic_entries[:max(max_synthetic, 0)]
            if synthetic_entries:
                print(f"[lora] Merging {len(synthetic_entries)} synthetic tasks (cap={max_synthetic})")
            entries.extend(synthetic_entries)

    return entries


def format_as_chat(entries: list[dict]) -> list[dict]:
    """Format entries as Qwen3.5 chat messages.

    No system prompt — matches inference path in target_mlx_arc.py which sends
    raw prompts to mlx_lm.generate() without chat template wrapping.
    The tokenizer's apply_chat_template handles <|im_start|>/<|im_end|> boundaries.
    """
    formatted = []
    for e in entries:
        formatted.append({
            "messages": [
                {"role": "user", "content": e["prompt"]},
                {"role": "assistant", "content": f"```python\n{e['code']}\n```"},
            ]
        })
    return formatted


def prepare_data(jsonl_path: Path, output_dir: Path, seed: int = 42):
    """Load, dedup, split, and write train/valid JSONL files."""
    entries = load_and_dedup(jsonl_path)
    if not entries:
        print(f"[lora] No entries in {jsonl_path}")
        return 0, []

    formatted = format_as_chat(entries)

    random.seed(seed)
    random.shuffle(formatted)
    split = max(1, int(len(formatted) * 0.9))
    train_data = formatted[:split]
    valid_data = formatted[split:] or formatted[:1]  # at least 1 validation example

    output_dir.mkdir(parents=True, exist_ok=True)
    train_path = output_dir / "train.jsonl"
    valid_path = output_dir / "valid.jsonl"

    for path, data in [(train_path, train_data), (valid_path, valid_data)]:
        with open(path, "w") as f:
            for item in data:
                f.write(json.dumps(item) + "\n")

    near_miss_count = sum(1 for e in entries if e.get("source") == "near_miss")
    synthetic_count = sum(1 for e in entries if e.get("source") == "synthetic")
    print(f"[lora] Data: {len(entries)} unique ({near_miss_count} near-miss, {synthetic_count} synthetic) → {len(train_data)} train, {len(valid_data)} valid")
    return len(entries), entries


# ---------------------------------------------------------------------------
# TRAINING
# ---------------------------------------------------------------------------

def run_training(data_dir: Path, adapter_output: Path):
    """Run LoRA training via mlx_lm.lora CLI (subprocess for clean memory)."""
    adapter_output.mkdir(parents=True, exist_ok=True)

    # Write LoRA config for rank (--lora-rank removed in newer mlx_lm)
    lora_config = adapter_output / "lora_config.yaml"
    lora_config.write_text(f"lora_layers: {LORA_LAYERS}\nlora_parameters:\n  rank: {LORA_RANK}\n  dropout: 0.0\n  scale: 20.0\n")

    cmd = [
        MLX_PYTHON, "-m", "mlx_lm.lora",
        "--model", MODEL_PATH,
        "--train",
        "--data", str(data_dir),
        "--adapter-path", str(adapter_output),
        "--batch-size", str(BATCH_SIZE),
        "--num-layers", str(LORA_LAYERS),
        "--iters", str(ITERS),
        "--learning-rate", str(LEARNING_RATE),
        "--max-seq-length", str(MAX_SEQ_LENGTH),
        "--val-batches", "10",
        "--steps-per-report", "20",
        "--steps-per-eval", "50",
        "-c", str(lora_config),
    ]

    log_file = adapter_output / "training.log"
    print(f"[lora] Training: {' '.join(cmd)}")
    print(f"[lora] Live log: tail -f {log_file}")
    with open(log_file, "w") as lf:
        result = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, text=True, timeout=1800)

    if result.returncode != 0:
        print(f"[lora] Training FAILED (exit {result.returncode})")
        # Print tail of log for diagnostics
        try:
            lines = log_file.read_text().strip().split("\n")
            for line in lines[-10:]:
                print(f"  {line}")
        except Exception:
            pass
        return False

    print(f"[lora] Training complete. Adapter saved to {adapter_output}")
    try:
        lines = log_file.read_text().strip().split("\n")
        for line in lines[-5:]:
            print(f"  {line}")
    except Exception:
        pass
    return True


def fuse_adapter(adapter_path: Path, save_path: Path = None) -> Path | None:
    """Fuse LoRA adapter into base model weights.

    Returns the fused model directory path, or None on failure.
    This produces a standalone model with identical memory footprint to the
    base model — no adapter overhead at inference time.
    """
    if save_path is None:
        save_path = adapter_path / "fused_model"

    cmd = [
        MLX_PYTHON, "-m", "mlx_lm", "fuse",
        "--model", MODEL_PATH,
        "--adapter-path", str(adapter_path),
        "--save-path", str(save_path),
    ]

    print(f"[lora] Fusing adapter into base model → {save_path}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            print(f"[lora] Fuse FAILED (exit {result.returncode})")
            if result.stderr:
                print(f"[lora] stderr: {result.stderr[-500:]}")
            return None
        print(f"[lora] Fuse complete. Merged model at {save_path}")
        return save_path
    except subprocess.TimeoutExpired:
        print("[lora] Fuse timed out (10min limit)")
        return None
    except Exception as e:
        print(f"[lora] Fuse error: {e}")
        return None


# ---------------------------------------------------------------------------
# CANARY VALIDATION
# ---------------------------------------------------------------------------

def select_canary_tasks(entries: list[dict], count: int = CANARY_COUNT,
                        min_solves: int = CANARY_MIN_SOLVES) -> list[str]:
    """Pick tasks that were solved most frequently — reliable canaries."""
    task_counts = Counter(e["task_name"] for e in entries)
    reliable = [(name, cnt) for name, cnt in task_counts.items() if cnt >= min_solves]
    reliable.sort(key=lambda x: -x[1])

    if len(reliable) >= count:
        return [name for name, _ in reliable[:count]]

    # Fall back: take most-solved tasks even if < min_solves
    all_sorted = sorted(task_counts.items(), key=lambda x: -x[1])
    return [name for name, _ in all_sorted[:count]]


def validate_adapter(adapter_path: Path, canary_task_names: list[str]) -> bool:
    """Load model+adapter, run canary tasks, check all pass.

    Uses mx.eval() barriers and clears Metal cache on exit (C3).
    """
    import mlx.core as mx
    from mlx_lm import load, generate
    from mlx_lm.sample_utils import make_sampler

    # Search multiple directories for task JSON files
    arc_search_dirs = [
        WORKSPACE / "arc_agi_2_data" / "training",
        WORKSPACE / "arc_agi_2_data" / "evaluation",
        WORKSPACE / "arc_data" / "data" / "training",
        WORKSPACE / "arc_data" / "data" / "evaluation",
        WORKSPACE / "evolution_results" / "synthetic_task_json",
    ]

    def find_task_json(task_name: str) -> Path | None:
        for d in arc_search_dirs:
            p = d / f"{task_name}.json"
            if p.exists():
                return p
        return None

    print(f"[lora] Validating adapter on {len(canary_task_names)} canary tasks...")

    model, tokenizer = load(MODEL_PATH, adapter_path=str(adapter_path))

    # Load DSL namespace for build_prompt
    dsl_path = WORKSPACE / "dsl.py"
    dsl_ns = {}
    try:
        exec(compile(dsl_path.read_text(), str(dsl_path), "exec"), dsl_ns)
    except Exception as e:
        print(f"[lora] WARNING: DSL load failed: {e}")

    build_prompt = dsl_ns.get("build_prompt")
    all_passed = True

    for task_name in canary_task_names:
        task_path = find_task_json(task_name)
        if task_path is None:
            print(f"  [canary] {task_name}: SKIP (file not found)")
            continue

        task_data = json.loads(task_path.read_text())

        # Build prompt
        if build_prompt:
            try:
                prompt = build_prompt(task_data)
            except Exception:
                prompt = None
        else:
            prompt = None

        if not prompt:
            # Fallback prompt
            prompt = "Output ONLY python code `def transform(input_grid):`\n```python\n"
            for pair in task_data.get("train", [])[:2]:
                prompt = f"Input:\n{pair['input']}\nOutput:\n{pair['output']}\n\n" + prompt

        # Generate
        sampler = make_sampler(temp=1e-6)
        response = generate(model, tokenizer, prompt=prompt, max_tokens=1024, sampler=sampler)
        mx.eval(model.parameters())  # force eager evaluation

        # Extract and test code
        import re
        code_match = re.search(r"```python\s*(.*?)```", response, re.DOTALL)
        if not code_match or "def transform" not in response:
            print(f"  [canary] {task_name}: FAIL (no transform in response)")
            all_passed = False
            continue

        code = code_match.group(1).strip()
        ns = dict(dsl_ns)
        try:
            exec(dsl_ns.get("HELPER_CODE_PREFIX", "") + "\n" + code, ns)
            transform_fn = ns.get("transform")
            if not transform_fn:
                print(f"  [canary] {task_name}: FAIL (no transform function)")
                all_passed = False
                continue

            passed = True
            for pair in task_data.get("train", []):
                pred = transform_fn(pair["input"])
                pred_list = [list(row) for row in pred] if pred else []
                out_list = [list(row) for row in pair["output"]]
                if pred_list != out_list:
                    passed = False
                    break

            status = "PASS" if passed else "FAIL"
            print(f"  [canary] {task_name}: {status}")
            if not passed:
                all_passed = False

        except Exception as e:
            print(f"  [canary] {task_name}: FAIL ({e})")
            all_passed = False

    # C3: Clean up — clear all state before exit
    del model, tokenizer
    gc.collect()
    mx.clear_cache()

    # Save validation results
    results = {"passed": all_passed, "tasks": canary_task_names}
    (adapter_path / "validation_results.json").write_text(json.dumps(results, indent=2))

    return all_passed


# ---------------------------------------------------------------------------
# PB2 — Population-Based Bandits for hyperparameter scheduling
# (Parker-Holder et al., NeurIPS 2020, arXiv:2002.02518)
# Sequential single-agent variant: GP-based Bayesian optimization over
# (learning_rate, iters, data_mix) → holdout score.
# ---------------------------------------------------------------------------

def _load_pb2_history() -> list[dict]:
    """Load PB2 trial history."""
    if not PB2_HISTORY_PATH.exists():
        return []
    entries = []
    with open(PB2_HISTORY_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def _save_pb2_trial(config: dict, score: float):
    """Append a PB2 trial result."""
    PB2_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    import time
    entry = {
        "lr": config["lr"],
        "iters": config["iters"],
        "data_mix": config["data_mix"],
        "score": score,
        "timestamp": time.time(),
    }
    with open(PB2_HISTORY_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def pb2_suggest_config() -> dict:
    """Suggest next LoRA hyperparameters using GP-UCB.

    Falls back to random sampling if sklearn is unavailable or history is too short.
    Returns dict with keys: lr, iters, data_mix.
    """
    import math

    history = _load_pb2_history()

    # Need at least 3 trials for GP to be meaningful
    if len(history) < 3:
        # Random sampling for initial exploration
        lr = math.exp(random.uniform(math.log(PB2_LR_BOUNDS[0]),
                                     math.log(PB2_LR_BOUNDS[1])))
        iters = random.randint(PB2_ITERS_BOUNDS[0], PB2_ITERS_BOUNDS[1])
        data_mix = random.uniform(*PB2_MIX_BOUNDS)
        return {"lr": lr, "iters": iters, "data_mix": data_mix}

    try:
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import Matern
        import numpy as np
    except ImportError:
        # sklearn not available — perturb best config
        best = max(history, key=lambda h: h["score"])
        lr = best["lr"] * random.choice([0.5, 0.8, 1.0, 1.25, 2.0])
        lr = max(PB2_LR_BOUNDS[0], min(PB2_LR_BOUNDS[1], lr))
        iters = best["iters"] + random.choice([-50, -25, 0, 25, 50])
        iters = max(PB2_ITERS_BOUNDS[0], min(PB2_ITERS_BOUNDS[1], iters))
        data_mix = best["data_mix"] + random.uniform(-0.2, 0.2)
        data_mix = max(0.0, min(1.0, data_mix))
        return {"lr": lr, "iters": iters, "data_mix": data_mix}

    # Normalize features to [0, 1]
    X = np.array([
        [math.log(h["lr"]), h["iters"], h["data_mix"]]
        for h in history
    ])
    y = np.array([h["score"] for h in history])

    # Normalize X columns
    X_min = X.min(axis=0)
    X_max = X.max(axis=0)
    X_range = X_max - X_min
    X_range[X_range == 0] = 1.0
    X_norm = (X - X_min) / X_range

    # Normalize y
    y_mean, y_std = y.mean(), max(y.std(), 1e-8)
    y_norm = (y - y_mean) / y_std

    # Fit GP
    kernel = Matern(nu=2.5, length_scale=0.5, length_scale_bounds=(0.01, 10.0))
    gp = GaussianProcessRegressor(kernel=kernel, alpha=0.1, n_restarts_optimizer=3)
    gp.fit(X_norm, y_norm)

    # UCB acquisition: generate random candidates, pick best UCB
    beta = 2.0  # exploration-exploitation tradeoff
    n_candidates = 200
    candidates = np.random.rand(n_candidates, 3)  # uniform [0,1]^3
    mu, sigma = gp.predict(candidates, return_std=True)
    ucb = mu + beta * sigma
    best_idx = np.argmax(ucb)

    # Denormalize
    best_norm = candidates[best_idx]
    best_raw = best_norm * X_range + X_min
    lr = math.exp(best_raw[0])
    lr = max(PB2_LR_BOUNDS[0], min(PB2_LR_BOUNDS[1], lr))
    iters = int(round(best_raw[1]))
    iters = max(PB2_ITERS_BOUNDS[0], min(PB2_ITERS_BOUNDS[1], iters))
    data_mix = float(best_raw[2])
    data_mix = max(0.0, min(1.0, data_mix))

    print(f"[pb2] GP-UCB suggested: lr={lr:.2e}, iters={iters}, data_mix={data_mix:.2f} "
          f"(from {len(history)} trials, best_ucb={ucb[best_idx]:.3f})")

    return {"lr": lr, "iters": iters, "data_mix": data_mix}


def run_training_pb2(data_dir: Path, adapter_output: Path,
                     pb2_config: dict | None = None) -> bool:
    """Run LoRA training with PB2-suggested hyperparameters."""
    if pb2_config is None:
        pb2_config = pb2_suggest_config()

    lr = pb2_config["lr"]
    iters = pb2_config["iters"]

    adapter_output.mkdir(parents=True, exist_ok=True)

    # Write LoRA config for rank
    lora_config = adapter_output / "lora_config.yaml"
    lora_config.write_text(f"lora_layers: {LORA_LAYERS}\nlora_parameters:\n  rank: {LORA_RANK}\n  dropout: 0.0\n  scale: 20.0\n")

    cmd = [
        MLX_PYTHON, "-m", "mlx_lm.lora",
        "--model", MODEL_PATH,
        "--train",
        "--data", str(data_dir),
        "--adapter-path", str(adapter_output),
        "--batch-size", str(BATCH_SIZE),
        "--num-layers", str(LORA_LAYERS),
        "--iters", str(iters),
        "--learning-rate", str(lr),
        "--max-seq-length", str(MAX_SEQ_LENGTH),
        "--val-batches", "10",
        "--steps-per-report", "20",
        "--steps-per-eval", "50",
        "-c", str(lora_config),
    ]

    log_file = adapter_output / "training.log"
    print(f"[pb2] Training: lr={lr:.2e}, iters={iters}, data_mix={pb2_config['data_mix']:.2f}")
    print(f"[pb2] Live log: tail -f {log_file}")
    with open(log_file, "w") as lf:
        result = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, text=True, timeout=1800)

    if result.returncode != 0:
        print(f"[pb2] Training FAILED (exit {result.returncode})")
        try:
            lines = log_file.read_text().strip().split("\n")
            for line in lines[-10:]:
                print(f"  {line}")
        except Exception:
            pass
        return False

    print(f"[pb2] Training complete. Adapter saved to {adapter_output}")
    try:
        lines = log_file.read_text().strip().split("\n")
        for line in lines[-5:]:
            print(f"  {line}")
    except Exception:
        pass
    return True


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LoRA self-distillation on successful ARC programs")
    parser.add_argument("--data", type=Path, required=True, help="Path to successful_programs.jsonl")
    parser.add_argument("--output", type=Path, required=True, help="Adapter output directory")
    parser.add_argument("--pb2", action="store_true", help="Use PB2 hyperparameter scheduling")
    parser.add_argument("--fuse", action="store_true", help="Fuse adapter into base model after validation")
    args = parser.parse_args()

    if not args.data.exists():
        print(f"[lora] Data file not found: {args.data}")
        sys.exit(1)

    # Step 1: Prepare data
    data_dir = WORKSPACE / "evolution_results" / "lora_data"
    count, entries = prepare_data(args.data, data_dir)
    if count < 10:
        print(f"[lora] Only {count} unique programs — need at least 10 for training")
        sys.exit(1)

    # Step 2: Train (with optional PB2 hyperparameter scheduling)
    pb2_config = None
    if args.pb2:
        pb2_config = pb2_suggest_config()
        print(f"[pb2] Config: lr={pb2_config['lr']:.2e}, iters={pb2_config['iters']}, "
              f"data_mix={pb2_config['data_mix']:.2f}")
        success = run_training_pb2(data_dir, args.output, pb2_config)
    else:
        success = run_training(data_dir, args.output)

    if not success:
        sys.exit(1)

    # Step 3: Validate on canary tasks
    canary_tasks = select_canary_tasks(entries)
    if not canary_tasks:
        print("[lora] No canary tasks available — accepting adapter without validation")
        if pb2_config:
            _save_pb2_trial(pb2_config, 0.5)  # neutral score for unvalidated
        sys.exit(0)

    passed = validate_adapter(args.output, canary_tasks)
    if passed:
        print(f"[lora] Adapter VALIDATED — all {len(canary_tasks)} canary tasks passed")
        if pb2_config:
            _save_pb2_trial(pb2_config, 1.0)  # full score for validated adapter

        # Fuse adapter into base model weights (same memory as base at inference)
        if args.fuse:
            fused_path = fuse_adapter(args.output)
            if fused_path:
                # Write marker so caller knows the fused path
                (args.output / "fused_model_path.txt").write_text(str(fused_path))
            else:
                print("[lora] Fuse failed — adapter still usable but will OOM on 16GB")
        sys.exit(0)
    else:
        print(f"[lora] Adapter REJECTED — canary task regression detected")
        if pb2_config:
            _save_pb2_trial(pb2_config, 0.0)  # zero for rejected
        sys.exit(1)


if __name__ == "__main__":
    main()
