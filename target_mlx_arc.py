"""
target_mlx_arc.py — Local Apple Silicon (MLX) port of target_kaggle_arc.py
Targets M4 16GB with Qwen3-30B-A3B-4bit via mlx-lm + turboquant KV cache compression.

Backend: MLX with optional TurboQuant KV cache compression for longer contexts.

Usage:
  python target_mlx_arc.py                      # evaluate MAX_TASKS_TO_EVALUATE tasks
  python target_mlx_arc.py path/to/task.json     # single task
"""

import gc
import json
import re
import os
import sys
import traceback
import random
import threading
from pathlib import Path
from copy import deepcopy

# Ensure turboquant-mlx venv site-packages are on sys.path (mlx_lm lives there)
_tq_venv = Path(__file__).resolve().parent.parent / "turboquant-mlx" / ".venv"
_tq_sp = next(_tq_venv.glob("lib/python*/site-packages"), None)
if _tq_sp and str(_tq_sp) not in sys.path:
    sys.path.insert(0, str(_tq_sp))

import numpy as np

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

MODEL_PATH = os.environ.get(
    "ARC_MODEL_PATH",
    "mlx-community/Qwen3.5-9B-4bit",  # Dense 9B at 4-bit, ~5.5GB — fits M4 16GB
)

MAX_TASKS_TO_EVALUATE = 10
MAX_REFLECTIONS = 3
NUM_CANDIDATES = 5  # fewer than Kaggle (no batching advantage on single GPU)
MAX_NEW_TOKENS = int(os.environ.get("ARC_MAX_TOKENS", "1024"))
USE_TURBOQUANT = os.environ.get("USE_TURBOQUANT", "1") == "1"
TQ_BITS = int(os.environ.get("TQ_BITS", "3"))
TQ_FP16_LAYERS = int(os.environ.get("TQ_FP16_LAYERS", "4"))

# ---------------------------------------------------------------------------
# BACKEND: MLX
# ---------------------------------------------------------------------------

_model = None
_tokenizer = None
_adapter_path = None


def _init_backend():
    global _model, _tokenizer

    from mlx_lm import load
    load_kwargs = {}
    if _adapter_path:
        load_kwargs["adapter_path"] = _adapter_path
        print(f"[backend] Loading {MODEL_PATH} via MLX with adapter {_adapter_path}...", flush=True)
    else:
        print(f"[backend] Loading {MODEL_PATH} via MLX...", flush=True)
    _model, _tokenizer = load(MODEL_PATH, **load_kwargs)

    if USE_TURBOQUANT:
        print(f"[backend] KV quantization: {TQ_BITS}-bit (mlx-lm built-in)", flush=True)

    print("[backend] MLX ready.", flush=True)


def unload_model():
    """Free model memory (including Metal cache) before LoRA training subprocess."""
    import mlx.core as mx
    global _model, _tokenizer
    _model = _tokenizer = None
    gc.collect()
    mx.clear_cache()
    print("[backend] Model unloaded, Metal cache cleared.", flush=True)


def reload_with_adapter(adapter_path=None):
    """Reload model, optionally with a LoRA adapter."""
    global _adapter_path
    _adapter_path = adapter_path
    unload_model()
    _init_backend()


def _generate(prompt: str, temperature: float, max_tokens: int = None) -> str:
    """Generate a single response."""
    if _model is None:
        _init_backend()

    from mlx_lm import generate
    from mlx_lm.sample_utils import make_sampler

    kwargs = {
        "max_tokens": max_tokens or MAX_NEW_TOKENS,
        "sampler": make_sampler(temp=max(temperature, 1e-6)),
    }
    if USE_TURBOQUANT:
        kwargs["kv_bits"] = TQ_BITS

    response = generate(
        _model,
        _tokenizer,
        prompt=prompt,
        **kwargs,
    )
    return response


def call_model(prompt: str, temperature: float = 0.0, max_tokens: int = None) -> str:
    text = _generate(prompt, temperature, max_tokens=max_tokens)
    print(f"[model] {len(text)} chars. Preview: {repr(text[:120])}", flush=True)
    return text


# ---------------------------------------------------------------------------
# ARC helpers (shared with target_kaggle_arc.py)
# ---------------------------------------------------------------------------

HELPER_FUNCTIONS = {"np": np, "deepcopy": deepcopy}


def fix_indentation(code: str) -> str:
    code = code.replace("\t", "    ")
    lines = code.split("\n")
    return "\n".join(line if line.strip() else "" for line in lines)


def extract_python_code(text: str) -> str:
    code = None
    m = re.search(r"```python\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        code = m.group(1)
    if not code:
        m = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
        if m and "def transform" in m.group(1):
            code = m.group(1)
    if not code:
        m = re.search(r"(def\s+transform\s*\(.*)", text, re.DOTALL)
        if m:
            code = m.group(1)
    if not code:
        code = text
    if "def transform" in code:
        code = code[code.find("def transform"):]
        lines = code.splitlines()
        trimmed = []
        for i, line in enumerate(lines):
            if i == 0:
                trimmed.append(line)
                continue
            if line.startswith((" ", "\t")) or line.strip() == "" or line.lstrip().startswith("#"):
                trimmed.append(line)
                continue
            break
        code = "\n".join(trimmed)
    return fix_indentation(code)


def grid_to_str(grid):
    if not grid or not isinstance(grid, list):
        return str(grid)
    try:
        return "\n".join("".join(str(c) for c in row) for row in grid)
    except Exception:
        return str(grid)


def hunter_seeker_arc_jsons(root_path: Path, max_tasks: int) -> list[Path]:
    valid_tasks = [
        p for p in root_path.rglob("*.json")
        if "metadata" not in p.name and "package" not in p.name
    ]
    random.shuffle(valid_tasks)
    return valid_tasks[:max_tasks]


def build_prompt(task_data: dict) -> str:
    result = [None]
    err = [None]

    def _run():
        try:
            ns = {"grid_to_str": grid_to_str}
            exec(open("dsl.py").read(), ns)
            if "build_prompt" in ns:
                result[0] = ns["build_prompt"](task_data)
        except Exception as e:
            err[0] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=120)
    if result[0] is not None:
        return result[0]
    if err[0]:
        print(f"[!] DSL prompt error: {err[0]}")

    prompt = "ARC puzzle.\n"
    for i, pair in enumerate(task_data["train"]):
        prompt += f"Ex{i+1} In:\n{grid_to_str(pair['input'])}\nOut:\n{grid_to_str(pair['output'])}\n\n"
    prompt += "Output ONLY python code `def transform(input_grid):`\n```python\n"
    return prompt


def build_task_hints(task_data: dict) -> str:
    try:
        full_prompt = build_prompt(task_data)
        if "HINTS:\n" in full_prompt:
            hint_block = full_prompt.split("HINTS:\n", 1)[1]
            if "Output ONLY" in hint_block:
                hint_block = hint_block.split("Output ONLY", 1)[0].rstrip()
            if hint_block:
                return "HINTS:\n" + hint_block + "\n\n"
    except Exception:
        pass
    return ""


def build_reflection_prompt(task_data: dict, code: str, failures: list, cached_hints: str = "") -> str:
    prompt = "WRONG. Fix this code:\n```python\n" + code + "\n```\nErrors:\n"
    for inp, expected, got, err in failures[:2]:
        if err:
            prompt += f"- {err}\n"
        else:
            prompt += f"- Expected:\n{grid_to_str(expected)}\n  Got:\n{grid_to_str(got)}\n"
    prompt += "\nTraining examples:\n"
    for i, pair in enumerate(task_data.get("train", [])[:3]):
        prompt += f"Ex{i+1} In:\n{grid_to_str(pair['input'])}\nOut:\n{grid_to_str(pair['output'])}\n\n"
    prompt += cached_hints
    prompt += (
        "Revise the rule so it matches every training example. "
        "Prefer short helper-based code and preserve rectangular list-of-lists output.\n"
        "Output ONLY corrected code. NO explanation.\n```python\ndef transform(input_grid):\n"
    )
    return prompt


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
        raise TimeoutError("Infinite loop detected")
    if error[0]:
        raise error[0]
    return result[0]


def _trace_transform(code: str, input_grid, dsl_code: str) -> list[dict]:
    """ABPR: capture intermediate grid states during transform execution.

    Wraps each top-level DSL call inside transform() to record before/after.
    Returns list of {"call": "func_name(...)", "result_shape": (r,c), "ok": bool}.
    """
    traces = []
    ns = dict(HELPER_FUNCTIONS)
    try:
        exec(dsl_code + "\n" + code, ns)
    except Exception:
        return traces

    transform_fn = ns.get("transform")
    if not transform_fn:
        return traces

    import dis
    try:
        instructions = list(dis.get_instructions(transform_fn))
    except Exception:
        return traces

    # Extract top-level function calls from bytecode
    call_names = []
    for instr in instructions:
        if instr.opname in ("LOAD_GLOBAL", "LOAD_DEREF") and isinstance(instr.argval, str):
            if instr.argval in ns and callable(ns.get(instr.argval)):
                call_names.append(instr.argval)

    if not call_names:
        return traces

    # Instrument: wrap each called function to record intermediate results
    call_log = []
    for fname in set(call_names):
        original = ns.get(fname)
        if not original or not callable(original):
            continue

        def make_wrapper(orig, name):
            def wrapper(*args, **kwargs):
                result = orig(*args, **kwargs)
                shape = None
                if isinstance(result, list) and result and isinstance(result[0], list):
                    shape = (len(result), len(result[0]))
                call_log.append({"call": name, "result_shape": shape})
                return result
            return wrapper

        ns[fname] = make_wrapper(original, fname)

    try:
        ns2 = dict(ns)
        exec(dsl_code + "\n" + code, ns2)
        # Re-apply wrappers to the new namespace
        for fname in set(call_names):
            if fname in ns and fname not in ("transform",):
                ns2[fname] = ns[fname]
        transform_fn2 = ns2.get("transform")
        if transform_fn2:
            run_with_timeout(transform_fn2, (input_grid,), timeout_sec=5)
    except Exception as e:
        call_log.append({"call": "EXCEPTION", "error": str(e)[:100]})

    return call_log


def try_code_on_task(code: str, task_data: dict, evaluate_on_test=False, abpr_trace=False):
    ns = dict(HELPER_FUNCTIONS)
    failures = []
    pairs = task_data.get("test", []) if evaluate_on_test else task_data.get("train", [])

    try:
        dsl_code = open("dsl.py").read()
    except Exception as e:
        dsl_code = ""
        print(f"Warning: Could not read dsl.py: {e}")

    try:
        exec(dsl_code + "\n" + code, ns)
        transform_fn = ns.get("transform")
        if not transform_fn:
            return False, [(pairs[0]["input"], pairs[0]["output"], None, "No 'transform' function", None)]

        for pair in pairs:
            try:
                pred = run_with_timeout(transform_fn, (pair["input"],), timeout_sec=5)
                pred_list = [list(row) for row in pred] if pred else []
                out_list = [list(row) for row in pair["output"]]
                if pred_list != out_list:
                    abpr = _trace_transform(code, pair["input"], dsl_code) if abpr_trace else None
                    failures.append((pair["input"], pair["output"], pred_list, None, None, abpr))
                else:
                    pass  # success — no trace needed
            except Exception as e:
                abpr = _trace_transform(code, pair["input"], dsl_code) if abpr_trace else None
                failures.append((pair["input"], pair["output"], None, str(e), traceback.format_exc(), abpr))

    except Exception as e:
        tb = traceback.format_exc()
        if pairs:
            failures.append((pairs[0]["input"], pairs[0]["output"], None, str(e), tb, None))
        else:
            failures.append(("", "", None, str(e), tb, None))

    return len(failures) == 0, failures


def run_code_on_inputs(code: str, inputs: list) -> list:
    """Execute transform code on a list of input grids. Returns predictions (None on crash).

    Used by D4 ensemble to get test predictions for voting.
    """
    ns = dict(HELPER_FUNCTIONS)
    try:
        dsl_code = open("dsl.py").read()
    except Exception:
        dsl_code = ""
    exec(dsl_code + "\n" + code, ns)
    transform_fn = ns.get("transform")
    if not transform_fn:
        return [None] * len(inputs)
    results = []
    for inp in inputs:
        try:
            pred = run_with_timeout(transform_fn, (inp,), timeout_sec=5)
            results.append([list(row) for row in pred] if pred else None)
        except Exception:
            results.append(None)
    return results


def calculate_pixel_accuracy(expected, predicted) -> float:
    if not predicted or not expected:
        return 0.0
    if not isinstance(predicted, list) or not all(isinstance(r, list) for r in predicted):
        return 0.0
    if len(set(len(r) for r in predicted)) > 1:
        return 0.0
    try:
        exp = np.array(expected)
        pred = np.array(predicted)
        max_r = max(exp.shape[0], pred.shape[0])
        max_c = max(exp.shape[1], pred.shape[1])
        canvas_exp = np.full((max_r, max_c), -1.0)
        canvas_pred = np.full((max_r, max_c), -2.0)
        canvas_exp[: exp.shape[0], : exp.shape[1]] = exp
        canvas_pred[: pred.shape[0], : pred.shape[1]] = pred

        base_score = float(np.sum(canvas_exp == canvas_pred) / (max_r * max_c))

        spatial_score, valid_colors = 0.0, 0
        for color in np.unique(canvas_exp):
            if color < 0:
                continue
            coords_exp = np.argwhere(canvas_exp == color)
            coords_pred = np.argwhere(canvas_pred == color)
            if coords_exp.size == 0 or coords_pred.size == 0:
                continue
            diff = coords_exp[:, np.newaxis, :] - coords_pred[np.newaxis, :, :]
            distances = np.linalg.norm(diff, ord=1, axis=2)
            hausdorff = max(np.max(np.min(distances, axis=1)), np.max(np.min(distances, axis=0)))
            spatial_score += max(0.0, 1.0 - hausdorff / (max_r + max_c))
            valid_colors += 1

        bonus = (spatial_score / valid_colors) * 0.5 if valid_colors > 0 else 0.0
        return float(min(1.0, base_score * 0.5 + bonus))
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# MAIN EVALUATION — sequential (no batching on single MLX device)
# ---------------------------------------------------------------------------

def evaluate_arc_neurosymbolic(target_task=None):
    _init_backend()

    if target_task:
        task_files = [Path(target_task)]
    else:
        for candidate_root in [
            Path("./arc_data/training"),
            Path("/Users/aurascoper/Developer/arc_agi/arc_data/training"),
        ]:
            if candidate_root.exists():
                arc_root = candidate_root
                break
        else:
            print("ARC data directory not found. Place tasks in ./arc_data/training/")
            return

        task_files = hunter_seeker_arc_jsons(arc_root, MAX_TASKS_TO_EVALUATE)

    if not task_files:
        print("No ARC JSON tasks found.")
        return

    total_accuracy = 0.0
    candidate_temps = [0.0, 0.35, 0.75]

    for task_file in task_files:
        print(f"\n--- Task: {task_file.name} ---")
        with open(task_file) as f:
            task_data = json.load(f)

        prompt = build_prompt(task_data)
        cached_hints = build_task_hints(task_data)
        best_task_score = 0.0

        for ci in range(NUM_CANDIDATES):
            if best_task_score == 1.0:
                break
            temp = candidate_temps[min(ci, len(candidate_temps) - 1)]
            print(f"  Candidate {ci+1}/{NUM_CANDIDATES} (temp={temp})")

            code = extract_python_code(call_model(prompt, temperature=temp))
            passed_train, failures = try_code_on_task(code, task_data)

            for attempt in range(MAX_REFLECTIONS):
                if passed_train:
                    break
                print(f"    Reflection {attempt+1}/{MAX_REFLECTIONS}...")
                ref_prompt = build_reflection_prompt(task_data, code, failures, cached_hints)
                code = extract_python_code(call_model(ref_prompt, temperature=temp))
                passed_train, failures = try_code_on_task(code, task_data)

            passed_test, test_failures = try_code_on_task(code, task_data, evaluate_on_test=True)

            if passed_test:
                print("    TEST PASSED!")
                best_task_score = 1.0
            elif test_failures and len(test_failures[0]) >= 3:
                acc = calculate_pixel_accuracy(test_failures[0][1], test_failures[0][2])
                if acc > best_task_score:
                    best_task_score = acc
                print(f"    Failed. Pixel Accuracy: {best_task_score:.2f}")

        total_accuracy += best_task_score
        print(f"  Final Task Score: {best_task_score:.4f}")

    final_score = total_accuracy / len(task_files)
    print(f"\n=======================")
    print(f"Final Score: {final_score:.4f}")
    print(f"=======================")

    with open("metric.json", "w") as f:
        json.dump({"score": 1.0 - final_score}, f)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    evaluate_arc_neurosymbolic(target)
