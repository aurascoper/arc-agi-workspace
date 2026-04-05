"""
target_arc2_kaggle.py — ARC-AGI-2 Kaggle submission solver
Hardware: T4x2 (32 GB total VRAM) — tensor-parallel via vLLM
Model:    Qwen3.5-35B-A3B (MoE, 3B active) — GPTQ-Int4 or bitsandbytes INT4
Scoring:  exact match; 2 attempts per test input
Output:   submission.json in standard ARC format

Auto-detects model path from Kaggle mounts:
  1. /kaggle/input/qwen35-35b-a3b-gptq-int4  (GPTQ, fastest)
  2. /kaggle/input/models/qwen-lm/qwen-3-5/transformers/qwen3.5-35b-a3b/1  (bitsandbytes)
  3. Falls back to HF hub download

Usage:
  python target_arc2_kaggle.py                    # full eval, writes submission.json
  python target_arc2_kaggle.py path/to/task.json  # single task debug
"""

import gc
import json
import os
import random
import re
import sys
import threading
import traceback
from copy import deepcopy
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

MODEL_PATH = os.environ.get("ARC_MODEL_PATH", "Qwen/Qwen3-30B-A3B-GPTQ-Int4")

# Auto-detect Kaggle model mounts — Qwen3-30B-A3B fits T4x2 better than 35B
_model_candidates = [
    ("/kaggle/input/qwen3-30b-a3b-gptq-int4", "gptq"),
    ("/kaggle/input/qwenqwen3-30b-a3b-gptq-int4", "gptq"),
    ("/kaggle/input/qwen3-30b-a3b-thinking-2507-4bit", "gptq"),
    ("/kaggle/input/junhowieqwen3-30b-a3b-instruct-2507-gptq", "gptq"),
    ("/kaggle/input/qwen35-35b-a3b-gptq-int4", "gptq"),
    ("/kaggle/input/models/qwen-lm/qwen-3-5/transformers/qwen3.5-35b-a3b/1", "bitsandbytes"),
    ("/kaggle/input/models/qwen-lm/qwen-3/transformers/qwen3-30b-a3b/1", "bitsandbytes"),
]
QUANTIZATION = os.environ.get("ARC_QUANTIZATION", "gptq")

for _path, _quant in _model_candidates:
    if Path(_path).exists():
        MODEL_PATH = _path
        QUANTIZATION = _quant
        break

TP = int(os.environ.get("ARC_TP", "2"))  # T4x2
MAX_NEW_TOKENS = int(os.environ.get("ARC_MAX_TOKENS", "3072"))
NUM_CANDIDATES = 10      # vLLM batches efficiently
MAX_REFLECTIONS = 3
NUM_ATTEMPTS = 2         # ARC-AGI-2 allows 2 submissions per test input

DSL_PATH = Path("/kaggle/working/dsl.py")
if not DSL_PATH.exists():
    DSL_PATH = Path("dsl.py")

ARC_DATA_ROOTS = [
    Path("/kaggle/input/arc-prize-2026/arc-agi_2_test_challenges.json"),
    Path("/kaggle/input/arc-prize-2026/arc-agi_2_evaluation_challenges.json"),
    Path("/kaggle/input/arc-agi-2/arc-agi_2_test_challenges.json"),
    Path("./arc_data/arc-agi_2_test_challenges.json"),
    Path("./arc_data/training"),
]

SUBMISSION_PATH = Path(os.environ.get(
    "ARC_SUBMISSION_PATH", "/kaggle/working/submission.json"
))

# ---------------------------------------------------------------------------
# BACKEND: vLLM
# ---------------------------------------------------------------------------

_llm = None


def _init_backend():
    global _llm
    if _llm is not None:
        return

    import torch
    from vllm import LLM

    llm_kwargs = dict(
        model=MODEL_PATH,
        tensor_parallel_size=TP,
        gpu_memory_utilization=0.90,
        max_model_len=4096,
        trust_remote_code=True,
    )

    if QUANTIZATION == "gptq":
        # Use standard "gptq" — "gptq_marlin" fails on models missing Marlin config
        llm_kwargs["dtype"] = "bfloat16"
        llm_kwargs["quantization"] = "gptq"
    elif QUANTIZATION == "bitsandbytes":
        llm_kwargs["dtype"] = "float16"
        llm_kwargs["quantization"] = "bitsandbytes"
        llm_kwargs["load_format"] = "bitsandbytes"
    else:
        llm_kwargs["dtype"] = "float16" if torch.cuda.is_available() else "float32"
        if QUANTIZATION and QUANTIZATION not in ("auto", "none", "0", ""):
            llm_kwargs["quantization"] = QUANTIZATION

    print(f"[backend] vLLM: {MODEL_PATH}", flush=True)
    print(f"  TP={TP} dtype={llm_kwargs.get('dtype')} quant={QUANTIZATION}", flush=True)
    _llm = LLM(**llm_kwargs)
    print("[backend] vLLM ready.", flush=True)


def _generate_batch(prompts: list[str], temperature: float) -> list[str]:
    if _llm is None:
        _init_backend()

    from vllm import SamplingParams
    params = SamplingParams(
        temperature=max(temperature, 1e-6),
        max_tokens=MAX_NEW_TOKENS,
        stop=["```\n\n", "```\n#", "\n\nif __name__"],
    )
    outputs = _llm.generate(prompts, params)
    return [o.outputs[0].text for o in outputs]


def call_model(prompt: str, temperature: float = 0.0) -> str:
    return _generate_batch([prompt], temperature)[0]


# ---------------------------------------------------------------------------
# ARC helpers
# ---------------------------------------------------------------------------

HELPER_FUNCTIONS = {"np": np, "deepcopy": deepcopy}


def fix_indentation(code: str) -> str:
    return "\n".join(
        line if line.strip() else ""
        for line in code.replace("\t", "    ").split("\n")
    )


def extract_python_code(text: str) -> str:
    # Strip Qwen3 chain-of-thought
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    code = None
    for pat in [r"```python\s*(.*?)\s*```", r"```\s*(.*?)\s*```"]:
        m = re.search(pat, text, re.DOTALL)
        if m and "def transform" in m.group(1):
            code = m.group(1)
            break
    if not code:
        m = re.search(r"(def\s+transform\s*\(.*)", text, re.DOTALL)
        if m:
            code = m.group(1)
    if not code:
        code = text
    if "def transform" in code:
        code = code[code.find("def transform"):]
        lines, trimmed = code.splitlines(), []
        for i, line in enumerate(lines):
            if i == 0 or line.startswith((" ", "\t")) or not line.strip() or line.lstrip().startswith("#"):
                trimmed.append(line)
            else:
                break
        code = "\n".join(trimmed)
    return fix_indentation(code)


def grid_to_str(grid) -> str:
    if not grid or not isinstance(grid, list):
        return str(grid)
    try:
        return "\n".join("".join(str(c) for c in row) for row in grid)
    except Exception:
        return str(grid)


def run_with_timeout(fn, args, timeout_sec=5):
    result, error = [None], [None]

    def target():
        try:
            result[0] = fn(*args)
        except Exception as e:
            error[0] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout_sec)
    if t.is_alive():
        raise TimeoutError("Infinite loop")
    if error[0]:
        raise error[0]
    return result[0]


def _read_dsl():
    try:
        return DSL_PATH.read_text()
    except Exception:
        return ""


def try_code_on_task(code: str, task_data: dict, evaluate_on_test=False):
    ns = dict(HELPER_FUNCTIONS)
    failures = []
    pairs = task_data.get("test" if evaluate_on_test else "train", [])
    dsl_code = _read_dsl()
    preds = []

    try:
        exec(dsl_code + "\n" + code, ns)
        transform_fn = ns.get("transform")
        if not transform_fn:
            return False, [], [(pairs[0]["input"] if pairs else "", "", None, "No transform fn")]

        for pair in pairs:
            try:
                pred = run_with_timeout(transform_fn, (pair["input"],), timeout_sec=5)
                pred_list = [list(row) for row in pred] if pred else []
                out_list = [list(row) for row in pair["output"]]
                if pred_list != out_list:
                    failures.append((pair["input"], pair["output"], pred_list, None))
                preds.append(pred_list)
            except Exception as e:
                failures.append((pair["input"], pair["output"], None, str(e)))
                preds.append(None)
    except Exception as e:
        failures.append(("", "", None, str(e)))

    return len(failures) == 0, preds, failures


def build_prompt(task_data: dict) -> str:
    result = [None]

    def _run():
        try:
            ns = {"grid_to_str": grid_to_str}
            exec(_read_dsl(), ns)
            if "build_prompt" in ns:
                result[0] = ns["build_prompt"](task_data)
        except Exception:
            pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=120)
    if result[0] is not None:
        return result[0]

    prompt = "ARC puzzle.\n"
    for i, pair in enumerate(task_data["train"]):
        prompt += f"Ex{i+1} In:\n{grid_to_str(pair['input'])}\nOut:\n{grid_to_str(pair['output'])}\n\n"
    prompt += "Output ONLY python code `def transform(input_grid):`\n```python\n"
    return prompt


def build_reflection_prompt(task_data: dict, code: str, failures: list) -> str:
    prompt = "WRONG. Fix:\n```python\n" + code + "\n```\nErrors:\n"
    for _, expected, got, err in failures[:2]:
        prompt += f"- {err}\n" if err else f"- Expected:\n{grid_to_str(expected)}\n  Got:\n{grid_to_str(got)}\n"
    prompt += "\nTraining:\n"
    for i, pair in enumerate(task_data.get("train", [])[:3]):
        prompt += f"Ex{i+1} In:\n{grid_to_str(pair['input'])}\nOut:\n{grid_to_str(pair['output'])}\n\n"
    prompt += "Output ONLY corrected code.\n```python\ndef transform(input_grid):\n"
    return prompt


# ---------------------------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------------------------

def load_tasks() -> dict:
    for candidate in ARC_DATA_ROOTS:
        if candidate.is_file() and candidate.suffix == ".json":
            print(f"[data] Loading from {candidate}", flush=True)
            return json.loads(candidate.read_text())
        if candidate.is_dir():
            print(f"[data] Loading from directory {candidate}", flush=True)
            tasks = {}
            for p in sorted(candidate.rglob("*.json")):
                if "metadata" in p.name or "package" in p.name:
                    continue
                try:
                    tasks[p.stem] = json.loads(p.read_text())
                except Exception:
                    pass
            if tasks:
                return tasks
    raise FileNotFoundError(
        f"No ARC data found. Checked: {[str(r) for r in ARC_DATA_ROOTS]}"
    )


# ---------------------------------------------------------------------------
# CORE SOLVER — batched candidate generation + reflection
# ---------------------------------------------------------------------------

def solve_task(task_data: dict) -> list[list]:
    """Solve one task. Returns [num_test_inputs][NUM_ATTEMPTS] grid predictions."""
    prompt = build_prompt(task_data)
    temps = [0.0, 0.35, 0.75]
    candidate_temps = [temps[min(i, len(temps) - 1)] for i in range(NUM_CANDIDATES)]

    # Batch all initial candidates by temperature
    unique_temps = sorted(set(candidate_temps))
    all_codes = []
    for temp in unique_temps:
        count = candidate_temps.count(temp)
        responses = _generate_batch([prompt] * count, temperature=temp)
        all_codes.extend(extract_python_code(r) for r in responses)

    # Reflection pass
    refined_codes = []
    for ci, code in enumerate(all_codes):
        temp = candidate_temps[ci]
        _, _, failures = try_code_on_task(code, task_data, evaluate_on_test=False)
        for _ in range(MAX_REFLECTIONS):
            if not failures:
                break
            ref = build_reflection_prompt(task_data, code, failures)
            code = extract_python_code(call_model(ref, temperature=temp))
            _, _, failures = try_code_on_task(code, task_data, evaluate_on_test=False)
        refined_codes.append(code)

    # Collect distinct predictions per test input
    test_pairs = task_data.get("test", [])
    if not test_pairs:
        return [[None] * NUM_ATTEMPTS]

    dsl_code = _read_dsl()
    all_test_predictions = []
    for pair in test_pairs:
        seen, preds = [], []
        for code in refined_codes:
            if len(preds) >= NUM_ATTEMPTS:
                break
            try:
                ns = dict(HELPER_FUNCTIONS)
                exec(dsl_code + "\n" + code, ns)
                transform_fn = ns.get("transform")
                if not transform_fn:
                    continue
                pred = run_with_timeout(transform_fn, (pair["input"],), timeout_sec=5)
                pred_list = [list(row) for row in pred] if pred else None
                if pred_list is not None and pred_list not in seen:
                    seen.append(pred_list)
                    preds.append(pred_list)
            except Exception:
                pass
        while len(preds) < NUM_ATTEMPTS:
            preds.append(preds[-1] if preds else None)
        all_test_predictions.append(preds)

    return all_test_predictions


# ---------------------------------------------------------------------------
# SUBMISSION WRITER
# ---------------------------------------------------------------------------

def predictions_to_submission(task_id: str, all_preds: list) -> dict:
    result = []
    for preds in all_preds:
        entry = {}
        for i, pred in enumerate(preds[:NUM_ATTEMPTS]):
            entry[f"attempt_{i+1}"] = pred if pred is not None else [[0]]
        result.append(entry)
    return {task_id: result}


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def run(single_task_path: str | None = None):
    _init_backend()

    if single_task_path:
        task_id = Path(single_task_path).stem
        task_data = json.loads(Path(single_task_path).read_text())
        tasks = {task_id: task_data}
    else:
        tasks = load_tasks()

    print(f"[eval] {len(tasks)} tasks to solve", flush=True)

    submission = {}
    correct = 0

    for i, (task_id, task_data) in enumerate(tasks.items()):
        print(f"\n[{i+1}/{len(tasks)}] {task_id}", flush=True)
        all_preds = solve_task(task_data)
        submission.update(predictions_to_submission(task_id, all_preds))

        # Score if ground truth available
        for j, pair in enumerate(task_data.get("test", [])):
            if "output" not in pair:
                continue
            gt = pair["output"]
            preds = all_preds[j] if j < len(all_preds) else []
            hit = any(p == gt for p in preds if p is not None)
            if hit:
                correct += 1
            print(f"  test[{j}]: {'PASS' if hit else 'fail'}", flush=True)

    SUBMISSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUBMISSION_PATH.write_text(json.dumps(submission, indent=2))
    print(f"\n[done] submission -> {SUBMISSION_PATH}", flush=True)

    scored = sum(1 for td in tasks.values() if any("output" in p for p in td.get("test", [])))
    if scored:
        print(f"[score] {correct}/{scored} = {correct/scored:.3f}", flush=True)


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else None)
