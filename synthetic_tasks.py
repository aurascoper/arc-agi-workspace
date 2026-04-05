"""TransCoder-inspired synthetic task generation from failed programs.

When beam search produces a program that doesn't solve the target task,
that program still implements SOME transformation. By applying it to the
task's inputs, we create a new (task', program) pair where the program IS
the correct solution. This bootstraps supervised training data.

Based on: TransCoder (Bednarek & Krawiec, 2410.04480)
  - "Learning from mistakes": failed programs generate synthetic training tasks
  - Synthetic tasks are easier → provide learning gradient for supervised training
  - Over 5 cycles: synthetic task solve rate 1.72% → 21.66%

Integration: called from beam_search_local after each mutation evaluation,
and from evolve_qwen_arc during EXPERIMENT step to collect training data.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
SYNTHETIC_TASKS_PATH = WORKSPACE / "evolution_results" / "synthetic_tasks.jsonl"
MAX_SYNTHETIC_TASKS = 5000  # cap file size

# ---------------------------------------------------------------------------
# Core: generate synthetic task from a failed program
# ---------------------------------------------------------------------------

def generate_synthetic_task(task_data: dict, code: str, task_name: str = "unknown",
                            ) -> dict | None:
    """Apply a failed program to task inputs to create a synthetic (task', program) pair.

    The key insight from TransCoder: if program P fails to solve task T,
    we can still apply P to T's inputs to get outputs O. The pair (inputs, O)
    forms a new task T' where P is the correct solution.

    Args:
        task_data: Original ARC task dict with train/test pairs
        code: Python code with def transform(grid) that FAILED on this task
        task_name: Name for logging

    Returns:
        Dict with synthetic task data + the code, or None if generation fails.
        Format: {
            "source_task": str,
            "synthetic_task": {"train": [...], "test": [...]},
            "code": str,
            "timestamp": float,
            "nontrivial": bool
        }
    """
    # Execute the code to get the transform function
    try:
        dsl_path = WORKSPACE / "dsl.py"
        dsl_code = dsl_path.read_text()
        ns: dict = {}
        exec(compile(dsl_code + "\n" + code, "<synthetic>", "exec"), ns)
        transform_fn = ns.get("transform")
        if transform_fn is None:
            return None
    except Exception:
        return None

    # Apply transform to all training inputs
    synthetic_train = []
    outputs_set = set()  # track uniqueness for nontriviality check

    for pair in task_data.get("train", []):
        inp = pair["input"]
        try:
            result = _run_with_timeout(transform_fn, inp, timeout=5.0)
            if result is None:
                return None  # crash = unusable
            out = [list(row) for row in result]
        except Exception:
            return None  # any failure = discard

        # Basic validation
        if not out or not out[0]:
            return None
        if len(out) > 30 or len(out[0]) > 30:
            return None  # unreasonable size

        synthetic_train.append({"input": inp, "output": out})
        outputs_set.add(str(out))

    if len(synthetic_train) < 2:
        return None  # need at least 2 training pairs

    # Apply to test inputs too
    synthetic_test = []
    for pair in task_data.get("test", []):
        inp = pair["input"]
        try:
            result = _run_with_timeout(transform_fn, inp, timeout=5.0)
            if result is None:
                continue
            out = [list(row) for row in result]
            synthetic_test.append({"input": inp, "output": out})
        except Exception:
            continue

    # Nontriviality checks (from TransCoder paper):
    # 1. Outputs must not all be identical (program must depend on input)
    all_same = len(outputs_set) == 1
    # 2. Output must differ from input (not identity)
    is_identity = all(
        pair["input"] == pair["output"] for pair in synthetic_train
    )
    # 3. Output must not be empty/trivial
    is_trivial = all(
        all(c == 0 for row in pair["output"] for c in row)
        for pair in synthetic_train
    )

    nontrivial = not all_same and not is_identity and not is_trivial

    if not nontrivial:
        return None  # only keep nontrivial synthetic tasks

    return {
        "source_task": task_name,
        "synthetic_task": {
            "train": synthetic_train,
            "test": synthetic_test,
        },
        "code": code,
        "timestamp": time.time(),
        "num_train": len(synthetic_train),
        "num_test": len(synthetic_test),
    }


def _run_with_timeout(fn, grid, timeout: float = 5.0):
    """Run transform function with timeout."""
    import signal

    class TimeoutError(Exception):
        pass

    def handler(signum, frame):
        raise TimeoutError()

    old = signal.signal(signal.SIGALRM, handler)
    signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        result = fn(grid)
        return result
    except TimeoutError:
        return None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


# ---------------------------------------------------------------------------
# Logging — append synthetic tasks to JSONL
# ---------------------------------------------------------------------------

def log_synthetic_task(entry: dict) -> bool:
    """Append a synthetic task entry to the JSONL file.

    Returns True if logged, False if at capacity or error.
    """
    try:
        SYNTHETIC_TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Check size cap
        if SYNTHETIC_TASKS_PATH.exists():
            line_count = sum(1 for _ in open(SYNTHETIC_TASKS_PATH))
            if line_count >= MAX_SYNTHETIC_TASKS:
                return False

        with open(SYNTHETIC_TASKS_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Collection — process beam search failures into synthetic tasks
# ---------------------------------------------------------------------------

def collect_from_beam_failure(task_data: dict, code: str,
                              task_name: str = "unknown") -> bool:
    """Try to create and log a synthetic task from a failed beam search program.

    Call this whenever a beam search mutation produces code that doesn't
    beat baseline. The "failed" code may still encode a useful transformation.

    Returns True if a synthetic task was created and logged.
    """
    if not code or "def transform" not in code:
        return False

    entry = generate_synthetic_task(task_data, code, task_name)
    if entry is None:
        return False

    return log_synthetic_task(entry)


# ---------------------------------------------------------------------------
# Loading — read synthetic tasks for training
# ---------------------------------------------------------------------------

def load_synthetic_tasks(max_tasks: int = 500) -> list[dict]:
    """Load synthetic tasks from JSONL for LoRA fine-tuning or prompt augmentation.

    Returns list of dicts with 'synthetic_task' and 'code' fields.
    Most recent tasks first (LIFO for freshness).
    """
    if not SYNTHETIC_TASKS_PATH.exists():
        return []

    tasks = []
    try:
        with open(SYNTHETIC_TASKS_PATH) as f:
            for line in f:
                line = line.strip()
                if line:
                    tasks.append(json.loads(line))
    except Exception:
        return []

    # Most recent first, cap at max
    tasks.reverse()
    return tasks[:max_tasks]


def get_synthetic_stats() -> dict:
    """Quick stats on the synthetic task collection."""
    if not SYNTHETIC_TASKS_PATH.exists():
        return {"total": 0, "unique_sources": 0}

    sources = set()
    total = 0
    try:
        with open(SYNTHETIC_TASKS_PATH) as f:
            for line in f:
                if line.strip():
                    total += 1
                    entry = json.loads(line)
                    sources.add(entry.get("source_task", "?"))
    except Exception:
        pass

    return {
        "total": total,
        "unique_sources": len(sources),
        "path": str(SYNTHETIC_TASKS_PATH),
    }


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Test with a simple "failed" program
    test_task = {
        "train": [
            {"input": [[0, 1, 2], [3, 4, 5]], "output": [[5, 4, 3], [2, 1, 0]]},
            {"input": [[1, 0], [0, 1]], "output": [[1, 0], [0, 1]]},
        ],
        "test": [{"input": [[7, 8, 9], [0, 0, 0]]}]
    }
    # This code does rotate_180, which is wrong for the task but valid
    test_code = """
def transform(grid):
    return [row[::-1] for row in grid[::-1]]
"""
    result = generate_synthetic_task(test_task, test_code, "test_task")
    if result:
        print(f"[synthetic] Generated task from 'test_task':")
        print(f"  Train pairs: {result['num_train']}")
        print(f"  Test pairs: {result['num_test']}")
        print(f"  Source: {result['source_task']}")
        st = result["synthetic_task"]
        for i, pair in enumerate(st["train"]):
            print(f"  Pair {i}: {pair['input']} → {pair['output']}")
    else:
        print("[synthetic] No synthetic task generated (trivial or crashed)")

    print(f"\n[synthetic] Stats: {get_synthetic_stats()}")
    print("[synthetic] Module loaded OK.")
