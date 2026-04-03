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
import os
import re
import sys
import subprocess
import random
import threading
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

MODEL_PATH = os.environ.get("ARC_MODEL_PATH", "mlx-community/Qwen3.5-9B-4bit")
MAX_NEW_TOKENS = int(os.environ.get("EVOLVE_MAX_TOKENS", "2048"))
TASKS_PER_DIAGNOSTIC = int(os.environ.get("TASKS_PER_DIAGNOSTIC", "5"))
OUTER_ROUNDS = int(os.environ.get("EVOLVE_ROUNDS", "3"))
CODOPT_BRANCHES = int(os.environ.get("CODOPT_BRANCHES", "3"))
CODOPT_TIME = int(os.environ.get("CODOPT_TIME", "120"))
TIER3_TASKS = int(os.environ.get("TIER3_TASKS", "5"))

USE_TURBOQUANT = os.environ.get("USE_TURBOQUANT", "1") == "1"
TQ_BITS = int(os.environ.get("TQ_BITS", "3"))
TQ_FP16_LAYERS = int(os.environ.get("TQ_FP16_LAYERS", "4"))

# ---------------------------------------------------------------------------
# RESEARCH CONTEXT — curated ARC technique summaries for diagnostic grounding
# ---------------------------------------------------------------------------

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
# MLX BACKEND
# ---------------------------------------------------------------------------

_model = None
_tokenizer = None


def init_mlx():
    global _model, _tokenizer
    if _model is not None:
        return

    from mlx_lm import load
    print(f"[evolve] Loading {MODEL_PATH}...", flush=True)
    _model, _tokenizer = load(MODEL_PATH)

    if USE_TURBOQUANT:
        print(f"[evolve] KV quantization: {TQ_BITS}-bit (mlx-lm built-in)", flush=True)

    print("[evolve] MLX ready.", flush=True)


def generate(prompt: str, temperature: float = 0.3) -> str:
    init_mlx()
    from mlx_lm import generate as mlx_generate
    from mlx_lm.sample_utils import make_sampler

    kwargs = {
        "max_tokens": MAX_NEW_TOKENS,
        "sampler": make_sampler(temp=max(temperature, 1e-6)),
    }
    if USE_TURBOQUANT:
        kwargs["kv_bits"] = TQ_BITS

    return mlx_generate(_model, _tokenizer, prompt=prompt, **kwargs)


# ---------------------------------------------------------------------------
# HYPOTHESIS TRACKING — JSONL experiment log
# ---------------------------------------------------------------------------

def log_hypothesis(round_num, hypothesis, source, proposed_functions,
                   metric_before, metric_after, solve_before, solve_after,
                   status, commit_hash=None):
    """Append one experiment record to hypotheses.jsonl."""
    RESULTS_DIR.mkdir(exist_ok=True)
    entry = {
        "round": round_num,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "hypothesis": hypothesis,
        "source": source,
        "proposed_functions": proposed_functions,
        "metric_before": round(metric_before, 4),
        "metric_after": round(metric_after, 4),
        "solve_before": round(solve_before, 4),
        "solve_after": round(solve_after, 4),
        "status": status,
        "commit": commit_hash,
    }
    with open(HYPOTHESES_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


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


def solve_task_single(task_data):
    """Tier 3: One-shot solve attempt via MLX. Returns pixel accuracy 0.0-1.0."""
    from target_mlx_arc import try_code_on_task, extract_python_code, calculate_pixel_accuracy

    ns = load_dsl_namespace()
    bp = ns.get("build_prompt")
    if bp:
        prompt_result, prompt_err = _run_with_timeout(bp, (task_data,), timeout=10)
        prompt = prompt_result if (not prompt_err and prompt_result) else _fallback_prompt(task_data)
    else:
        prompt = _fallback_prompt(task_data)

    response = generate(prompt, temperature=0.0)
    code = extract_python_code(response)
    if not code or "def transform" not in code:
        return 0.0

    passed, failures = try_code_on_task(code, task_data)
    if passed:
        return 1.0
    if failures and failures[0][2] is not None:
        return calculate_pixel_accuracy(failures[0][1], failures[0][2])
    return 0.0


def find_failing_tasks(sample_size=50, tier3_count=None):
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

    random.seed(42)
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

    # Tier 3 on worst N tasks (requires model)
    tier3_targets = failing_tuples[:tier3_count]
    results = []
    if tier3_targets:
        print(f"[evolve] Tier 3: solving {len(tier3_targets)} worst tasks...")
        for tf, td, t1, t2, combined in tier3_targets:
            try:
                solve_score = solve_task_single(td)
            except Exception as e:
                print(f"  [tier3] {tf.name}: error {e}")
                solve_score = 0.0
            category = "CRASH" if t1 < 1.0 else ("PROMPT_FAIL" if t2 < 1.0 else "WRONG_ANSWER")
            results.append({
                "path": tf, "task_data": td, "category": category,
                "tier1": t1, "tier2": t2, "tier3": solve_score, "combined": combined,
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

    return results


def compute_solve_score(failing_results):
    """Average Tier 3 solve score across tasks that were tested."""
    tier3_scores = [r["tier3"] for r in failing_results if r["tier3"] is not None]
    if not tier3_scores:
        return 0.0
    return sum(tier3_scores) / len(tier3_scores)


# ---------------------------------------------------------------------------
# DIAGNOSTIC PROMPTS — enriched with research context + hypothesis history
# ---------------------------------------------------------------------------

DIAGNOSTIC_PROMPT = """\
You are an expert at the ARC-AGI challenge. Analyze these failing ARC tasks and \
propose NEW Python helper functions that would help solve them.

Current DSL has {num_functions} helper functions.

## Research Context — Known ARC Techniques
{research_context}

## Existing Function Signatures (do NOT duplicate these)
{existing_signatures}

## Previous Hypotheses (what worked / what didn't)
{hypothesis_history}

## Failing Tasks
{task_descriptions}

For each failing task:
1. Describe what transformation pattern you see (in/out relationship)
2. Identify what CAPABILITY is missing from the DSL (reference research context above)
3. Write a NEW Python function that implements this capability

Output format:
```python
def new_function_name(grid, ...):
    \"\"\"One-line description of what this does.\"\"\"
    # implementation
    ...
```

Rules:
- Functions must be self-contained (only use stdlib + numpy)
- Each function does ONE clear thing
- Include type hints and a docstring
- Test mentally on the example grids before proposing
- DO NOT rewrite existing functions — only propose NEW ones
- Reference the research context to ground your proposals

Propose 3-5 new functions."""


def _extract_function_signatures(helper_code):
    """Extract 'def name(args):' lines from HELPER_CODE_PREFIX."""
    return re.findall(r"(def \w+\([^)]*\))", helper_code)


def _format_hypothesis_history(entries):
    """Format recent hypotheses for prompt context."""
    if not entries:
        return "No previous experiments."
    lines = []
    for e in entries:
        icon = "+" if e["status"] == "keep" else "-"
        funcs = ", ".join(e.get("proposed_functions", [])[:3])
        lines.append(
            f"  [{icon}] Round {e['round']}: {e['hypothesis'][:80]} "
            f"({funcs}) metric {e['metric_before']:.3f}->{e['metric_after']:.3f}"
        )
    return "\n".join(lines)


def build_diagnostic_prompt(failing_results):
    """Build enriched diagnostic prompt from failing tasks."""
    ns = load_dsl_namespace()
    helper_code = ns.get("HELPER_CODE_PREFIX", "")
    num_functions = helper_code.count("\ndef ") + 1

    # Function signatures — show last 50 to avoid prompt explosion
    sigs = _extract_function_signatures(helper_code)
    sig_lines = [f"  {s}" for s in sigs[-50:]]
    if len(sigs) > 50:
        sig_lines.insert(0, f"  ... ({len(sigs) - 50} more) ...")
    sig_text = "\n".join(sig_lines) if sig_lines else "  (none)"

    # Hypothesis history
    recent = load_recent_hypotheses(10)
    history_text = _format_hypothesis_history(recent)

    # Task descriptions with failure categories
    shown = [r for r in failing_results if r["tier3"] is not None][:TASKS_PER_DIAGNOSTIC]
    if not shown:
        shown = failing_results[:TASKS_PER_DIAGNOSTIC]

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

    return DIAGNOSTIC_PROMPT.format(
        num_functions=num_functions,
        research_context=RESEARCH_CONTEXT.strip(),
        existing_signatures=sig_text,
        hypothesis_history=history_text,
        task_descriptions="\n".join(task_descs),
    )


# ---------------------------------------------------------------------------
# FUNCTION EXTRACTION & VALIDATION
# ---------------------------------------------------------------------------

def extract_functions_from_response(response: str) -> list[str]:
    """Extract Python function definitions from LLM response."""
    functions = []
    blocks = re.findall(r"```python\s*(.*?)\s*```", response, re.DOTALL)
    if not blocks:
        blocks = re.findall(r"```\s*(.*?)\s*```", response, re.DOTALL)

    for block in blocks:
        parts = re.split(r"(?=\ndef )", block)
        for part in parts:
            part = part.strip()
            if part.startswith("def "):
                functions.append(part)
    return functions


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

    return dsl_code[:last_close] + injection + "\n" + dsl_code[last_close:]


# ---------------------------------------------------------------------------
# CODOPT INNER LOOP
# ---------------------------------------------------------------------------

def run_codopt_round():
    """Run one codopt tournament round on dsl.py."""
    cmd = [
        "codopt", "run",
        "--edit", str(DSL_PATH),
        "--metric", str(METRIC_FILE),
        "--metric-key", "score",
        "--command", f"python3 {WORKSPACE / 'benchmark_dsl.py'}",
        "--test", f"python3 {WORKSPACE / 'tests_dsl.py'}",
        "--info", str(WORKSPACE / "INFO.md"),
        "--branch", str(CODOPT_BRANCHES),
        "--time", str(CODOPT_TIME),
        "--rounds", "1",
        "--max-agents", "6",
    ]

    print(f"[evolve] Running codopt: {' '.join(cmd[:6])}...")
    try:
        result = subprocess.run(
            cmd, cwd=str(WORKSPACE), capture_output=True, text=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        print("[evolve] codopt timed out (600s)")
        return False

    if result.returncode == 0:
        print("[evolve] codopt round complete")
        if result.stdout:
            for line in result.stdout.split("\n"):
                if "score" in line.lower() or "metric" in line.lower():
                    print(f"  {line.strip()}")
    else:
        print(f"[evolve] codopt failed: {result.stderr[:300]}")

    return result.returncode == 0


# ---------------------------------------------------------------------------
# GIT COMMIT — auto-commit winning mutations
# ---------------------------------------------------------------------------

def git_commit_if_improved(round_num, pre_score, post_score, hypothesis="",
                           solve_before=0.0, solve_after=0.0):
    """Compare scores and commit if improved. Returns (new_score, commit_hash)."""
    if post_score <= pre_score and solve_after <= solve_before:
        print(f"[evolve] No improvement: metric {pre_score:.4f}->{post_score:.4f}, "
              f"solve {solve_before:.4f}->{solve_after:.4f}")
        return pre_score, None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    msg = (
        f"evolve: round {round_num} DSL improvement "
        f"{pre_score:.4f} -> {post_score:.4f}\n\n"
        f"Solve score: {solve_before:.4f} -> {solve_after:.4f}\n"
        f"Hypothesis: {hypothesis[:200]}\n"
        f"Model: {MODEL_PATH}\n"
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
# MAIN AUTORESEARCH LOOP
# ---------------------------------------------------------------------------

def evolve(rounds=None, diagnose_only=False, never_stop=False, tier3_tasks=None):
    if rounds is None:
        rounds = OUTER_ROUNDS
    if tier3_tasks is not None:
        global TIER3_TASKS
        TIER3_TASKS = tier3_tasks

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

    round_num = 0
    while True:
        round_num += 1
        if not never_stop and round_num > rounds:
            break

        label = f"{round_num}" + ("" if never_stop else f"/{rounds}")
        print(f"\n{'='*60}")
        print(f"  AUTORESEARCH ROUND {label}")
        print(f"{'='*60}")

        # --- 1. EVALUATE ---
        print("\n[1/9] EVALUATE — three-tier task scoring...")
        failing = find_failing_tasks(tier3_count=TIER3_TASKS)
        if not failing:
            print("[evolve] No failing tasks — DSL is perfect!")
            if not never_stop:
                break
            # Re-seed for a fresh sample
            random.seed(datetime.now().microsecond)
            failing = find_failing_tasks(tier3_count=TIER3_TASKS)
            if not failing:
                print("[evolve] Still perfect after re-seed. Sleeping 60s...")
                import time
                time.sleep(60)
                continue

        solve_before = compute_solve_score(failing)
        print(f"[evolve] Pre-round solve score: {solve_before:.4f}")

        # --- 2. DIAGNOSE ---
        print(f"\n[2/9] DIAGNOSE — analyzing {len(failing)} failures...")
        diag_prompt = build_diagnostic_prompt(failing)
        diag_path = RESULTS_DIR / f"round{round_num}_diagnostic.txt"
        diag_path.write_text(diag_prompt)

        if diagnose_only:
            print(f"[evolve] Diagnostic saved to {diag_path}")
            print(diag_prompt[:2000])
            continue

        # --- 3. HYPOTHESIZE ---
        print("\n[3/9] HYPOTHESIZE — generating with MLX...")
        response = generate(diag_prompt, temperature=0.4)
        resp_path = RESULTS_DIR / f"round{round_num}_response.txt"
        resp_path.write_text(response)
        print(f"[evolve] Response ({len(response)} chars) saved to {resp_path}")

        # --- 4. INJECT ---
        print("\n[4/9] INJECT — extracting and validating functions...")
        new_functions = extract_functions_from_response(response)
        validated = [f for f in new_functions if validate_function(f)]
        func_names = []
        for v in validated:
            m = re.match(r"def\s+(\w+)", v)
            if m:
                func_names.append(m.group(1))
        print(f"[evolve] Proposed {len(new_functions)}, valid {len(validated)}: {func_names}")

        hypothesis = f"Add {', '.join(func_names)}" if func_names else "No valid functions proposed"

        if validated:
            mutated_dsl = inject_functions_into_dsl(validated)
            DSL_PATH.write_text(mutated_dsl)
            print(f"[evolve] Injected {len(validated)} functions into dsl.py")

            # Verify tests still pass
            test_result = subprocess.run(
                ["python3", str(WORKSPACE / "tests_dsl.py")],
                cwd=str(WORKSPACE), capture_output=True, text=True,
            )
            if test_result.returncode != 0:
                print("[evolve] WARNING: Tests failed after injection, reverting")
                subprocess.run(["git", "checkout", "dsl.py"], cwd=str(WORKSPACE))
                log_hypothesis(
                    round_num, hypothesis, "diagnostic", func_names,
                    current_score, current_score, solve_before, solve_before, "crash",
                )
                continue

        # --- 5. EXPERIMENT ---
        print("\n[5/9] EXPERIMENT — running codopt tournament...")
        pre_score = current_score
        codopt_ok = run_codopt_round()

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
                solve_after = full_metric.get("compose_score", 0.0)
        except Exception:
            solve_after = 0.0

        print(f"[evolve] Results: metric {pre_score:.4f}->{post_score:.4f}, "
              f"solve {solve_before:.4f}->{solve_after:.4f}")

        # --- 7. DECIDE ---
        improved = post_score > pre_score or solve_after > solve_before
        status = "keep" if improved else "discard"
        print(f"\n[7/9] DECIDE — {status}")

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
            round_num, hypothesis, "diagnostic", func_names,
            pre_score, post_score, solve_before, solve_after,
            status, commit_hash,
        )

        print(f"\n[evolve] Round {round_num} done. Score: {current_score:.4f} [{status}]")

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
    args = parser.parse_args()
    evolve(
        rounds=args.rounds,
        diagnose_only=args.diagnose_only,
        never_stop=args.never_stop,
        tier3_tasks=args.tier3_tasks,
    )
