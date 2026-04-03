"""
target_kaggle_arc.py — CUDA/A100 port of target_qwen_arc.py
Targets Colab Pro A100 (80 GB) and Kaggle T4/A100 notebooks.

Backend priority:
  1. vLLM  — batched, fastest on A100 (install: pip install vllm)
  2. HF transformers + torch — universal fallback

Offline-compatible: set MODEL_PATH to a local dir (Kaggle dataset or cached HF).
No MLX, no HTTP server, no Docker.

Usage:
  python target_kaggle_arc.py                  # evaluate MAX_TASKS_TO_EVALUATE tasks
  python target_kaggle_arc.py path/to/task.json # single task
"""

import json
import re
import os
import sys
import random
import threading
import numpy as np
from pathlib import Path
from copy import deepcopy

# ---------------------------------------------------------------------------
# CONFIGURATION — edit these for your environment
# ---------------------------------------------------------------------------

# HuggingFace model ID or local path.
# Kaggle: mount the model dataset and point here, e.g. "/kaggle/input/qwen25-7b-instruct"
# Colab:  leave as HF ID; will auto-download on first run (needs internet).
MODEL_PATH = os.environ.get(
    "ARC_MODEL_PATH",
    "Qwen/Qwen2.5-14B-Instruct",   # swap to Qwen2.5-14B-Instruct on A100 for best results
)

MAX_TASKS_TO_EVALUATE = 10        # auto-increased by run_swarm.sh when score hits 0.0
MAX_REFLECTIONS = 3
NUM_CANDIDATES = 10

# Generation limits — A100 can handle longer sequences; T4 keep at 512
MAX_NEW_TOKENS = int(os.environ.get("ARC_MAX_TOKENS", "1024"))

# ---------------------------------------------------------------------------
# BACKEND: vLLM (preferred) or HF transformers (fallback)
# ---------------------------------------------------------------------------

_llm = None          # vLLM LLM instance
_hf_model = None     # HF model
_hf_tokenizer = None # HF tokenizer
_backend = None      # "vllm" | "hf"


def _init_backend():
    global _llm, _hf_model, _hf_tokenizer, _backend

    # --- Try vLLM first ---
    try:
        from vllm import LLM, SamplingParams  # noqa: F401
        import torch
        gpu_mem = 0.90  # fraction of GPU memory vLLM may use

        dtype = "bfloat16" if torch.cuda.is_available() else "float32"
        print(f"[backend] Initialising vLLM ({MODEL_PATH}, dtype={dtype})...", flush=True)
        _llm = LLM(
            model=MODEL_PATH,
            dtype=dtype,
            gpu_memory_utilization=gpu_mem,
            max_model_len=4096,
            trust_remote_code=True,
        )
        _backend = "vllm"
        print("[backend] vLLM ready.", flush=True)
        return
    except Exception as e:
        print(f"[backend] vLLM unavailable ({e}), falling back to HF transformers.", flush=True)

    # --- HF transformers fallback ---
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM

        dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[backend] Loading {MODEL_PATH} via HF transformers on {device} ({dtype})...", flush=True)

        _hf_tokenizer = AutoTokenizer.from_pretrained(
            MODEL_PATH,
            trust_remote_code=True,
            padding_side="left",
        )
        _hf_model = AutoModelForCausalLM.from_pretrained(
            MODEL_PATH,
            torch_dtype=dtype,
            device_map="auto",
            trust_remote_code=True,
        )
        _hf_model.eval()
        _backend = "hf"
        print(f"[backend] HF transformers ready on {device}.", flush=True)
        return
    except Exception as e:
        raise RuntimeError(f"No usable inference backend found. vLLM and HF both failed: {e}")


def _generate_batch(prompts: list[str], temperature: float) -> list[str]:
    """Generate responses for a batch of prompts. Returns list of response strings."""
    if _backend is None:
        _init_backend()

    if _backend == "vllm":
        from vllm import SamplingParams
        params = SamplingParams(
            temperature=max(temperature, 1e-6),  # vLLM requires > 0
            max_tokens=MAX_NEW_TOKENS,
            stop=["```\n\n", "```\n#", "\n\nif __name__"],
        )
        outputs = _llm.generate(prompts, params)
        return [o.outputs[0].text for o in outputs]

    if _backend == "hf":
        import torch
        results = []
        # HF: process one at a time to keep memory predictable (batch if RAM allows)
        for prompt in prompts:
            inputs = _hf_tokenizer(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=3072,
            ).to(_hf_model.device)
            with torch.no_grad():
                output_ids = _hf_model.generate(
                    **inputs,
                    max_new_tokens=MAX_NEW_TOKENS,
                    temperature=temperature if temperature > 0 else None,
                    do_sample=temperature > 0,
                    pad_token_id=_hf_tokenizer.eos_token_id,
                )
            new_ids = output_ids[0][inputs["input_ids"].shape[1]:]
            results.append(_hf_tokenizer.decode(new_ids, skip_special_tokens=True))
        return results

    raise RuntimeError(f"Unknown backend: {_backend}")


def call_model(prompt: str, temperature: float = 0.0) -> str:
    """Single-prompt wrapper around _generate_batch."""
    responses = _generate_batch([prompt], temperature)
    text = responses[0] if responses else ""
    print(f"[model] {len(text)} chars. Preview: {repr(text[:120])}", flush=True)
    return text


# ---------------------------------------------------------------------------
# ARC helpers (identical to target_qwen_arc.py)
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

    # Fallback
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


def try_code_on_task(code: str, task_data: dict, evaluate_on_test=False):
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
            return False, [(pairs[0]["input"], pairs[0]["output"], None, "No 'transform' function")]

        for pair in pairs:
            try:
                pred = run_with_timeout(transform_fn, (pair["input"],), timeout_sec=5)
                pred_list = [list(row) for row in pred] if pred else []
                out_list = [list(row) for row in pair["output"]]
                if pred_list != out_list:
                    failures.append((pair["input"], pair["output"], pred_list, None))
            except Exception as e:
                failures.append((pair["input"], pair["output"], None, str(e)))

    except Exception as e:
        if pairs:
            failures.append((pairs[0]["input"], pairs[0]["output"], None, str(e)))
        else:
            failures.append(("", "", None, str(e)))

    return len(failures) == 0, failures


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
# MAIN EVALUATION — batched candidate generation per task
# ---------------------------------------------------------------------------

def evaluate_arc_neurosymbolic(target_task=None):
    # Warm up the backend once before the eval loop
    _init_backend()

    if target_task:
        task_files = [Path(target_task)]
    else:
        # Kaggle: /kaggle/input/arc-agi-3/arc-agi-3/data/training/
        # Colab / local: ./arc_data/training/
        for candidate_root in [
            Path("/kaggle/input/arc-agi-3/arc-agi-3/data/training"),
            Path("/kaggle/input/arc-prize-2026/arc-agi-3/data/training"),
            Path("./arc_data/training"),
        ]:
            if candidate_root.exists():
                arc_root = candidate_root
                break
        else:
            print("Critical: ARC data directory not found. Set arc_data/training or Kaggle dataset path.")
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

        # ---- Batch all NUM_CANDIDATES initial prompts at once (vLLM shines here) ----
        temps = [candidate_temps[min(i, len(candidate_temps) - 1)] for i in range(NUM_CANDIDATES)]
        unique_temps = sorted(set(temps))

        candidate_codes = []
        for temp in unique_temps:
            count = temps.count(temp)
            responses = _generate_batch([prompt] * count, temperature=temp)
            candidate_codes.extend(extract_python_code(r) for r in responses)

        for ci, code in enumerate(candidate_codes):
            if best_task_score == 1.0:
                break
            temp = temps[ci]
            print(f"  Candidate {ci+1}/{NUM_CANDIDATES} (temp={temp})")

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
    evaluate_arc_neurosymbolic(None)
