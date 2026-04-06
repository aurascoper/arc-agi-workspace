#!/usr/bin/env python3
"""
beam_search_local.py — Local beam-search code optimization using Ollama.

Replaces codopt for ARC-AGI DSL evolution. Uses Ollama (Qwen 3 14B default)
via native API, git worktrees for candidate isolation, and subprocess evaluation.

Strategy: dsl.py is ~650KB so we can't ask the LLM to output the whole file.
Instead, we ask for NEW functions to inject into HELPER_CODE_PREFIX, same
approach as evolve_qwen_arc.py's hypothesis step.

Usage:
  python beam_search_local.py                          # defaults: 2 rounds, branch 3
  python beam_search_local.py --rounds 1 --branch 2   # quick test
  python beam_search_local.py --model qwen3:32b        # different model

As a library:
  from beam_search_local import run_beam_search, BeamConfig
  result = run_beam_search(BeamConfig(rounds=2, branch_factor=3))
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    requests = None  # only needed for ollama backend

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

WORKSPACE = Path(__file__).parent
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("BEAM_MODEL", "deepseek-coder-v2")


@dataclass
class BeamConfig:
    """Configuration for a beam-search run."""
    rounds: int = 2
    branch_factor: int = 3
    max_agents: int = 4          # survivor_cap = max_agents // branch_factor
    time_limit: int = 300        # seconds per LLM call
    edit_file: str = "dsl.py"
    metric_file: str = "metric.json"
    metric_key: str = "score"
    benchmark_cmd: str = "python3 benchmark_dsl.py"
    test_cmd: str = "python3 tests_dsl.py"
    info_file: str = "INFO.md"
    model: str = DEFAULT_MODEL
    workspace: Path = WORKSPACE
    temperature: float = 0.4
    keep_worktrees: bool = False
    backend: str = os.environ.get("BEAM_BACKEND", "mlx")  # "mlx" or "ollama"


@dataclass
class NodeResult:
    """Result of evaluating one candidate."""
    node_id: str
    parent_id: Optional[str]
    score: Optional[float] = None
    test_passed: bool = False
    worktree_path: Optional[str] = None
    branch_name: Optional[str] = None
    error: Optional[str] = None
    dsl_code: str = ""
    response: str = ""


# ---------------------------------------------------------------------------
# OLLAMA INTERACTION
# ---------------------------------------------------------------------------

EVAL_TEMPERATURE = 0.1  # Low temp for judge/eval consistency (arXiv 2603.28304)


def ollama_generate(prompt: str, config: BeamConfig, temperature: Optional[float] = None) -> str:
    """Send a chat completion to Ollama and return the response text."""
    temp = temperature if temperature is not None else config.temperature
    url = f"{OLLAMA_URL}/api/chat"
    payload = {
        "model": config.model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,  # Qwen 3 compat; harmless for other models
        "options": {
            "temperature": temp,
            "num_predict": 2048,
        },
    }

    try:
        resp = requests.post(url, json=payload, timeout=config.time_limit)
        resp.raise_for_status()
        data = resp.json()
        msg = data.get("message", {})
        content = msg.get("content", "")
        # Fallback: if content is empty but thinking has content, use thinking
        if not content.strip() and msg.get("thinking"):
            content = msg["thinking"]
        return content
    except requests.Timeout:
        print(f"    [ollama] Timeout after {config.time_limit}s")
        return ""
    except Exception as e:
        print(f"    [ollama] Error: {e}")
        return ""


def mlx_generate(prompt: str, config: BeamConfig, temperature: Optional[float] = None) -> str:
    """Generate via MLX (reuses target_mlx_arc's loaded model + TurboQuant KV cache)."""
    import gc
    temp = temperature if temperature is not None else config.temperature
    sys.path.insert(0, str(config.workspace))
    try:
        from target_mlx_arc import call_model
        result = call_model(prompt, temperature=temp, max_tokens=2048)
        # Flush KV cache between generations to prevent Metal memory fragmentation
        try:
            import mlx.core as mx
            gc.collect()
            mx.clear_cache()
        except Exception:
            pass
        return result
    except Exception as e:
        print(f"    [mlx] Error: {e}")
        return ""
    finally:
        if str(config.workspace) in sys.path:
            sys.path.remove(str(config.workspace))


def generate(prompt: str, config: BeamConfig, temperature: Optional[float] = None) -> str:
    """Dispatch to MLX or Ollama based on config.backend.

    If temperature is given, it overrides config.temperature for this call only.
    """
    if config.backend == "mlx":
        return mlx_generate(prompt, config, temperature=temperature)
    return ollama_generate(prompt, config, temperature=temperature)


# ---------------------------------------------------------------------------
# PROMPT & PARSING
# ---------------------------------------------------------------------------

def _extract_helper_summary(dsl_code: str, max_sigs: int = 20, task_data: list = None) -> str:
    """Extract function signatures from HELPER_CODE_PREFIX for prompt context.

    If task_data is provided, uses the recognition model to rank by relevance.
    Otherwise falls back to showing the last max_sigs signatures.
    """
    if task_data:
        try:
            from dsl_recognition import get_relevant_signatures
            ranked = get_relevant_signatures(dsl_code, task_data, n=max_sigs)
            total = len(re.findall(r"def \w+\(", dsl_code))
            lines = [f"  {s}" for s in ranked]
            if total > max_sigs:
                lines.insert(0, f"  ... ({total - max_sigs} more, ranked by task relevance) ...")
            return "\n".join(lines) if lines else "  (none)"
        except Exception:
            pass  # fallback below
    sigs = re.findall(r"(def \w+\([^)]*\))", dsl_code)
    shown = sigs[-max_sigs:]
    if len(sigs) > max_sigs:
        shown.insert(0, f"... ({len(sigs) - max_sigs} more) ...")
    return "\n".join(f"  {s}" for s in shown) if shown else "  (none)"


def _extract_function_names(dsl_code: str) -> list[str]:
    """Extract all function names defined in the DSL code."""
    return re.findall(r"def\s+(\w+)\s*\(", dsl_code)


def build_optimization_prompt(dsl_code: str, info_text: str, config: BeamConfig) -> str:
    """Build the prompt sent to the LLM for code optimization."""
    sigs = _extract_helper_summary(dsl_code)
    existing_names = _extract_function_names(dsl_code)
    ban_list = ", ".join(existing_names[-30:]) if existing_names else "(none)"

    # Go-Explore archive context — inject prior best attempts for near-solved tasks
    archive_context = ""
    try:
        from program_archive import get_archive
        archive = get_archive()
        near_solved = archive.get_near_solved(min_score=0.5, max_score=0.99)
        if near_solved:
            import random as _arc_rng
            sampled = _arc_rng.sample(near_solved, min(1, len(near_solved)))
            parts = []
            for tid in sampled:
                snippet = archive.format_for_prompt(tid, k=1)
                if snippet:
                    parts.append(snippet)
            if parts:
                archive_context = "\n".join(parts)
    except Exception:
        pass

    # Categories to encourage diversity
    import random
    categories = [
        "flood fill, connected components, region growing",
        "pattern repetition detection, periodicity, tiling analysis",
        "border/frame detection, inner region extraction",
        "color mapping, palette transformation, recoloring",
        "shape recognition, rectangle detection, L-shape finding",
        "grid alignment, centering, padding, cropping to content",
        "diagonal operations, anti-diagonal reflection, skew transforms",
        "mask operations, overlay, XOR grids, difference detection",
        "gravity simulation, dropping objects, compacting",
        "fractal/recursive patterns, self-similar structure detection",
        "counting, histogram, frequency analysis of grid values",
        "path finding, shortest route, maze solving on grids",
        "scaling, upsampling, downsampling grid by integer factor",
        "noise removal, denoising, outlier pixel correction",
        "template matching, sliding window pattern search",
    ]
    focus = random.choice(categories)

    # Branch task instruction for AGI-2 (DSL helpers) vs AGI-3 (policy mutation)
    is_arc3 = "arc3" in config.edit_file.lower() or "agent" in config.edit_file.lower()

    if is_arc3:
        task_instruction = """## Your task
Output an improved `POLICY_CODE` block that enhances the agent's interactive policy.
- Compose grid manipulation logic using the proven DSL primitives above
- Focus on exploration strategy (which actions to try) and exploitation (how to solve)
- The policy must define `choose_policy_action(frames, latest_frame, action_log=None)`
- Return a dict with "action" key (ACTION1-5, ACTION7) and optional "x","y" for ACTION6

Output ONLY a ```python block containing the full POLICY_CODE. No explanation."""
    else:
        task_instruction = """## Your task
Output 3-5 NEW Python functions to ADD to HELPER_CODE_PREFIX. Each function:
- Takes `grid: list[list[int]]` as first arg (2D array, values 0-9)
- Is self-contained (only stdlib + numpy)
- Does ONE useful ARC transformation
- Has a UNIQUE name not in the banned list above
- Has a one-line docstring

Output ONLY ```python blocks with function definitions. No explanation.

```python
def function_name(grid: list[list[int]]) -> list[list[int]]:
    \"\"\"One-line description.\"\"\"
    # implementation
    return result
```"""

    # Inject proven DSL primitives when optimizing AGI-3 agent
    dsl_primitives_section = ""
    if is_arc3:
        try:
            from dsl_core import get_primitives_for_prompt
            prims = get_primitives_for_prompt(n=5)
            if prims and not prims.startswith("(no"):
                dsl_primitives_section = f"""
## Proven DSL primitives (from ARC-AGI-2, can inline into POLICY_CODE)
These functions are battle-tested on 50+ ARC tasks. You may copy/adapt them:
```python
{prims}
```
"""
        except ImportError:
            pass

    return f"""You are optimizing an ARC-AGI DSL. The goal is to improve the benchmark score
in `{config.metric_file}` (key: "{config.metric_key}", higher is better).

The DSL file `{config.edit_file}` contains `HELPER_CODE_PREFIX` — a string of Python helper
functions that get prepended to LLM-generated transform() functions for ARC tasks.

## Scoring
The benchmark tests: (1) whether helpers execute without errors on real ARC grids,
(2) whether build_prompt() generates valid prompts, (3) helper composition correctness.

## Existing functions (signatures only):
{sigs}

## BANNED NAMES — these functions ALREADY EXIST. Do NOT create functions with any of these names:
{ban_list}

## Focus area for this round
Prioritize functions related to: {focus}

## Background
{info_text}
{dsl_primitives_section}
{archive_context}
{task_instruction}"""


def extract_functions(response: str) -> list[str]:
    """Extract Python function definitions from LLM response."""
    functions = []
    blocks = re.findall(r"```python\s*(.*?)```", response, re.DOTALL)
    if not blocks:
        blocks = re.findall(r"```\s*(.*?)```", response, re.DOTALL)

    for block in blocks:
        parts = re.split(r"(?=\ndef )", block)
        for part in parts:
            part = part.strip()
            if part.startswith("def "):
                healed = _heal_truncated(part)
                if healed:
                    functions.append(healed)
    return functions


def _heal_truncated(func_code: str) -> Optional[str]:
    """If func_code doesn't compile, trim lines until it does."""
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


def validate_function(func_code: str, dsl_code: str) -> bool:
    """Check if a proposed function is valid and doesn't shadow existing names."""
    try:
        compile(func_code, "<proposed>", "exec")
    except SyntaxError:
        return False

    func_name = re.match(r"def\s+(\w+)", func_code)
    if func_name:
        # Check if function already exists in DSL
        existing = re.findall(r"def\s+(\w+)\(", dsl_code)
        if func_name.group(1) in existing:
            return False
    return True


def inject_functions(dsl_code: str, new_functions: list[str]) -> Optional[str]:
    """Append validated new functions to HELPER_CODE_PREFIX in dsl.py code."""
    closing_marker = "'''"
    last_close = dsl_code.rfind(closing_marker)
    if last_close == -1:
        return None

    injection = "\n\n# --- BEAM SEARCH EVOLVED FUNCTIONS ---\n"
    for func in new_functions:
        injection += "\n" + func + "\n"

    result = dsl_code[:last_close] + injection + "\n" + dsl_code[last_close:]

    try:
        compile(result, "<mutated>", "exec")
        return result
    except SyntaxError:
        return None


# ---------------------------------------------------------------------------
# GIT WORKTREE OPERATIONS
# ---------------------------------------------------------------------------

def create_worktree(config: BeamConfig, node_id: str) -> tuple[str, str]:
    """Create a git worktree for a candidate. Returns (worktree_path, branch_name)."""
    branch_name = f"beam/{node_id}"
    worktree_path = str(config.workspace / ".beam_worktrees" / node_id)

    # Clean up if leftover from a previous run
    if os.path.exists(worktree_path):
        subprocess.run(
            ["git", "worktree", "remove", "--force", worktree_path],
            cwd=str(config.workspace), capture_output=True,
        )

    subprocess.run(
        ["git", "branch", "-D", branch_name],
        cwd=str(config.workspace), capture_output=True,
    )

    result = subprocess.run(
        ["git", "worktree", "add", "-b", branch_name, worktree_path, "HEAD"],
        cwd=str(config.workspace), capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create worktree: {result.stderr}")

    return worktree_path, branch_name


def cleanup_worktree(config: BeamConfig, worktree_path: str, branch_name: str):
    """Remove a git worktree and its branch."""
    subprocess.run(
        ["git", "worktree", "remove", "--force", worktree_path],
        cwd=str(config.workspace), capture_output=True,
    )
    subprocess.run(
        ["git", "branch", "-D", branch_name],
        cwd=str(config.workspace), capture_output=True,
    )


def cleanup_all_worktrees(config: BeamConfig):
    """Remove all beam search worktrees."""
    wt_dir = config.workspace / ".beam_worktrees"
    if wt_dir.exists():
        shutil.rmtree(str(wt_dir), ignore_errors=True)

    # Prune AFTER removing directories so git knows they're gone
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=str(config.workspace), capture_output=True,
    )

    # Clean up leftover beam branches
    result = subprocess.run(
        ["git", "branch", "--list", "beam/*"],
        cwd=str(config.workspace), capture_output=True, text=True,
    )
    for line in result.stdout.strip().split('\n'):
        branch = line.strip()
        if branch:
            subprocess.run(
                ["git", "branch", "-D", branch],
                cwd=str(config.workspace), capture_output=True,
            )


# ---------------------------------------------------------------------------
# MINI TIER 3 SOLVE TEST
# ---------------------------------------------------------------------------

SOLVE_TASKS = 3  # number of tasks for quick tier 3 eval
SOLVE_WEIGHT = 0.3  # when base score is at ceiling, blend: 0.7*base + 0.3*solve

def _mini_solve_eval(worktree_path: str, config: BeamConfig) -> float:
    """Quick tier 3 eval: load DSL from worktree, solve a few tasks, return avg pixel accuracy."""
    arc_data = config.workspace / "arc_agi_2_data" / "training"
    if not arc_data.exists():
        return 0.0

    # We need target_mlx_arc utilities — import from the main workspace
    sys.path.insert(0, str(config.workspace))
    try:
        from target_mlx_arc import try_code_on_task, extract_python_code, calculate_pixel_accuracy
    except ImportError:
        return 0.0
    finally:
        sys.path.pop(0)

    # Load DSL from the worktree (candidate's mutated version)
    dsl_path = os.path.join(worktree_path, config.edit_file)
    try:
        dsl_code = Path(dsl_path).read_text()
        dsl_ns: dict = {}
        exec(compile(dsl_code, dsl_path, "exec"), dsl_ns)
        build_prompt = dsl_ns.get("build_prompt")
        if not build_prompt:
            return 0.0
    except Exception:
        return 0.0

    # Pick a sample that is consistent within a beam search run but varies across runs.
    # config._solve_seed is set once at the start of run_beam_search().
    import random as _rng
    task_files = sorted(arc_data.glob("*.json"))
    _rng.seed(getattr(config, "_solve_seed", 0))
    sample = _rng.sample(task_files, min(SOLVE_TASKS, len(task_files)))

    EARLY_TERM_AFTER = 3  # check for early termination after this many tasks
    scores = []
    for tf in sample:
        # Early termination: if first N tasks all score 0, bail (arXiv 2504.03037 insight)
        if len(scores) >= EARLY_TERM_AFTER and all(s == 0.0 for s in scores):
            print(f"    [tier3-mini] Early termination: first {EARLY_TERM_AFTER} tasks all 0.0")
            return 0.0
        try:
            td = json.loads(tf.read_text())
            # Canonicalize colors — LLM sees frequency-ordered colors
            try:
                from evolve_qwen_arc import _canonicalize_task
                td, _inv = _canonicalize_task(td)
            except ImportError:
                pass
            # H3: Try composition search before LLM (fast, no tokens)
            try:
                from mdl_compose import compose_search
                comp_code = compose_search(td, dsl_ns, timeout=3.0)
                if comp_code:
                    comp_passed, _ = try_code_on_task(comp_code, td)
                    if comp_passed:
                        scores.append(1.0)
                        try:
                            from evolve_qwen_arc import _log_successful_program
                            _log_successful_program(tf.stem, td, comp_code, "composition_search")
                        except Exception:
                            pass
                        continue
            except Exception:
                pass
            prompt = build_prompt(td)
            if not prompt:
                scores.append(0.0)
                continue
            response = generate(prompt, config, temperature=EVAL_TEMPERATURE)
            code = extract_python_code(response)
            if not code or "def transform" not in code:
                scores.append(0.0)
                continue
            passed, failures = try_code_on_task(code, td)
            if passed:
                scores.append(1.0)
                # Log for LoRA fine-tuning
                try:
                    from evolve_qwen_arc import _log_successful_program
                    _log_successful_program(tf.stem, td, code, prompt)
                except Exception:
                    pass
                # Archive successful solve (Go-Explore)
                try:
                    from program_archive import get_archive
                    get_archive().update(tf.stem, 1.0, code)
                except Exception:
                    pass
            elif failures:
                pair_scores = [calculate_pixel_accuracy(f[1], f[2]) if f[2] is not None else 0.0 for f in failures]
                avg_pa = sum(pair_scores) / len(pair_scores)
                # Log near-miss for LoRA fine-tuning
                if avg_pa >= 0.92 and all(f[2] is not None for f in failures):
                    try:
                        from evolve_qwen_arc import _log_near_miss_program
                        _log_near_miss_program(tf.stem, td, code, prompt, avg_pa)
                    except Exception:
                        pass
                # Collect synthetic task from failed program (TransCoder-style)
                try:
                    from synthetic_tasks import collect_from_beam_failure
                    collect_from_beam_failure(td, code, tf.stem)
                except Exception:
                    pass
                # Archive partial solution (Go-Explore)
                try:
                    from program_archive import get_archive
                    get_archive().update(tf.stem, avg_pa, code)
                except Exception:
                    pass
                scores.append(avg_pa)
            else:
                # Even total failures can generate synthetic tasks
                try:
                    from synthetic_tasks import collect_from_beam_failure
                    collect_from_beam_failure(td, code, tf.stem)
                except Exception:
                    pass
                scores.append(0.0)
        except Exception:
            scores.append(0.0)

    return sum(scores) / len(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# EVALUATION
# ---------------------------------------------------------------------------

def evaluate_candidate(worktree_path: str, config: BeamConfig) -> tuple[Optional[float], bool, str]:
    """Run benchmark + tests in a worktree. Returns (score, test_passed, error_msg).

    When the base benchmark score is at ceiling (>=0.999), blends in a mini
    tier 3 solve test so candidates have actual selection pressure.
    """
    metric_path = os.path.join(worktree_path, config.metric_file)

    # Clear any stale metric file
    if os.path.exists(metric_path):
        os.remove(metric_path)

    # Run benchmark
    try:
        result = subprocess.run(
            config.benchmark_cmd.split(),
            cwd=worktree_path, capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return None, False, f"benchmark failed: {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return None, False, "benchmark timed out"

    # Read metric
    try:
        with open(metric_path) as f:
            metric_data = json.load(f)
        base_score = float(metric_data[config.metric_key])
    except Exception as e:
        return None, False, f"metric parse error: {e}"

    # Run correctness tests
    try:
        result = subprocess.run(
            config.test_cmd.split(),
            cwd=worktree_path, capture_output=True, text=True, timeout=60,
        )
        test_passed = result.returncode == 0
        if not test_passed:
            return base_score, False, f"tests failed: {result.stdout[:200]}"
    except subprocess.TimeoutExpired:
        return base_score, False, "tests timed out"

    # If base score is at ceiling, add tier 3 solve pressure
    if base_score >= 0.999:
        solve_score = _mini_solve_eval(worktree_path, config)
        blended = base_score * (1 - SOLVE_WEIGHT) + solve_score * SOLVE_WEIGHT
        print(f"    [tier3-mini] solve={solve_score:.2f} blended={blended:.4f}")
        return blended, True, ""

    return base_score, True, ""


# ---------------------------------------------------------------------------
# BEAM SEARCH
# ---------------------------------------------------------------------------

def run_beam_search(config: Optional[BeamConfig] = None) -> Optional[NodeResult]:
    """Run beam-search optimization. Returns the best NodeResult or None."""
    if config is None:
        config = BeamConfig()

    # Fix seed for mini-solve so baseline and all candidates use the same tasks
    config._solve_seed = int(time.time()) % 100000

    survivor_cap = max(1, config.max_agents // config.branch_factor)
    edit_path = config.workspace / config.edit_file
    info_path = config.workspace / config.info_file

    if not edit_path.exists():
        print(f"[beam] ERROR: {edit_path} not found")
        return None

    dsl_code = edit_path.read_text()
    info_text = info_path.read_text() if info_path.exists() else ""

    # Baseline evaluation
    print(f"[beam] Evaluating baseline...")
    baseline_score, baseline_passed, baseline_err = evaluate_candidate(
        str(config.workspace), config,
    )
    if baseline_score is None:
        print(f"[beam] Baseline evaluation failed: {baseline_err}")
        return None

    print(f"[beam] Baseline score: {baseline_score:.4f}")

    baseline = NodeResult(
        node_id="baseline",
        parent_id=None,
        score=baseline_score,
        test_passed=baseline_passed,
        dsl_code=dsl_code,
    )

    frontier = [baseline]
    all_nodes: list[NodeResult] = [baseline]

    for round_idx in range(1, config.rounds + 1):
        print(f"\n[beam] === Round {round_idx}/{config.rounds} === "
              f"(frontier={len(frontier)}, branching={config.branch_factor}, "
              f"survivor_cap={survivor_cap})")

        candidates: list[NodeResult] = []

        for parent in frontier:
            for child_idx in range(config.branch_factor):
                node_id = f"r{round_idx}_p{parent.node_id}_{child_idx}"
                print(f"\n  [{node_id}] Generating mutation...")

                # Create worktree
                try:
                    wt_path, branch_name = create_worktree(config, node_id)
                except Exception as e:
                    print(f"  [{node_id}] Worktree failed: {e}")
                    candidates.append(NodeResult(
                        node_id=node_id, parent_id=parent.node_id,
                        error=str(e),
                    ))
                    continue

                # Generate new functions via LLM
                prompt = build_optimization_prompt(parent.dsl_code, info_text, config)
                t0 = time.time()
                response = generate(prompt, config)
                gen_time = time.time() - t0
                print(f"  [{node_id}] Generated in {gen_time:.1f}s ({len(response)} chars)")

                # Extract and validate functions
                raw_functions = extract_functions(response)
                valid_functions = [f for f in raw_functions
                                   if validate_function(f, parent.dsl_code)]

                if not valid_functions:
                    print(f"  [{node_id}] No valid functions extracted "
                          f"(raw={len(raw_functions)})")
                    cleanup_worktree(config, wt_path, branch_name)
                    candidates.append(NodeResult(
                        node_id=node_id, parent_id=parent.node_id,
                        error="no valid functions", response=response[:500],
                    ))
                    continue

                # Dedup by function name (keep first occurrence)
                seen_names: set[str] = set()
                deduped: list[str] = []
                for f in valid_functions:
                    m = re.match(r"def\s+(\w+)", f)
                    if m and m.group(1) not in seen_names:
                        seen_names.add(m.group(1))
                        deduped.append(f)
                if len(deduped) < len(valid_functions):
                    print(f"  [{node_id}] Deduped {len(valid_functions)} -> {len(deduped)} functions")
                valid_functions = deduped

                func_names = []
                for f in valid_functions:
                    m = re.match(r"def\s+(\w+)", f)
                    if m:
                        func_names.append(m.group(1))
                print(f"  [{node_id}] Injecting {len(valid_functions)} functions: "
                      f"{func_names}")

                # Inject into dsl.py
                new_code = inject_functions(parent.dsl_code, valid_functions)
                if new_code is None:
                    print(f"  [{node_id}] Injection failed (syntax error)")
                    cleanup_worktree(config, wt_path, branch_name)
                    candidates.append(NodeResult(
                        node_id=node_id, parent_id=parent.node_id,
                        error="injection syntax error",
                    ))
                    continue

                # Write mutated code to worktree
                (Path(wt_path) / config.edit_file).write_text(new_code)

                # Evaluate
                print(f"  [{node_id}] Evaluating...")
                score, passed, err = evaluate_candidate(wt_path, config)
                print(f"  [{node_id}] Score: {score} | Tests: "
                      f"{'PASS' if passed else 'FAIL'}"
                      f"{f' | {err}' if err else ''}")

                node = NodeResult(
                    node_id=node_id,
                    parent_id=parent.node_id,
                    score=score,
                    test_passed=passed,
                    worktree_path=wt_path,
                    branch_name=branch_name,
                    error=err if not passed else None,
                    dsl_code=new_code,
                    response=response[:1000],
                )
                candidates.append(node)
                all_nodes.append(node)

        # Select survivors with novelty bonus (QD-inspired)
        valid = [c for c in candidates if c.score is not None and c.test_passed]
        # Compute novelty bonus: reward candidates whose new functions cover
        # underrepresented transformation types
        NOVELTY_LAMBDA = 0.15  # weight of novelty bonus vs raw score
        # Cache baseline names once (avoid re-extracting 22K line file per candidate)
        baseline_names = set(_extract_function_names(dsl_code))
        for c in valid:
            novelty = 0.0
            if c.dsl_code:
                # Only extract new names from the diff (candidate code after baseline)
                candidate_names = set(_extract_function_names(c.dsl_code))
                new_names = candidate_names - baseline_names
                if new_names:
                    # Count how many distinct type categories the new functions cover
                    types_covered = set()
                    for name in new_names:
                        best_type = "other"
                        best_hits = 0
                        for ttype, kws in [
                            ("symmetry", ["symmetr", "mirror", "reflect", "flip"]),
                            ("flood_fill", ["flood", "fill", "paint", "region"]),
                            ("connected_components", ["connect", "component", "object", "blob"]),
                            ("color_logic", ["color", "palette", "histogram", "recolor"]),
                            ("pattern_tile", ["pattern", "tile", "repeat", "stamp"]),
                            ("transform_geom", ["rotate", "scale", "crop", "shift", "gravity"]),
                            ("grid_decompose", ["decompos", "split", "quadrant", "partition"]),
                            ("topology", ["topology", "layer", "occlu", "stack"]),
                            ("counting_arithmetic", ["count", "arith", "sum", "sort"]),
                            ("boundary_edge", ["boundar", "edge", "border", "contour"]),
                            ("masking_boolean", ["mask", "boolean", "xor", "union"]),
                        ]:
                            hits = sum(1 for kw in kws if kw in name.lower())
                            if hits > best_hits:
                                best_type, best_hits = ttype, hits
                        types_covered.add(best_type)
                    # Novelty = fraction of distinct types (0-1 range)
                    novelty = len(types_covered) / max(len(new_names), 1)
            c._novelty_bonus = novelty  # type: ignore[attr-defined]
            c._adjusted_score = (c.score or 0) + NOVELTY_LAMBDA * novelty  # type: ignore[attr-defined]

        valid.sort(key=lambda n: getattr(n, '_adjusted_score', n.score or -1),
                   reverse=True)
        survivors = valid[:survivor_cap]

        # Report round results
        if valid:
            print(f"\n[beam] Round {round_idx} results:")
            for v in valid:
                marker = " *" if v in survivors else ""
                print(f"  {v.node_id}: {v.score:.4f}{marker}")
        else:
            print(f"\n[beam] Round {round_idx}: no valid candidates")

        # Cleanup non-survivors
        for c in candidates:
            if c not in survivors and c.worktree_path and c.branch_name:
                if not config.keep_worktrees:
                    cleanup_worktree(config, c.worktree_path, c.branch_name)

        if not survivors:
            print("[beam] No survivors — stopping early")
            break

        frontier = survivors

    # Find best overall result
    all_valid = [n for n in all_nodes if n.score is not None and n.test_passed]
    if not all_valid:
        print("[beam] No valid candidates found across all rounds")
        cleanup_all_worktrees(config)
        return baseline

    best = max(all_valid, key=lambda n: n.score if n.score is not None else -1)

    if (best.score is not None and baseline.score is not None
            and best.score > baseline.score):
        print(f"\n[beam] WINNER: {best.node_id} with score {best.score:.4f} "
              f"(+{best.score - baseline.score:.4f} over baseline)")
        edit_path.write_text(best.dsl_code)
    else:
        print(f"\n[beam] No improvement over baseline ({baseline.score:.4f})")

    # Always cleanup all worktrees (survivors included)
    cleanup_all_worktrees(config)

    return best


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Local beam-search code optimization via Ollama")
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--branch", type=int, default=3)
    parser.add_argument("--max-agents", type=int, default=4)
    parser.add_argument("--time", type=int, default=120)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--temp", type=float, default=0.4)
    parser.add_argument("--keep-worktrees", action="store_true")
    args = parser.parse_args()

    config = BeamConfig(
        rounds=args.rounds,
        branch_factor=args.branch,
        max_agents=args.max_agents,
        time_limit=args.time,
        model=args.model,
        temperature=args.temp,
        keep_worktrees=args.keep_worktrees,
    )

    print(f"[beam] Config: rounds={config.rounds} branch={config.branch_factor} "
          f"survivors={max(1, config.max_agents // config.branch_factor)} "
          f"model={config.model} temp={config.temperature}")

    result = run_beam_search(config)

    if result and result.score is not None:
        print(f"\n[beam] Final best score: {result.score:.4f} ({result.node_id})")
    else:
        print("\n[beam] No valid result")


if __name__ == "__main__":
    main()
