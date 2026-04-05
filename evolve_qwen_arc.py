#!/usr/bin/env python3
"""
evolve_qwen_arc.py — Autoresearch outer loop for ARC-AGI DSL evolution.

Architecture (three nested loops):
  Autoresearch (this file) — hypothesis generation, literature grounding, experiment tracking
    └─ Codopt (middle) — beam-search mutation of dsl.py
         └─ TurboQuant-MLX (inner) — 3-bit KV compressed inference on M4

Per-round cycle:
  1. EVALUATE — three-tier task scoring (helper coverage, prompt gen, actual solve)
  2. DIAGNOSE — build context-enriched diagnostic prompt
  3. HYPOTHESIZE — MLX generates proposed DSL functions
  4. INJECT — validate + inject into dsl.py
  5. EXPERIMENT — codopt tournament (the autoresearch "experiment")
  6. ANALYZE — post-codopt full benchmark evaluation
  7. DECIDE — compare scores before/after
  8. RECORD — log hypothesis to JSONL
  9. COMMIT — git commit if improved

Usage:
  python evolve_qwen_arc.py                    # full evolution cycle (3 rounds)
  python evolve_qwen_arc.py --rounds 5         # 5 outer rounds
  python evolve_qwen_arc.py --diagnose-only    # just print diagnostics
  python evolve_qwen_arc.py --never-stop       # continuous evolution until killed
  python evolve_qwen_arc.py --tier3-tasks 3    # Tier 3 solve eval on N tasks (default 5)
"""

import json
import gc
import os
import re
import signal
import sys
import subprocess
import random
import threading
import traceback
from pathlib import Path
from datetime import datetime
from copy import deepcopy

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

WORKSPACE = Path(__file__).parent
DSL_PATH = WORKSPACE / "dsl.py"
ARC_DATA = WORKSPACE / "arc_agi_2_data" / "training"
METRIC_FILE = WORKSPACE / "metric.json"
RESULTS_DIR = WORKSPACE / "evolution_results"
HYPOTHESES_FILE = RESULTS_DIR / "hypotheses.jsonl"

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "deepseek-coder-v2")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MAX_NEW_TOKENS = int(os.environ.get("EVOLVE_MAX_TOKENS", "4096"))
TASKS_PER_DIAGNOSTIC = int(os.environ.get("TASKS_PER_DIAGNOSTIC", "5"))
OUTER_ROUNDS = int(os.environ.get("EVOLVE_ROUNDS", "3"))
CODOPT_BRANCHES = int(os.environ.get("CODOPT_BRANCHES", "3"))
CODOPT_TIME = int(os.environ.get("CODOPT_TIME", "120"))

# Fixed holdout set for consistent progress tracking (seed=2026, n=10)
HOLDOUT_SEED = 2026
HOLDOUT_SIZE = 10
HOLDOUT_FILE = RESULTS_DIR / "holdout_scores.jsonl"
SOLVE_COMMIT_THRESHOLD = float(os.environ.get("SOLVE_THRESHOLD", "0.85"))
TIER3_TASKS = int(os.environ.get("TIER3_TASKS", "2"))

# ---------------------------------------------------------------------------
# CRASH RESILIENCE — log fatal signals so overnight runs leave a trace
# ---------------------------------------------------------------------------

def _crash_handler(signum, frame):
    """Log crash info before dying so we know what killed overnight runs."""
    crash_file = RESULTS_DIR / "crash.log"
    try:
        with open(crash_file, "a") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"CRASH at {datetime.now().isoformat()} — signal {signum}\n")
            if frame:
                f.write("".join(traceback.format_stack(frame)))
            f.write(f"{'='*60}\n")
    except Exception:
        pass
    sys.exit(128 + signum)

for _sig in (signal.SIGTERM, signal.SIGHUP):
    signal.signal(_sig, _crash_handler)


# ---------------------------------------------------------------------------
# RESEARCH CONTEXT — curated ARC technique summaries for diagnostic grounding
# ---------------------------------------------------------------------------

HYPOTHESIS_TYPES_FILE = RESULTS_DIR / "hypothesis_type_scores.json"

# Mapping from keyword patterns in function names/hypotheses to type categories
HYPOTHESIS_TYPE_KEYWORDS = {
    "symmetry": ["symmetr", "mirror", "reflect", "flip"],
    "flood_fill": ["flood", "fill", "paint", "region"],
    "connected_components": ["connect", "component", "object", "blob", "segment"],
    "color_logic": ["color", "palette", "histogram", "frequency", "recolor"],
    "spatial_relation": ["spatial", "relation", "adjacen", "neighbor", "touching", "overlap"],
    "pattern_tile": ["pattern", "tile", "repeat", "stamp", "template", "period"],
    "transform_geom": ["rotate", "scale", "resize", "crop", "translate", "shift", "gravity", "drop", "slide"],
    "grid_decompose": ["decompos", "split", "quadrant", "strip", "partition", "separator"],
    "topology": ["topology", "layer", "occlu", "z_order", "stack"],
    "counting_arithmetic": ["count", "arith", "sum", "multiply", "sort", "rank", "max", "min"],
    "boundary_edge": ["boundar", "edge", "border", "contour", "outline", "perimete"],
    "masking_boolean": ["mask", "boolean", "xor", "intersection", "union", "overlay"],
}


def classify_hypothesis_type(hypothesis: str, func_names: list[str]) -> str:
    """Classify a hypothesis into a type category based on keywords."""
    text = (hypothesis + " " + " ".join(func_names)).lower()
    best_type, best_count = "other", 0
    for htype, keywords in HYPOTHESIS_TYPE_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > best_count:
            best_type, best_count = htype, hits
    return best_type


def _load_hypothesis_type_scores() -> dict:
    """Load hypothesis type win/loss tallies."""
    if HYPOTHESIS_TYPES_FILE.exists():
        try:
            return json.loads(HYPOTHESIS_TYPES_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_hypothesis_type_scores(scores: dict):
    HYPOTHESIS_TYPES_FILE.write_text(json.dumps(scores, indent=2))


def update_hypothesis_type_scores(htype: str, improved: bool):
    """Record a win or loss for a hypothesis type."""
    scores = _load_hypothesis_type_scores()
    if htype not in scores:
        scores[htype] = {"wins": 0, "losses": 0, "total": 0}
    scores[htype]["total"] += 1
    if improved:
        scores[htype]["wins"] += 1
    else:
        scores[htype]["losses"] += 1
    _save_hypothesis_type_scores(scores)


def format_hypothesis_type_guidance() -> str:
    """Format hypothesis type win rates for injection into diagnostic prompt."""
    scores = _load_hypothesis_type_scores()
    if not scores:
        return ""
    lines = ["## Hypothesis Type Track Record (win rate by category)"]
    sorted_types = sorted(scores.items(), key=lambda x: x[1]["wins"] / max(x[1]["total"], 1), reverse=True)
    for htype, s in sorted_types:
        total = s["total"]
        if total == 0:
            continue
        rate = s["wins"] / total
        bar = "+" * s["wins"] + "-" * s["losses"]
        lines.append(f"  {htype}: {rate:.0%} ({s['wins']}/{total}) [{bar}]")
    lines.append("PREFER types with higher win rates. AVOID types that consistently lose.")
    return "\n".join(lines)


RESEARCH_CONTEXT = """\
Key ARC-AGI solution techniques from the literature:

1. CONNECTED COMPONENTS: Identify connected regions of same-colored cells (4- or
   8-connected). Used for object isolation, counting, and spatial reasoning.

2. FLOOD FILL: Fill enclosed regions bounded by a specific color. Common in tasks
   involving containment, boundary detection, and region painting.

3. SYMMETRY DETECTION: Detect reflective (horizontal, vertical, diagonal) and
   rotational symmetry in grids. Many tasks involve completing symmetric patterns.

4. TOPOLOGICAL SORTING / LAYERING: Tasks involving occlusion or z-ordering require
   understanding which objects overlap and their relative positions.

5. PATTERN MATCHING / TEMPLATE DETECTION: Find recurring sub-grids (stamps, tiles)
   within larger grids. Used for tiling, repetition detection, and rule extraction.

6. COLOR HISTOGRAM / FREQUENCY ANALYSIS: Count color occurrences to detect dominant
   colors, rare colors (markers), or color-based rules (majority vote, XOR).

7. OBJECT RELATION GRAPHS: Build graphs of spatial relationships between objects
   (above, below, left, right, inside, touching) for compositional reasoning.

8. GRID DECOMPOSITION: Split grids into quadrants, strips, or tiles based on
   separators (lines of uniform color). Many tasks operate on sub-grids independently.

9. SCALING / RESAMPLING: Enlarge or shrink patterns by integer factors. Tasks
   frequently involve upscaling a small pattern to fill a larger grid.

10. GRAVITY / MOVEMENT SIMULATION: Move objects in a direction until they hit
    boundaries or other objects. Used in "drop", "slide", and "gravity" tasks."""

# ---------------------------------------------------------------------------
# LLM BACKEND — MLX (default) or Ollama fallback
# ---------------------------------------------------------------------------

EVOLVE_BACKEND = os.environ.get("EVOLVE_BACKEND", "mlx")  # "mlx" or "ollama"


def _generate_mlx(prompt: str, temperature: float, max_tokens: int | None) -> str:
    """Generate via MLX (reuses target_mlx_arc's loaded model + TurboQuant KV cache)."""
    from target_mlx_arc import call_model
    result = call_model(prompt, temperature=temperature, max_tokens=max_tokens or MAX_NEW_TOKENS)
    # Flush Metal cache between generations to prevent memory fragmentation
    try:
        import mlx.core as mx
        gc.collect()
        mx.clear_cache()
    except Exception:
        pass
    return result


def _generate_ollama(prompt: str, temperature: float, max_tokens: int | None) -> str:
    """Generate via Ollama HTTP API (fallback)."""
    import requests
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {
            "temperature": max(temperature, 1e-6),
            "num_predict": max_tokens or MAX_NEW_TOKENS,
        },
    }
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat", json=payload, timeout=600,
        )
        resp.raise_for_status()
        msg = resp.json().get("message", {})
        content = msg.get("content", "")
        if not content.strip() and msg.get("thinking"):
            content = msg["thinking"]
        return content
    except Exception as e:
        print(f"[evolve] Ollama error: {e}")
        return ""


def generate(prompt: str, temperature: float = 0.3, max_tokens: int | None = None) -> str:
    """Dispatch to MLX or Ollama based on EVOLVE_BACKEND."""
    if EVOLVE_BACKEND == "mlx":
        return _generate_mlx(prompt, temperature, max_tokens)
    return _generate_ollama(prompt, temperature, max_tokens)


# ---------------------------------------------------------------------------
# HYPOTHESIS TRACKING — JSONL experiment log
# ---------------------------------------------------------------------------

def log_hypothesis(round_num, hypothesis, source, proposed_functions,
                   metric_before, metric_after, solve_before, solve_after,
                   status, commit_hash=None, literature_hints=None):
    """Append one experiment record to hypotheses.jsonl."""
    RESULTS_DIR.mkdir(exist_ok=True)
    htype = classify_hypothesis_type(hypothesis, proposed_functions)
    improved = status == "keep"
    entry = {
        "round": round_num,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "hypothesis": hypothesis,
        "hypothesis_type": htype,
        "source": source,
        "proposed_functions": proposed_functions,
        "metric_before": round(metric_before, 4),
        "metric_after": round(metric_after, 4),
        "solve_before": round(solve_before, 4),
        "solve_after": round(solve_after, 4),
        "status": status,
        "commit": commit_hash,
    }
    if literature_hints:
        entry["literature_hints"] = literature_hints
        entry["hints_helped"] = improved
    with open(HYPOTHESES_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    # Cross-run learning: track which hypothesis types win/lose
    update_hypothesis_type_scores(htype, improved)
    if literature_hints:
        _update_hint_attribution(literature_hints, improved)


HINT_ATTRIBUTION_FILE = RESULTS_DIR / "hint_attribution.json"


def _update_hint_attribution(hints: list[str], improved: bool):
    """Track which literature hints led to improvements vs failures."""
    data = {}
    if HINT_ATTRIBUTION_FILE.exists():
        try:
            data = json.loads(HINT_ATTRIBUTION_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    for hint in hints:
        key = hint[:80]  # truncate for key
        if key not in data:
            data[key] = {"wins": 0, "losses": 0, "total": 0}
        data[key]["total"] += 1
        if improved:
            data[key]["wins"] += 1
        else:
            data[key]["losses"] += 1
    HINT_ATTRIBUTION_FILE.write_text(json.dumps(data, indent=2))


def load_recent_hypotheses(n=10):
    """Load last N hypothesis entries for prompt context."""
    if not HYPOTHESES_FILE.exists():
        return []
    lines = HYPOTHESES_FILE.read_text().strip().split("\n")
    entries = []
    for line in lines[-n:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return entries


# ---------------------------------------------------------------------------
# DSL EVALUATION — three-tier task scoring
# ---------------------------------------------------------------------------

CORE_FUNCTIONS = [
    "detect_background_color", "get_objects", "shape", "palette",
    "color_counts", "copy_grid", "rotate_cw", "mirror_h",
]


def grid_to_str(grid):
    if not grid or not isinstance(grid, list):
        return str(grid)
    return "\n".join("".join(str(c) for c in row) for row in grid)


def load_dsl_namespace():
    ns = {"grid_to_str": grid_to_str}
    exec(DSL_PATH.read_text(), ns)
    return ns


def _run_with_timeout(fn, args, timeout=5):
    """Run fn(*args) with a timeout. Returns (result, error_string_or_None)."""
    result = [None]
    error = [None]

    def _run():
        try:
            result[0] = fn(*args)
        except Exception as e:
            error[0] = str(e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        return None, "timeout"
    return result[0], error[0]


def _prepare_helper_ns(ns):
    """Exec HELPER_CODE_PREFIX into a helper namespace. Returns (helper_ns, error)."""
    import numpy as np
    helper_code = ns.get("HELPER_CODE_PREFIX", "")
    helper_ns = {"__builtins__": __builtins__, "np": np, "deepcopy": deepcopy}
    try:
        exec(helper_code, helper_ns)
        return helper_ns, None
    except Exception as e:
        return None, str(e)


def eval_task_tier1(helper_ns, task_data):
    """Tier 1: Test 8 core helper functions on task grids. Returns score 0.0-1.0."""
    grid = task_data["train"][0]["input"]
    passed = 0
    for fname in CORE_FUNCTIONS:
        fn = helper_ns.get(fname)
        if fn is None:
            continue
        result, err = _run_with_timeout(fn, (grid,), timeout=2)
        if err is None and result is not None:
            passed += 1
    return passed / len(CORE_FUNCTIONS)


def eval_task_tier2(ns, task_data):
    """Tier 2: Test build_prompt() produces valid output. Returns score 0.0-1.0."""
    bp = ns.get("build_prompt")
    if bp is None:
        return 0.0
    result, err = _run_with_timeout(bp, (task_data,), timeout=5)
    if err is not None or result is None:
        return 0.0
    if len(str(result)) < 50:
        return 0.0
    return 1.0


def _fallback_prompt(task_data):
    """Simple prompt when build_prompt() is unavailable."""
    prompt = "ARC puzzle.\n"
    for i, pair in enumerate(task_data["train"]):
        prompt += (
            f"Ex{i+1} In:\n{grid_to_str(pair['input'])}\n"
            f"Out:\n{grid_to_str(pair['output'])}\n\n"
        )
    prompt += "Output ONLY python code `def transform(input_grid):`\n```python\n"
    return prompt


# ---------------------------------------------------------------------------
# COLOR CANONICALIZATION — removes color permutation as confounding variable
# ---------------------------------------------------------------------------

def _build_color_mapping(task_data):
    """Build a frequency-ordered color mapping from training data.

    Returns (forward_map, inverse_map) where forward_map remaps original→canonical
    and inverse_map remaps canonical→original.  Canonical order: most frequent color
    across ALL training grids = 0, next = 1, etc.
    """
    from collections import Counter
    freq = Counter()
    for pair in task_data.get("train", []):
        for row in pair.get("input", []):
            freq.update(row)
        for row in pair.get("output", []):
            freq.update(row)
    # Sort by descending frequency, then ascending value for ties
    sorted_colors = sorted(freq.keys(), key=lambda c: (-freq[c], c))
    forward = {orig: canon for canon, orig in enumerate(sorted_colors)}
    inverse = {canon: orig for orig, canon in forward.items()}
    return forward, inverse


def _remap_grid(grid, color_map):
    """Remap all cell values in a grid using color_map dict."""
    return [[color_map.get(c, c) for c in row] for row in grid]


def _canonicalize_task(task_data):
    """Canonicalize colors in a task. Returns (canon_task, inverse_map).

    The LLM sees frequency-ordered colors (0=most common, 1=next, ...).
    After solving, inverse_map converts canonical output back to originals.
    """
    from copy import deepcopy
    forward, inverse = _build_color_mapping(task_data)
    # Identity mapping — skip canonicalization overhead
    if all(k == v for k, v in forward.items()):
        return task_data, None
    canon = deepcopy(task_data)
    for pair in canon.get("train", []):
        pair["input"] = _remap_grid(pair["input"], forward)
        pair["output"] = _remap_grid(pair["output"], forward)
    for pair in canon.get("test", []):
        pair["input"] = _remap_grid(pair["input"], forward)
        if "output" in pair:
            pair["output"] = _remap_grid(pair["output"], forward)
    return canon, inverse


def _decanonicalize_grid(grid, inverse_map):
    """Map canonical colors back to originals. No-op if inverse_map is None."""
    if inverse_map is None or not grid:
        return grid
    return _remap_grid(grid, inverse_map)


SUCCESSFUL_PROGRAMS_PATH = WORKSPACE / "evolution_results" / "successful_programs.jsonl"
LORA_STATE_PATH = RESULTS_DIR / "lora_state.json"
LORA_ADAPTERS_DIR = RESULTS_DIR / "lora_adapters"
LORA_MIN_PROGRAMS = 15
LORA_MIN_ROUNDS_BETWEEN = 5
LORA_SKIP_FIRST_ROUNDS = 3
LORA_MAX_KEPT_ADAPTERS = 3


def _log_successful_program(task_name: str, task_data: dict, code: str, prompt: str):
    """Append a successful transform() to JSONL for future LoRA fine-tuning."""
    import time as _time
    entry = {
        "task_name": task_name,
        "timestamp": _time.time(),
        "code": code,
        "prompt": prompt,
        "num_train": len(task_data.get("train", [])),
        "num_test": len(task_data.get("test", [])),
    }
    try:
        with open(SUCCESSFUL_PROGRAMS_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # never break the evolution loop for logging


NEAR_MISS_THRESHOLD = 0.92  # Minimum mean pixel accuracy for near-miss logging


def _log_near_miss_program(task_name: str, task_data: dict, code: str,
                           prompt: str, pixel_accuracy: float):
    """Log a high-accuracy near-miss transform() for LoRA training data."""
    import time as _time
    entry = {
        "task_name": task_name,
        "timestamp": _time.time(),
        "code": code,
        "prompt": prompt,
        "num_train": len(task_data.get("train", [])),
        "num_test": len(task_data.get("test", [])),
        "source": "near_miss",
        "pixel_accuracy": pixel_accuracy,
    }
    try:
        with open(SUCCESSFUL_PROGRAMS_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _truncate_traceback(tb: str, max_lines: int = 8) -> str:
    """Keep last N lines of traceback (the most informative part)."""
    lines = tb.strip().split("\n")
    if len(lines) <= max_lines:
        return tb.strip()
    return "...\n" + "\n".join(lines[-max_lines:])


def solve_task_single(task_data, task_name="unknown"):
    """Tier 3: One-shot solve attempt via MLX. Returns (pixel_accuracy, traces).

    Uses color canonicalization: remaps colors by frequency so the LLM sees
    cleaner patterns (0=most common, 1=next, ...). Evaluation uses the same
    canonical space, so no inverse mapping is needed for correctness.
    """
    from target_mlx_arc import try_code_on_task, extract_python_code, calculate_pixel_accuracy

    # Canonicalize colors — LLM sees frequency-ordered colors
    canon_data, _inv = _canonicalize_task(task_data)

    ns = load_dsl_namespace()
    bp = ns.get("build_prompt")
    if bp:
        prompt_result, prompt_err = _run_with_timeout(bp, (canon_data,), timeout=10)
        prompt = prompt_result if (not prompt_err and prompt_result) else _fallback_prompt(canon_data)
    else:
        prompt = _fallback_prompt(canon_data)

    response = generate(prompt, temperature=0.0, max_tokens=1024)
    code = extract_python_code(response)
    if not code or "def transform" not in code:
        return 0.0, [{"task_name": task_name, "failure_type": "NO_TRANSFORM",
                       "error_message": f"LLM response had no transform ({len(response)} chars)"}]

    # Evaluate against canonical data (both input and expected output are canonical)
    passed, failures = try_code_on_task(code, canon_data, abpr_trace=True)
    if passed:
        # Log successful program for future LoRA fine-tuning
        _log_successful_program(task_name, task_data, code, prompt)
        return 1.0, []

    traces = []
    for idx, fail in enumerate(failures):
        inp, expected, predicted, err_msg = fail[0], fail[1], fail[2], fail[3]
        tb = fail[4] if len(fail) > 4 else None
        abpr = fail[5] if len(fail) > 5 else None
        ftype = "CRASH" if predicted is None else "WRONG_ANSWER"
        pa = calculate_pixel_accuracy(expected, predicted) if predicted else 0.0
        trace_entry = {
            "task_name": task_name,
            "failure_type": ftype,
            "error_message": err_msg[:200] if err_msg else None,
            "stack_trace": _truncate_traceback(tb) if tb else None,
            "pixel_accuracy": pa,
            "input_shape": (len(inp), len(inp[0])) if isinstance(inp, list) and inp else (0, 0),
            "output_shape": (len(expected), len(expected[0])) if isinstance(expected, list) and expected else (0, 0),
            "predicted_shape": (len(predicted), len(predicted[0])) if isinstance(predicted, list) and predicted else None,
        }
        if abpr:
            trace_entry["abpr_trace"] = abpr[:10]  # limit to 10 calls
        traces.append(trace_entry)
    best_pa = max(t["pixel_accuracy"] for t in traces) if traces else 0.0
    # Log near-miss for LoRA (mean accuracy across all pairs, no crashes)
    if traces:
        mean_pa = sum(t["pixel_accuracy"] for t in traces) / len(traces)
        if mean_pa >= NEAR_MISS_THRESHOLD and all(t["failure_type"] == "WRONG_ANSWER" for t in traces):
            _log_near_miss_program(task_name, task_data, code, prompt, mean_pa)
    # Collect synthetic task from failed program (TransCoder-style)
    try:
        from synthetic_tasks import collect_from_beam_failure
        if collect_from_beam_failure(task_data, code, task_name):
            print(f"  [synthetic] {task_name}: collected training pair")
    except Exception:
        pass
    return best_pa, traces


ENHANCED_SOLVE = True  # Enable H2 (D4 symmetry) + H3 (MDL composition)


def solve_task_enhanced(task_data, task_name="unknown"):
    """Enhanced solve: H3 composition search -> H2 D4 ensemble -> fallback single.

    Returns (pixel_accuracy, traces) -- same interface as solve_task_single.
    """
    if not ENHANCED_SOLVE:
        return solve_task_single(task_data, task_name)

    # Phase 1: H3 -- fast composition search (no LLM, ~2-5s)
    try:
        from mdl_compose import compose_search
        from target_mlx_arc import try_code_on_task
        ns = load_dsl_namespace()
        canon_data, _inv = _canonicalize_task(task_data)
        code = compose_search(canon_data, ns, timeout=5.0)
        if code:
            passed, _ = try_code_on_task(code, canon_data)
            if passed:
                _log_successful_program(task_name, task_data, code, "composition_search")
                print(f"  [H3] {task_name}: SOLVED by composition")
                return 1.0, []
    except Exception as e:
        print(f"  [H3] {task_name}: error {e}")

    # Phase 2: H2 -- D4 symmetry ensemble (up to 8 LLM calls, ~40-80s)
    try:
        from d4_ensemble import solve_task_d4
        score, traces = solve_task_d4(task_data, task_name)
        return score, traces
    except Exception as e:
        print(f"  [H2] {task_name}: error {e}")

    # Fallback: original single solve
    return solve_task_single(task_data, task_name)


def find_failing_tasks(sample_size=50, tier3_count=None, seed=42):
    """Three-tier evaluation. Returns list of dicts with path, task_data, scores, category."""
    if tier3_count is None:
        tier3_count = TIER3_TASKS

    ns = load_dsl_namespace()
    helper_ns, helper_err = _prepare_helper_ns(ns)
    if helper_ns is None:
        print(f"[evolve] WARNING: Helper exec failed: {helper_err}")
        helper_ns = {}

    task_files = list(ARC_DATA.glob("*.json"))
    if not task_files:
        print(f"[evolve] No tasks found in {ARC_DATA}")
        return []

    random.seed(seed)
    sample = random.sample(task_files, min(sample_size, len(task_files)))

    # Tier 1 + Tier 2 on all tasks
    scored = []
    for tf in sample:
        with open(tf) as f:
            task_data = json.load(f)
        t1 = eval_task_tier1(helper_ns, task_data)
        t2 = eval_task_tier2(ns, task_data)
        combined = t1 * 0.6 + t2 * 0.4
        scored.append((tf, task_data, t1, t2, combined))

    # Sort ascending — worst tasks first
    scored.sort(key=lambda x: x[4])

    # Failing = combined < 1.0
    failing_tuples = [(tf, td, t1, t2, c) for tf, td, t1, t2, c in scored if c < 1.0]
    perfect = len(scored) - len(failing_tuples)
    print(f"[evolve] Tier 1+2: {len(failing_tuples)} imperfect, {perfect} perfect out of {len(sample)}")

    results = []

    if failing_tuples:
        # Tier 3 on worst N tasks with tier1+tier2 failures (requires model)
        tier3_targets = failing_tuples[:tier3_count]
        if tier3_targets:
            print(f"[evolve] Tier 3: solving {len(tier3_targets)} worst tasks...")
            for tf, td, t1, t2, combined in tier3_targets:
                try:
                    solve_score, traces = solve_task_enhanced(td, task_name=tf.stem)
                except Exception as e:
                    print(f"  [tier3] {tf.name}: error {e}")
                    solve_score, traces = 0.0, [{"task_name": tf.stem, "failure_type": "CRASH", "error_message": str(e)}]
                category = "CRASH" if t1 < 1.0 else ("PROMPT_FAIL" if t2 < 1.0 else "WRONG_ANSWER")
                results.append({
                    "path": tf, "task_data": td, "category": category,
                    "tier1": t1, "tier2": t2, "tier3": solve_score, "combined": combined,
                    "traces": traces,
                })
                print(f"  [tier3] {tf.name}: {category} t1={t1:.2f} t2={t2:.2f} t3={solve_score:.2f}")

        # Include remaining failures without tier3 score
        tier3_paths = {r["path"] for r in results}
        for tf, td, t1, t2, combined in failing_tuples:
            if tf not in tier3_paths:
                category = "CRASH" if t1 < 1.0 else ("PROMPT_FAIL" if t2 < 1.0 else "UNTESTED")
                results.append({
                    "path": tf, "task_data": td, "category": category,
                    "tier1": t1, "tier2": t2, "tier3": None, "combined": combined,
                })
    else:
        # All tier1+tier2 perfect — the bottleneck is tier3 (LLM solve).
        # Evaluate tier3 on a sample to find tasks the LLM still can't solve.
        tier3_targets = scored[:tier3_count]
        print(f"[evolve] Tier 1+2 all perfect. Tier 3: solving {len(tier3_targets)} tasks to find LLM failures...")
        for tf, td, t1, t2, combined in tier3_targets:
            try:
                solve_score, traces = solve_task_enhanced(td, task_name=tf.stem)
            except Exception as e:
                print(f"  [tier3] {tf.name}: error {e}")
                solve_score, traces = 0.0, [{"task_name": tf.stem, "failure_type": "CRASH", "error_message": str(e)}]
            results.append({
                "path": tf, "task_data": td, "category": "SOLVE_FAIL",
                "tier1": t1, "tier2": t2, "tier3": solve_score, "combined": combined,
                "traces": traces,
            })
            print(f"  [tier3] {tf.name}: SOLVE_FAIL t1={t1:.2f} t2={t2:.2f} t3={solve_score:.2f}")

        # Only return tasks the LLM actually failed on (tier3 < 1.0)
        results = [r for r in results if r["tier3"] < 1.0]
        # Sort by tier3 ascending so worst failures come first
        results.sort(key=lambda r: r["tier3"])
        if results:
            print(f"[evolve] Found {len(results)} tier3 failures out of {len(tier3_targets)} evaluated")
        else:
            print(f"[evolve] All {len(tier3_targets)} evaluated tasks also pass tier3 — truly perfect!")

    return results


def compute_solve_score(failing_results):
    """Average Tier 3 solve score across tasks that were tested."""
    tier3_scores = [r["tier3"] for r in failing_results if r["tier3"] is not None]
    if not tier3_scores:
        return 0.0
    return sum(tier3_scores) / len(tier3_scores)


def _get_holdout_tasks():
    """Return a fixed set of task files for consistent progress measurement."""
    task_files = sorted(ARC_DATA.glob("*.json"))
    if not task_files:
        return []
    rng = random.Random(HOLDOUT_SEED)
    return rng.sample(task_files, min(HOLDOUT_SIZE, len(task_files)))


def compute_holdout_score():
    """Evaluate tier3 solve on a FIXED set of tasks. Returns (mean_score, per_task_scores).

    Unlike compute_solve_score which uses random tasks each round, this always
    evaluates the same tasks, making progress observable across rounds.
    """
    holdout = _get_holdout_tasks()
    if not holdout:
        return 0.0, {}

    ns = load_dsl_namespace()
    per_task = {}
    for tf in holdout:
        with open(tf) as f:
            task_data = json.load(f)
        try:
            score, _ = solve_task_single(task_data, task_name=tf.stem)  # no D4 on holdout (too slow)
        except Exception:
            score = 0.0
        per_task[tf.stem] = round(score, 4)

    mean = sum(per_task.values()) / len(per_task) if per_task else 0.0
    return round(mean, 4), per_task


def log_holdout_score(round_num, mean_score, per_task):
    """Append holdout evaluation to tracking file."""
    entry = {
        "round": round_num,
        "ts": datetime.now().isoformat()[:19],
        "holdout_mean": mean_score,
        "per_task": per_task,
    }
    with open(HOLDOUT_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[holdout] Score: {mean_score:.4f} ({len(per_task)} tasks)")


# ---------------------------------------------------------------------------
# DIAGNOSTIC PROMPTS — enriched with research context + hypothesis history
# ---------------------------------------------------------------------------

DIAGNOSTIC_PROMPT = """\
/no_think
You are an ARC-AGI DSL engineer. Given failing tasks, output ONLY Python functions. No analysis, no explanation — just code.

Current DSL: {num_functions} functions. Do NOT duplicate existing functions.

## Known Techniques
{research_context}

## Existing (last 50 signatures, do NOT duplicate)
{existing_signatures}

## Previous Experiments ([-] = no improvement, [+] = improved)
{hypothesis_history}

## BLACKLIST — DO NOT propose functions similar to these (already tried, didn't help):
{blacklist}

## Failure Distribution: {category_summary}

## Failing Tasks
{task_descriptions}

## What went WRONG (execution traces from failed solve attempts)
{execution_traces}

IMPORTANT: Study the input/output pairs carefully. Each task has a UNIQUE transformation rule.
Do NOT propose generic mirror/pattern/tile functions. Analyze what SPECIFIC operation maps each input to its output.

OUTPUT EXACTLY 3-5 new Python functions in ```python blocks. Each function:
- Takes `grid: list[list[int]]` as first arg, returns `list[list[int]]`
- Is self-contained (only stdlib + numpy)
- Does ONE transformation relevant to the failing tasks above
- Has a one-line docstring
- Must be DIFFERENT from blacklisted approaches

```python
def function_name(grid: list[list[int]]) -> list[list[int]]:
    \"\"\"One-line description.\"\"\"
    import numpy as np
    # implementation
    return result
```

START WITH ```python IMMEDIATELY. No preamble."""


PROMPT_FIX_DIAGNOSTIC = """\
/no_think
You are an ARC-AGI DSL engineer. The bottleneck is `build_prompt()` — it crashes or returns empty on {prompt_fail_pct}% of tasks.
Your job: fix `analyze_task_deeply()` and `build_prompt()` to handle more task types without crashing.

Current `build_prompt` calls `analyze_task_deeply(task_data)` and `find_exact_programs(task_data)`.
These crash on tasks with unusual grid sizes, color distributions, or transformation types.

## Current build_prompt code (abridged)
{build_prompt_code}

## Current analyze_task_deeply code (abridged)
{analyze_code}

## Example tasks where build_prompt CRASHES (tier2=0.00)
{crash_examples}

## Previous Experiments ([-] = no improvement, [+] = improved)
{hypothesis_history}

FIX the crash by outputting a REPLACEMENT `analyze_task_deeply` function and/or `build_prompt` function.
The fix must:
- Handle all grid sizes (1x1 to 30x30)
- Not crash on empty grids or unusual color distributions
- Wrap risky operations in try/except
- Return a valid string even on edge cases

Output the fixed function(s) in ```python blocks.

```python
def analyze_task_deeply(task_data: dict) -> str:
    \"\"\"Analyze an ARC task and return a text description of patterns found.\"\"\"
    # robust implementation
    return analysis_text
```

START WITH ```python IMMEDIATELY. No preamble."""


def _targeted_literature_hints(categories: dict) -> str:
    """Query Semantic Scholar for papers relevant to current failure categories.

    Cherry-pick 1 from AutoResearchClaw: instead of generic literature scans
    only on stagnation, do targeted queries every round based on what's failing.
    Results are cached to evolution_results/literature_cache.json with 24h TTL.
    """
    import urllib.request
    import urllib.parse

    # Map failure categories to search queries
    CATEGORY_QUERIES = {
        "CRASH": "program synthesis robust grid transformation error handling",
        "PROMPT_FAIL": "visual reasoning prompt engineering grid puzzle",
        "WRONG_ANSWER": "ARC abstraction reasoning inductive program synthesis",
        "SOLVE_FAIL": "ARC-AGI program induction grid transformation",
        "UNTESTED": None,  # skip
    }

    # Pick query based on dominant failure category
    if not categories:
        return "", []
    dominant = max(categories, key=categories.get)
    query = CATEGORY_QUERIES.get(dominant)
    if not query:
        return "", []

    # Check cache (24h TTL)
    cache_file = RESULTS_DIR / "literature_cache.json"
    cache = {}
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    cache_key = dominant
    if cache_key in cache:
        cached = cache[cache_key]
        age_hours = (datetime.now().timestamp() - cached.get("ts", 0)) / 3600
        if age_hours < 24 and cached.get("hints"):
            return cached["hints"], cached.get("hint_ids", [])

    # Query Semantic Scholar (free, no API key needed, 100 req/5min)
    try:
        params = urllib.parse.urlencode({
            "query": query,
            "limit": 5,
            "fields": "title,abstract,year",
            "year": "2024-2026",
        })
        url = f"https://api.semanticscholar.org/graph/v1/paper/search?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "arc-agi-evolution/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"  [literature] Semantic Scholar query failed: {e}")
        return "", []

    papers = data.get("data", [])
    if not papers:
        return "", []

    lines = [f"## Targeted Literature (for {dominant} failures, from Semantic Scholar)"]
    hint_ids = []
    for p in papers[:3]:
        title = p.get("title", "")
        abstract = (p.get("abstract") or "")[:200]
        year = p.get("year", "")
        if abstract:
            lines.append(f"- **{title}** ({year}): {abstract}...")
            hint_ids.append(f"s2:{dominant}:{title[:60]}")
    lines.append("Consider techniques from these papers when designing new helper functions.")

    hints = "\n".join(lines)

    # Cache result
    cache[cache_key] = {"ts": datetime.now().timestamp(), "hints": hints, "hint_ids": hint_ids}
    try:
        RESULTS_DIR.mkdir(exist_ok=True)
        cache_file.write_text(json.dumps(cache, indent=2))
    except Exception:
        pass

    return hints, hint_ids


def _extract_function_signatures(helper_code):
    """Extract 'def name(args):' lines from HELPER_CODE_PREFIX."""
    return re.findall(r"(def \w+\([^)]*\))", helper_code)


def _format_hypothesis_history(entries):
    """Format recent hypotheses for prompt context."""
    if not entries:
        return "No previous experiments."
    lines = []
    for e in entries:
        improved = e["metric_after"] > e["metric_before"]
        icon = "+" if improved else "-"
        funcs = ", ".join(e.get("proposed_functions", [])[:3])
        htype = e.get("hypothesis_type", "")
        type_tag = f" [{htype}]" if htype else ""
        lines.append(
            f"  [{icon}] Round {e['round']}{type_tag}: {e['hypothesis'][:80]} "
            f"({funcs}) metric {e['metric_before']:.3f}->{e['metric_after']:.3f}"
        )
    return "\n".join(lines)


def _build_blacklist(entries):
    """Extract tried function name prefixes to avoid repetition."""
    tried = set()
    for e in entries:
        for fname in e.get("proposed_functions", []):
            # Extract the core concept: extract_and_mirror_patterns -> extract_mirror_pattern
            words = fname.replace("_", " ").split()
            # Keep 2-3 word combos as blacklist keys
            if len(words) >= 2:
                tried.add("_".join(words[:3]))
    return sorted(tried)


def _count_stagnant_streak(entries):
    """Count consecutive stagnant rounds at the end.
    Uses the status field (which accounts for beam search wins) rather than
    just metric_before/after (both 1.0 when base benchmark is at ceiling).
    """
    streak = 0
    for e in reversed(entries):
        if e.get("status", "stagnant") != "keep":
            streak += 1
        else:
            break
    return streak


def build_diagnostic_prompt(failing_results):
    """Build enriched diagnostic prompt from failing tasks."""
    ns = load_dsl_namespace()
    helper_code = ns.get("HELPER_CODE_PREFIX", "")
    num_functions = helper_code.count("\ndef ") + 1

    # Task descriptions with failure categories (computed first for relevance ranking)
    shown = [r for r in failing_results if r["tier3"] is not None][:TASKS_PER_DIAGNOSTIC]
    if not shown:
        shown = failing_results[:TASKS_PER_DIAGNOSTIC]

    # Function signatures — ranked by relevance to failing tasks
    all_sigs = _extract_function_signatures(helper_code)
    try:
        from dsl_recognition import get_relevant_signatures
        task_grids = [r["task_data"] for r in shown]
        ranked = get_relevant_signatures(helper_code, task_grids, n=50)
        sig_lines = [f"  {s}" for s in ranked]
        if len(all_sigs) > 50:
            sig_lines.insert(0, f"  ... ({len(all_sigs) - 50} more, ranked by task relevance) ...")
    except Exception:
        # Fallback to last-50 if recognition model fails
        sig_lines = [f"  {s}" for s in all_sigs[-50:]]
        if len(all_sigs) > 50:
            sig_lines.insert(0, f"  ... ({len(all_sigs) - 50} more) ...")
    sig_text = "\n".join(sig_lines) if sig_lines else "  (none)"

    # Hypothesis history + blacklist
    recent = load_recent_hypotheses(10)
    history_text = _format_hypothesis_history(recent)
    blacklist = _build_blacklist(recent)
    blacklist_text = ", ".join(blacklist) if blacklist else "(none yet)"

    # Category distribution for awareness
    categories = {}
    for r in failing_results:
        categories[r["category"]] = categories.get(r["category"], 0) + 1
    category_summary = ", ".join(f"{k}: {v}" for k, v in sorted(categories.items()))

    task_descs = []
    for r in shown:
        td = r["task_data"]
        desc = f"### Task: {r['path'].name} [{r['category']}]\n"
        desc += f"Scores: tier1={r['tier1']:.2f} tier2={r['tier2']:.2f}"
        if r["tier3"] is not None:
            desc += f" tier3(solve)={r['tier3']:.2f}"
        desc += "\n"
        for i, pair in enumerate(td["train"][:2]):
            inp, out = pair["input"], pair["output"]
            desc += f"Train {i+1} Input ({len(inp)}x{len(inp[0])}):\n{grid_to_str(inp)}\n"
            desc += f"Train {i+1} Output ({len(out)}x{len(out[0])}):\n{grid_to_str(out)}\n"
        task_descs.append(desc)

    # Build execution trace summaries from ABPR data
    trace_descs = []
    for r in shown:
        traces = r.get("traces", [])
        if not traces:
            continue
        for t in traces[:2]:  # max 2 traces per task
            tdesc = f"- {t.get('task_name', '?')}: {t['failure_type']}"
            if t.get("error_message"):
                tdesc += f"\n    Error: {t['error_message']}"
            if t.get("stack_trace"):
                indented = t["stack_trace"].replace("\n", "\n      ")
                tdesc += f"\n    Traceback:\n      {indented}"
            if t["failure_type"] == "WRONG_ANSWER":
                tdesc += f"\n    Pixel accuracy: {t.get('pixel_accuracy', 0):.2f}"
                tdesc += f"\n    Expected shape: {t.get('output_shape')}, Got: {t.get('predicted_shape')}"
            if t.get("abpr_trace"):
                tdesc += "\n    ABPR call trace:"
                for step in t["abpr_trace"]:
                    call = step.get("call", "?")
                    shape = step.get("result_shape", "?")
                    err = step.get("error", "")
                    tdesc += f"\n      → {call}() → shape={shape}" + (f" ERROR: {err}" if err else "")
            trace_descs.append(tdesc)

    # Cherry-pick 2: Inject hypothesis type win/loss guidance
    type_guidance = format_hypothesis_type_guidance()
    research = RESEARCH_CONTEXT.strip()
    if type_guidance:
        research = research + "\n\n" + type_guidance

    # Cherry-pick 1: Targeted literature search based on failure categories
    lit_hints, lit_hint_ids = _targeted_literature_hints(categories)
    if lit_hints:
        research = research + "\n\n" + lit_hints

    prompt = DIAGNOSTIC_PROMPT.format(
        num_functions=num_functions,
        research_context=research,
        existing_signatures=sig_text,
        hypothesis_history=history_text,
        blacklist=blacklist_text,
        category_summary=category_summary,
        task_descriptions="\n".join(task_descs),
        execution_traces="\n".join(trace_descs) if trace_descs else "(no traces captured)",
    )
    return prompt, lit_hint_ids


def build_prompt_fix_diagnostic(failing_results, prompt_fail_pct):
    """Build diagnostic prompt focused on fixing build_prompt/analyze_task_deeply crashes."""
    dsl_code = DSL_PATH.read_text()

    # Extract analyze_task_deeply source (up to 80 lines)
    analyze_match = re.search(
        r"(def analyze_task_deeply\(.*?\n(?:(?:    .*|)\n){0,80})",
        dsl_code, re.MULTILINE,
    )
    analyze_code = analyze_match.group(1)[:3000] if analyze_match else "(not found)"

    # Extract build_prompt source (up to 50 lines)
    bp_match = re.search(
        r"(def build_prompt\(.*?\n(?:(?:    .*|)\n){0,50})",
        dsl_code, re.MULTILINE,
    )
    build_prompt_code = bp_match.group(1)[:2000] if bp_match else "(not found)"

    # Show PROMPT_FAIL tasks
    prompt_fails = [r for r in failing_results if r["category"] == "PROMPT_FAIL"][:3]
    crash_examples = []
    for r in prompt_fails:
        td = r["task_data"]
        desc = f"### {r['path'].name}\n"
        pair = td["train"][0]
        desc += f"Input ({len(pair['input'])}x{len(pair['input'][0])}): "
        desc += f"{len(td['train'])} train pairs\n"
        desc += f"Grid snippet:\n{grid_to_str(pair['input'][:5])}\n"
        crash_examples.append(desc)

    recent = load_recent_hypotheses(10)
    history_text = _format_hypothesis_history(recent)

    return PROMPT_FIX_DIAGNOSTIC.format(
        prompt_fail_pct=int(prompt_fail_pct),
        build_prompt_code=build_prompt_code,
        analyze_code=analyze_code,
        crash_examples="\n".join(crash_examples) if crash_examples else "(none)",
        hypothesis_history=history_text,
    )


def get_prompt_score():
    """Read current prompt_score from metric.json."""
    try:
        with open(METRIC_FILE) as f:
            return json.load(f).get("prompt_score", None)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# FUNCTION EXTRACTION & VALIDATION
# ---------------------------------------------------------------------------

def extract_functions_from_response(response: str) -> list[str]:
    """Extract Python function definitions from LLM response.

    Handles truncated responses (no closing ```) and functions with nested defs.
    """
    functions = []
    # Match code blocks, including truncated ones that hit max_tokens
    blocks = re.findall(r"```python\s*(.*?)(?:\s*```|\Z)", response, re.DOTALL)
    if not blocks:
        blocks = re.findall(r"```\s*(.*?)(?:\s*```|\Z)", response, re.DOTALL)

    for block in blocks:
        # Split only on top-level (unindented) def — preserves nested defs
        parts = re.split(r"(?=\ndef )", block)
        for part in parts:
            part = part.strip()
            if part.startswith("def "):
                healed = _heal_truncated(part)
                if healed:
                    functions.append(healed)
    return functions


def _heal_truncated(func_code: str) -> str | None:
    """If func_code doesn't compile (e.g. truncated), trim lines until it does."""
    try:
        compile(func_code, "<proposed>", "exec")
        return func_code
    except SyntaxError:
        pass
    lines = func_code.split('\n')
    for i in range(len(lines) - 1, 0, -1):
        candidate = '\n'.join(lines[:i]).rstrip()
        if not candidate:
            continue
        try:
            compile(candidate, "<proposed>", "exec")
            return candidate
        except SyntaxError:
            continue
    return None


def validate_function(func_code: str) -> bool:
    """Check if a proposed function is valid Python and doesn't shadow existing names."""
    try:
        compile(func_code, "<proposed>", "exec")
    except SyntaxError:
        return False

    ns = load_dsl_namespace()
    helper_code = ns.get("HELPER_CODE_PREFIX", "")

    func_name = re.match(r"def\s+(\w+)", func_code)
    if func_name and func_name.group(1) in helper_code:
        print(f"  [skip] {func_name.group(1)} already exists in DSL")
        return False
    return True


# ---------------------------------------------------------------------------
# DSL MUTATION — inject new functions
# ---------------------------------------------------------------------------

def inject_functions_into_dsl(new_functions: list[str]) -> str:
    """Append validated new functions to HELPER_CODE_PREFIX in dsl.py."""
    dsl_code = DSL_PATH.read_text()

    closing_marker = "'''"
    last_close = dsl_code.rfind(closing_marker)
    if last_close == -1:
        print("[evolve] ERROR: Cannot find HELPER_CODE_PREFIX closing marker")
        return dsl_code

    injection = "\n\n# --- EVOLVED FUNCTIONS (auto-generated) ---\n"
    for func in new_functions:
        injection += "\n" + func + "\n"

    # Invalidate recognition model cache so new functions are indexed next round
    try:
        from dsl_recognition import invalidate_cache
        invalidate_cache()
    except ImportError:
        pass

    return dsl_code[:last_close] + injection + "\n" + dsl_code[last_close:]


# ---------------------------------------------------------------------------
# BEAM SEARCH INNER LOOP (local Ollama, replaces codopt)
# ---------------------------------------------------------------------------

def run_codopt_round():
    """Run one local beam-search tournament round on dsl.py via Ollama.

    Returns (ok: bool, improved: bool, blended_score: float).
    - ok: beam search ran without errors
    - improved: a candidate beat the baseline (dsl.py was updated)
    - blended_score: the winning score (includes tier 3 solve component)
    """
    from beam_search_local import run_beam_search, BeamConfig

    config = BeamConfig(
        rounds=1,
        branch_factor=CODOPT_BRANCHES,
        max_agents=4,
        time_limit=CODOPT_TIME,
        model=os.environ.get("BEAM_MODEL", "mlx"),
        workspace=WORKSPACE,
    )

    print(f"[evolve] Running local beam search: model={config.model} "
          f"branch={config.branch_factor} time={config.time_limit}s...")

    try:
        result = run_beam_search(config)
    except Exception as e:
        print(f"[evolve] beam search failed: {e}")
        return False, False, 0.0

    if result is None:
        print("[evolve] beam search returned no result")
        return False, False, 0.0

    if result.score is not None:
        # A winner beat baseline if its node_id is not "baseline"
        beam_improved = result.node_id != "baseline"
        print(f"[evolve] beam search complete: best={result.node_id} score={result.score:.4f}"
              f"{' [IMPROVED]' if beam_improved else ''}")
        return True, beam_improved, result.score

    print("[evolve] beam search: no valid candidates")
    return False, False, 0.0


# ---------------------------------------------------------------------------
# GIT COMMIT — auto-commit winning mutations
# ---------------------------------------------------------------------------

def _get_model_path():
    """Lazily fetch MODEL_PATH from target_mlx_arc (avoids top-level import)."""
    try:
        from target_mlx_arc import MODEL_PATH
        return MODEL_PATH
    except ImportError:
        return "unknown"

def git_commit_if_improved(round_num, pre_score, post_score, hypothesis="",
                           solve_before=0.0, solve_after=0.0):
    """Compare scores and commit if improved. Returns (new_score, commit_hash).

    At ceiling (both scores ≥ 0.999), commits based on solve improvement instead.
    """
    at_ceiling = pre_score >= 0.999 and post_score >= 0.999
    if at_ceiling:
        if solve_after <= solve_before:
            print(f"[evolve] At ceiling, no solve improvement: "
                  f"{solve_before:.4f}->{solve_after:.4f}")
            return pre_score, None
    elif post_score <= pre_score:
        print(f"[evolve] No improvement: metric {pre_score:.4f}->{post_score:.4f}")
        return pre_score, None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    label = (f"solve {solve_before:.4f} -> {solve_after:.4f}" if at_ceiling
             else f"{pre_score:.4f} -> {post_score:.4f}")
    msg = (
        f"evolve: round {round_num} results [keep] score={post_score:.4f}\n\n"
        f"Solve score: {solve_before:.4f} -> {solve_after:.4f}\n"
        f"Hypothesis: {hypothesis[:200]}\n"
        f"Model: {_get_model_path()}\n"
        f"Timestamp: {timestamp}"
    )

    subprocess.run(["git", "add", "dsl.py"], cwd=str(WORKSPACE))
    result = subprocess.run(
        ["git", "commit", "-m", msg],
        cwd=str(WORKSPACE), capture_output=True, text=True,
    )
    commit_hash = None
    if result.returncode == 0:
        m = re.search(r"\[[\w/\-]+ ([0-9a-f]+)\]", result.stdout)
        if m:
            commit_hash = m.group(1)
    print(f"[evolve] COMMITTED: metric {pre_score:.4f}->{post_score:.4f}, "
          f"solve {solve_before:.4f}->{solve_after:.4f}")
    return max(post_score, pre_score), commit_hash


# ---------------------------------------------------------------------------
# LORA SELF-DISTILLATION ORCHESTRATION
# ---------------------------------------------------------------------------

def _load_lora_state() -> dict:
    """Load LoRA training state from JSON file."""
    if LORA_STATE_PATH.exists():
        try:
            return json.loads(LORA_STATE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "last_training_round": 0,
        "programs_at_last_training": 0,
        "active_adapter": None,
        "adapter_history": [],
        "post_lora_scores": [],
    }


def _save_lora_state(state: dict):
    """Persist LoRA state to JSON."""
    LORA_STATE_PATH.write_text(json.dumps(state, indent=2))


def _count_successful_programs() -> int:
    """Count lines in successful_programs.jsonl."""
    if not SUCCESSFUL_PROGRAMS_PATH.exists():
        return 0
    with open(SUCCESSFUL_PROGRAMS_PATH) as f:
        return sum(1 for line in f if line.strip())


def should_trigger_lora_training(round_num: int, state: dict) -> bool:
    """Check if LoRA training should run this round.

    Counts real programs fully and synthetic tasks at 0.5x weight toward
    the LORA_MIN_PROGRAMS threshold (synthetic are easier, worth less).
    """
    if round_num <= LORA_SKIP_FIRST_ROUNDS:
        return False
    rounds_since = round_num - state.get("last_training_round", 0)
    if rounds_since < LORA_MIN_ROUNDS_BETWEEN:
        return False
    # Count real programs
    prog_count = _count_successful_programs()
    new_progs = prog_count - state.get("programs_at_last_training", 0)
    # Count synthetic tasks (each counts as 0.5 toward threshold)
    try:
        from synthetic_tasks import get_synthetic_stats
        synth_count = get_synthetic_stats().get("total", 0)
        synth_at_last = state.get("synthetic_at_last_training", 0)
        new_synth = synth_count - synth_at_last
        effective_new = new_progs + new_synth * 0.5
    except Exception:
        effective_new = new_progs
    return effective_new >= LORA_MIN_PROGRAMS


def run_lora_training_cycle(round_num: int, state: dict) -> dict:
    """Orchestrate: unload model → train subprocess → validate → reload."""
    from target_mlx_arc import unload_model, reload_with_adapter
    import time as _time

    timestamp = _time.strftime("%Y%m%d_%H%M%S")
    adapter_dir = LORA_ADAPTERS_DIR / timestamp

    print(f"[lora] Starting training cycle (adapter: {timestamp})")

    # Unload model to free GPU memory
    unload_model()

    # Run training as subprocess for memory isolation
    try:
        result = subprocess.run(
            [sys.executable, str(WORKSPACE / "lora_train.py"),
             "--data", str(SUCCESSFUL_PROGRAMS_PATH),
             "--output", str(adapter_dir)],
            capture_output=True, text=True, timeout=1800,
            cwd=str(WORKSPACE),
        )
        print(result.stdout[-2000:] if result.stdout else "")
        if result.stderr:
            print(f"[lora] stderr: {result.stderr[-500:]}")
    except subprocess.TimeoutExpired:
        print("[lora] Training timed out (30min limit)")
        reload_with_adapter(state.get("active_adapter"))
        return state
    except Exception as e:
        print(f"[lora] Training error: {e}")
        reload_with_adapter(state.get("active_adapter"))
        return state

    if result.returncode == 0:
        # Adapter validated — reload with it
        adapter_path = str(adapter_dir)
        reload_with_adapter(adapter_path)

        # Update state
        state["last_training_round"] = round_num
        state["programs_at_last_training"] = _count_successful_programs()
        state["active_adapter"] = adapter_path
        # Track synthetic count for threshold gating
        try:
            from synthetic_tasks import get_synthetic_stats
            state["synthetic_at_last_training"] = get_synthetic_stats().get("total", 0)
        except Exception:
            pass
        state["adapter_history"].append(timestamp)
        state["post_lora_scores"] = []  # reset regression tracking

        # Create 'active' symlink
        active_link = LORA_ADAPTERS_DIR / "active"
        if active_link.is_symlink() or active_link.exists():
            active_link.unlink()
        active_link.symlink_to(adapter_dir.name)

        # Prune old adapters (keep last N)
        if len(state["adapter_history"]) > LORA_MAX_KEPT_ADAPTERS:
            old = state["adapter_history"][:-LORA_MAX_KEPT_ADAPTERS]
            for old_ts in old:
                old_dir = LORA_ADAPTERS_DIR / old_ts
                if old_dir.exists():
                    import shutil
                    shutil.rmtree(old_dir, ignore_errors=True)
                    print(f"[lora] Pruned old adapter: {old_ts}")
            state["adapter_history"] = state["adapter_history"][-LORA_MAX_KEPT_ADAPTERS:]

        print(f"[lora] Adapter {timestamp} active. History: {state['adapter_history']}")
    else:
        # Adapter rejected — reload previous (or base model)
        print(f"[lora] Adapter rejected (exit {result.returncode}). Reverting.")
        reload_with_adapter(state.get("active_adapter"))

    _save_lora_state(state)
    return state


def check_lora_regression(state: dict, solve_score: float) -> dict:
    """Track post-LoRA solve scores; rollback if 2 consecutive regressions."""
    if not state.get("active_adapter"):
        return state

    scores = state.get("post_lora_scores", [])
    scores.append(solve_score)
    state["post_lora_scores"] = scores

    # Check for 2 consecutive regressions
    if len(scores) >= 3:
        if scores[-1] < scores[-3] and scores[-2] < scores[-3]:
            print(f"[lora] REGRESSION detected: {scores[-3]:.4f} → {scores[-2]:.4f} → {scores[-1]:.4f}")
            # Rollback to previous adapter or base model
            history = state.get("adapter_history", [])
            if len(history) >= 2:
                prev = str(LORA_ADAPTERS_DIR / history[-2])
                print(f"[lora] Rolling back to previous adapter: {history[-2]}")
                from target_mlx_arc import reload_with_adapter
                reload_with_adapter(prev)
                state["active_adapter"] = prev
                state["adapter_history"].pop()
            else:
                print("[lora] Rolling back to base model (no previous adapter)")
                from target_mlx_arc import reload_with_adapter
                reload_with_adapter(None)
                state["active_adapter"] = None
                state["adapter_history"] = []
            state["post_lora_scores"] = []
            _save_lora_state(state)

    return state


# ---------------------------------------------------------------------------
# MAIN AUTORESEARCH LOOP
# ---------------------------------------------------------------------------

def evolve(rounds=None, diagnose_only=False, never_stop=False, tier3_tasks=None, no_lora=False):
    if rounds is None:
        rounds = OUTER_ROUNDS
    if tier3_tasks is not None:
        global TIER3_TASKS
        TIER3_TASKS = tier3_tasks

    lora_enabled = not no_lora
    lora_state = _load_lora_state() if lora_enabled else None

    RESULTS_DIR.mkdir(exist_ok=True)

    # Baseline score
    print("[evolve] Getting baseline score...")
    subprocess.run(
        ["python3", str(WORKSPACE / "benchmark_dsl.py")],
        cwd=str(WORKSPACE), capture_output=True, timeout=120,
    )
    try:
        with open(METRIC_FILE) as f:
            current_score = json.load(f).get("score", 0.0)
    except Exception:
        current_score = 0.0
    print(f"[evolve] Baseline score: {current_score:.4f}")

    # Resume round numbering from hypotheses.jsonl (survives process restarts)
    round_num = 0
    if HYPOTHESES_FILE.exists():
        try:
            with open(HYPOTHESES_FILE) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entry = json.loads(line)
                        round_num = max(round_num, entry.get("round", 0))
        except (json.JSONDecodeError, OSError):
            pass
    if round_num > 0:
        print(f"[evolve] Resuming from round {round_num + 1} (found {round_num} in hypotheses.jsonl)")

    while True:
        round_num += 1
        if not never_stop and round_num > rounds:
            break

        label = f"{round_num}" + ("" if never_stop else f"/{rounds}")
        print(f"\n{'='*60}")
        print(f"  AUTORESEARCH ROUND {label}")
        print(f"{'='*60}")

        # --- 0. LORA CHECK ---
        if lora_enabled and should_trigger_lora_training(round_num, lora_state):
            print(f"\n[0/9] LORA — self-distillation training triggered")
            lora_state = run_lora_training_cycle(round_num, lora_state)
        elif lora_enabled:
            prog_count = _count_successful_programs()
            new_progs = prog_count - (lora_state.get("programs_at_last_training", 0))
            rounds_since = round_num - lora_state.get("last_training_round", 0)
            print(f"\n[0/9] LORA — skip (new_programs={new_progs}, rounds_since={rounds_since})")

        # --- 1. EVALUATE ---
        print("\n[1/9] EVALUATE — three-tier task scoring...")
        failing = find_failing_tasks(tier3_count=TIER3_TASKS, seed=round_num)
        if not failing:
            print("[evolve] No failing tasks (all tiers pass) — DSL may be perfect!")
            if not never_stop:
                break
            # Re-seed with a different sample — different tasks may still fail tier3
            failing = find_failing_tasks(tier3_count=TIER3_TASKS, seed=round_num * 1000 + datetime.now().microsecond)
            if not failing:
                print("[evolve] Still perfect after re-seed. Sleeping 60s before next round...")
                import time
                time.sleep(60)
                continue

        solve_before = compute_solve_score(failing)
        print(f"[evolve] Pre-round solve score: {solve_before:.4f}")

        # --- 2. DIAGNOSE ---
        # Decide mode: fix build_prompt (prompt_score bottleneck) vs new primitives
        prompt_score = get_prompt_score()
        prompt_fail_count = sum(1 for r in failing if r["category"] == "PROMPT_FAIL")
        prompt_fail_pct = prompt_fail_count / max(len(failing), 1) * 100

        # Use prompt-fix mode on even rounds when prompt_score < 0.5 and most failures are PROMPT_FAIL
        use_prompt_fix_mode = (
            prompt_score is not None
            and prompt_score < 0.5
            and prompt_fail_pct > 60
            and round_num % 2 == 0
        )

        injected_hint_ids = []
        if use_prompt_fix_mode:
            print(f"\n[2/9] DIAGNOSE — PROMPT-FIX MODE (prompt_score={prompt_score:.2f}, {prompt_fail_pct:.0f}% PROMPT_FAIL)...")
            diag_prompt = build_prompt_fix_diagnostic(failing, prompt_fail_pct)
        else:
            print(f"\n[2/9] DIAGNOSE — analyzing {len(failing)} failures...")
            diag_prompt, injected_hint_ids = build_diagnostic_prompt(failing)

        diag_path = RESULTS_DIR / f"round{round_num}_diagnostic.txt"
        diag_path.write_text(diag_prompt)

        if diagnose_only:
            print(f"[evolve] Diagnostic saved to {diag_path}")
            print(diag_prompt[:2000])
            continue

        # --- 3. HYPOTHESIZE ---
        recent = load_recent_hypotheses(10)
        stagnant_streak = _count_stagnant_streak(recent)
        temp = min(0.6 + stagnant_streak * 0.1, 0.9)  # 0.6 -> 0.7 -> 0.8 -> 0.9
        mode_label = "PROMPT-FIX" if use_prompt_fix_mode else "PRIMITIVES"
        print(f"\n[3/9] HYPOTHESIZE — generating with {EVOLVE_BACKEND} (temp={temp:.2f}, stagnant={stagnant_streak}, mode={mode_label})...")

        # Literature hints are now injected every round via _targeted_literature_hints()
        # in build_diagnostic_prompt(). On high stagnation, also add the broader scan hints.
        if stagnant_streak >= 5:
            try:
                from literature_scan import load_hints
                lit_hints = load_hints(max_hints=5)
                if lit_hints:
                    diag_prompt = diag_prompt.replace(
                        "## Failing Tasks",
                        f"{lit_hints}\n\n## Failing Tasks",
                    )
                    injected_hint_ids.append("broad:stagnation_hints")
                    print(f"  [literature] Extra broad hints injected (stagnant={stagnant_streak})")
            except ImportError:
                pass

        # Prompt-fix needs more tokens (replacing whole functions with nested helpers)
        gen_max = MAX_NEW_TOKENS * 3 if use_prompt_fix_mode else None
        response = generate(diag_prompt, temperature=temp, max_tokens=gen_max)
        resp_path = RESULTS_DIR / f"round{round_num}_response.txt"
        resp_path.write_text(response)
        print(f"[evolve] Response ({len(response)} chars) saved to {resp_path}")

        # --- 4. INJECT ---
        print("\n[4/9] INJECT — extracting and validating functions...")
        new_functions = extract_functions_from_response(response)

        if use_prompt_fix_mode:
            # In prompt-fix mode, replace existing analyze_task_deeply / build_prompt
            replacement_funcs = {}
            for func in new_functions:
                m = re.match(r"def\s+(\w+)", func)
                if m and m.group(1) in ("analyze_task_deeply", "build_prompt"):
                    try:
                        compile(func, "<proposed>", "exec")
                        replacement_funcs[m.group(1)] = func
                    except SyntaxError:
                        print(f"  [skip] {m.group(1)} has syntax error")
            func_names = list(replacement_funcs.keys())
            print(f"[evolve] Prompt-fix replacements: {func_names}")
            hypothesis = f"Fix {', '.join(func_names)}" if func_names else "No valid prompt fixes"

            if replacement_funcs:
                dsl_code = DSL_PATH.read_text()
                for fname, new_code in replacement_funcs.items():
                    # Replace the existing function in dsl.py
                    pattern = re.compile(
                        rf"(def {fname}\(.*?\n)"       # function signature
                        rf"((?:    .*\n|[ \t]*\n)*)",   # indented body
                        re.MULTILINE,
                    )
                    if pattern.search(dsl_code):
                        # Use lambda to prevent re.sub from interpreting \n etc in replacement
                        dsl_code = pattern.sub(lambda m: new_code + "\n\n", dsl_code, count=1)
                        print(f"  [replaced] {fname}")
                    else:
                        print(f"  [skip] {fname} not found in dsl.py for replacement")
                DSL_PATH.write_text(dsl_code)
        else:
            # Normal mode: append new primitives
            validated = [f for f in new_functions if validate_function(f)]
            func_names = []
            rejected_task_specific = []
            rejected_garbage = []
            # Garbage name patterns — generic/placeholder names that indicate
            # the model failed to produce task-aware hypotheses
            GARBAGE_NAME_PATTERNS = [
                r"^function_name$", r"^func\d*$", r"^new_function_name$",
                r"^replace_specific_values_with_\w+$",
                r"^replace_\w+_with_\w+$",  # e.g. replace_twos_with_eights
                r"^replace_value_\w+$",
            ]
            for v in validated:
                m = re.match(r"def\s+(\w+)", v)
                if m:
                    name = m.group(1)
                    # Reject task-specific functions (overfit to one puzzle)
                    if re.search(r"[0-9a-f]{8}", name) or re.search(r"task_\w+|specific_to_", name):
                        rejected_task_specific.append(name)
                        continue
                    # Reject garbage/placeholder names
                    if any(re.match(pat, name) for pat in GARBAGE_NAME_PATTERNS):
                        rejected_garbage.append(name)
                        continue
                    func_names.append(name)
            if rejected_task_specific:
                # Remove overfitting functions from validated list
                validated = [v for v in validated
                             if not any(rn in v for rn in rejected_task_specific)]
                print(f"[evolve] Rejected task-specific: {rejected_task_specific}")
            if rejected_garbage:
                validated = [v for v in validated
                             if not any(rn in v for rn in rejected_garbage)]
                print(f"[evolve] Rejected garbage names: {rejected_garbage}")
            print(f"[evolve] Proposed {len(new_functions)}, valid {len(validated)}: {func_names}")
            hypothesis = f"Add {', '.join(func_names)}" if func_names else "No valid functions proposed"

            if validated:
                mutated_dsl = inject_functions_into_dsl(validated)
                DSL_PATH.write_text(mutated_dsl)
                print(f"[evolve] Injected {len(validated)} functions into dsl.py")

        # Verify tests still pass (both modes)
        if func_names:
            test_result = subprocess.run(
                [sys.executable, str(WORKSPACE / "tests_dsl.py")],
                cwd=str(WORKSPACE), capture_output=True, text=True,
            )
            if test_result.returncode != 0:
                print(f"[evolve] WARNING: Tests failed after injection (rc={test_result.returncode}), reverting")
                print(f"  [test stdout] {(test_result.stdout or '').strip()[:800]}")
                print(f"  [test stderr] {(test_result.stderr or '').strip()[:800]}")
                subprocess.run(["git", "checkout", "dsl.py"], cwd=str(WORKSPACE))
                log_hypothesis(
                    round_num, hypothesis, "prompt-fix" if use_prompt_fix_mode else "diagnostic",
                    func_names, current_score, current_score, solve_before, solve_before, "crash",
                    literature_hints=injected_hint_ids or None,
                )
                continue

        # --- 5. EXPERIMENT ---
        print("\n[5/9] EXPERIMENT — running codopt tournament...")
        pre_score = current_score
        codopt_ok, beam_improved, beam_score = run_codopt_round()

        # Read post-codopt fast score
        try:
            with open(METRIC_FILE) as f:
                post_score = json.load(f).get("score", 0.0)
        except Exception:
            post_score = pre_score

        # --- 6. ANALYZE ---
        print("\n[6/9] ANALYZE — post-codopt full benchmark...")
        env = os.environ.copy()
        env["BENCHMARK_MODE"] = "full"
        subprocess.run(
            ["python3", str(WORKSPACE / "benchmark_dsl.py")],
            cwd=str(WORKSPACE), capture_output=True, timeout=300, env=env,
        )
        try:
            with open(METRIC_FILE) as f:
                full_metric = json.load(f)
                post_score = full_metric.get("score", post_score)
        except Exception:
            pass

        # Use the beam search blended score (includes tier 3 solve) as solve_after
        solve_after = beam_score if codopt_ok else 0.0

        print(f"[evolve] Results: metric {pre_score:.4f}->{post_score:.4f}, "
              f"solve {solve_before:.4f}->{solve_after:.4f}")

        # --- 6b. HOLDOUT — fixed-task progress measurement ---
        holdout_mean, holdout_per_task = compute_holdout_score()
        log_holdout_score(round_num, holdout_mean, holdout_per_task)

        # --- 7. DECIDE ---
        # Decision uses TWO signals:
        #   1. beam_improved — codopt tournament found a winner on blended score
        #   2. solve_after >= threshold — absolute tier3 quality gate (default 0.85)
        # NOTE: We no longer compare solve_after vs solve_before (too noisy due to
        # random task sampling). Instead, use absolute threshold + beam winner signal.
        if post_score >= 0.999:
            above_threshold = solve_after >= SOLVE_COMMIT_THRESHOLD
            if beam_improved or above_threshold:
                improved = True
                status = "keep"
                reason = "beam winner" if beam_improved else f"solve≥{SOLVE_COMMIT_THRESHOLD}"
                print(f"\n[7/9] DECIDE — {status} ({reason}: solve={solve_after:.4f}, holdout={holdout_mean:.4f})")
            else:
                improved = False
                status = "stagnant"
                print(f"\n[7/9] DECIDE — {status} (solve={solve_after:.4f}<{SOLVE_COMMIT_THRESHOLD}, holdout={holdout_mean:.4f})")
        else:
            improved = post_score > pre_score
            status = "keep" if improved else "stagnant"
            print(f"\n[7/9] DECIDE — {status} (metric {pre_score:.4f}->{post_score:.4f})")

        # --- 8. RECORD ---
        commit_hash = None
        if codopt_ok and improved:
            # --- 9. COMMIT ---
            print(f"\n[8/9] RECORD + [9/9] COMMIT...")
            current_score, commit_hash = git_commit_if_improved(
                round_num, pre_score, post_score, hypothesis,
                solve_before, solve_after,
            )
        else:
            print(f"\n[8/9] RECORD (no commit)")

        log_hypothesis(
            round_num, hypothesis, "prompt-fix" if use_prompt_fix_mode else "diagnostic",
            func_names, pre_score, post_score, solve_before, solve_after,
            status, commit_hash, literature_hints=injected_hint_ids or None,
        )

        # --- LoRA regression check ---
        if lora_enabled and lora_state:
            lora_state = check_lora_regression(lora_state, solve_after)

        # --- AUTO-PUSH — sync results to GitHub for remote monitoring ---
        try:
            subprocess.run(
                ["git", "add", "evolution_results/", "dsl.py", ".gitignore"],
                cwd=str(WORKSPACE), capture_output=True,
            )
            subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=str(WORKSPACE), capture_output=True,
            ).returncode != 0 and subprocess.run(
                ["git", "commit", "-m",
                 f"evolve: round {round_num} results [{status}] score={current_score:.4f}"],
                cwd=str(WORKSPACE), capture_output=True,
            )
            push_result = subprocess.run(
                ["git", "push", "--quiet"],
                cwd=str(WORKSPACE), capture_output=True, text=True, timeout=30,
            )
            if push_result.returncode == 0:
                print(f"[evolve] Pushed round {round_num} to GitHub")
            else:
                print(f"[evolve] Push failed: {push_result.stderr.strip()[:200]}")
        except Exception as e:
            print(f"[evolve] Auto-push error: {e}")

        print(f"\n[evolve] Round {round_num} done. Score: {current_score:.4f} [{status}]")

        # Periodic dead function pruning (every 10 rounds)
        if round_num % 10 == 0:
            try:
                from dsl_prune import prune_dsl
                removed = prune_dsl(dry_run=False)
                if removed > 0:
                    print(f"[evolve] Pruned {removed} dead functions from dsl.py")
            except Exception as e:
                print(f"[evolve] Prune skipped: {e}")

    print(f"\n{'='*60}")
    print(f"  EVOLUTION COMPLETE — Final Score: {current_score:.4f}")
    print(f"{'='*60}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Autoresearch outer loop for ARC-AGI DSL evolution",
    )
    parser.add_argument("--rounds", type=int, default=None, help="Number of outer rounds")
    parser.add_argument("--diagnose-only", action="store_true", help="Only print diagnostics")
    parser.add_argument("--never-stop", action="store_true", help="Run continuously until killed")
    parser.add_argument("--tier3-tasks", type=int, default=None, help="Tier 3 solve task count")
    parser.add_argument("--no-lora", action="store_true", help="Disable LoRA self-distillation")
    args = parser.parse_args()
    evolve(
        rounds=args.rounds,
        diagnose_only=args.diagnose_only,
        never_stop=args.never_stop,
        tier3_tasks=args.tier3_tasks,
        no_lora=args.no_lora,
    )
