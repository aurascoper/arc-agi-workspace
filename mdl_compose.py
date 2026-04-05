"""MDL-guided composition of DSL primitives for ARC tasks.

Enumerates chains of grid->grid functions up to depth 3.
Selects shortest chain that passes all training examples exactly.
Runs without LLM -- pure Python enumeration (~2-5s per task).

Source: RCE (2602.15725) -- "12-18 point gains on ARC-AGI-2 with Mistral-7B"
"""

from __future__ import annotations

import inspect
import time
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent

# Curated "interesting" primitives for depth 2-3 search (~32 functions).
# These are the most commonly useful grid->grid transforms.
INTERESTING_PRIMITIVES = [
    # Geometric (14)
    "rotate_cw", "rotate_ccw", "rotate_180", "mirror_h", "mirror_v",
    "transpose", "flip_anti_diagonal", "crop_foreground", "crop_to_bounding_box",
    "remove_border", "gravity_down", "symmetrize_h", "symmetrize_v", "scale_grid",
    # Color (8)
    "remove_noise", "fill_enclosed_background", "fill_holes", "recolor",
    "extract_color", "remove_color", "remap_colors", "infer_noise_color",
    # Object (6)
    "largest_object", "smallest_object", "extract_main_shape",
    "remove_small_objects", "sort_objects", "keep_most_common_colors",
    # Repair (4)
    "repair_symmetry", "repair_holes", "best_symmetry_repair", "best_pattern_repair",
]

# Adjacent pairs that cancel out (no-ops) -- skip these in depth-2/3
CANCEL_PAIRS = {
    ("rotate_cw", "rotate_ccw"),
    ("rotate_ccw", "rotate_cw"),
    ("mirror_h", "mirror_h"),
    ("mirror_v", "mirror_v"),
    ("transpose", "transpose"),
    ("rotate_180", "rotate_180"),
    ("flip_anti_diagonal", "flip_anti_diagonal"),
}


def _is_grid(val) -> bool:
    """Check if value looks like a grid (list of lists of ints)."""
    if not isinstance(val, list) or len(val) == 0:
        return False
    if not isinstance(val[0], list):
        return False
    return all(isinstance(c, (int, float)) for c in val[0])


def discover_composable(dsl_namespace: dict) -> list[tuple[str, callable]]:
    """Find functions that accept a single grid and return a grid.

    Tests each function with a 3x3 canary grid. Returns (name, fn) pairs.
    """
    canary = [[0, 1, 2], [3, 4, 5], [6, 7, 8]]
    composable = []

    for name, obj in sorted(dsl_namespace.items()):
        if not callable(obj) or name.startswith("_"):
            continue
        # Skip known non-composable (classes, etc.)
        if isinstance(obj, type):
            continue
        try:
            sig = inspect.signature(obj)
            params = list(sig.parameters.values())
            if not params:
                continue
            # Must have exactly 1 required param (the grid)
            required = [p for p in params if p.default is inspect.Parameter.empty
                        and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)]
            if len(required) != 1:
                continue
        except (ValueError, TypeError):
            continue

        try:
            result = obj(canary)
            if _is_grid(result):
                composable.append((name, obj))
        except Exception:
            continue

    return composable


def _eval_chain(chain: list[callable], task_data: dict) -> tuple[bool, float]:
    """Run chain on all training pairs. Returns (all_passed, mean_pixel_accuracy).

    Early exit on first mismatch but records pixel accuracy.
    """
    pairs = task_data.get("train", [])
    if not pairs:
        return False, 0.0

    total_correct = 0
    total_pixels = 0

    for pair in pairs:
        grid = pair["input"]
        expected = pair["output"]
        try:
            for fn in chain:
                grid = fn(grid)
            # Normalize to list of lists
            result = [list(row) for row in grid] if grid else []
            exp = [list(row) for row in expected]

            if result == exp:
                # Count all pixels as correct
                pixels = sum(len(row) for row in exp)
                total_correct += pixels
                total_pixels += pixels
            else:
                # Count matching pixels
                if len(result) == len(exp) and all(len(r) == len(e) for r, e in zip(result, exp)):
                    for r_row, e_row in zip(result, exp):
                        for r_val, e_val in zip(r_row, e_row):
                            total_pixels += 1
                            if r_val == e_val:
                                total_correct += 1
                else:
                    # Size mismatch -- 0 accuracy for this pair
                    total_pixels += sum(len(row) for row in exp)
                return False, total_correct / total_pixels if total_pixels else 0.0
        except Exception:
            return False, 0.0

    return True, 1.0


def _chain_to_code(func_names: list[str]) -> str:
    """Convert function name list to executable Python code."""
    lines = ["def transform(grid):"]
    for name in func_names:
        lines.append(f"    grid = {name}(grid)")
    lines.append("    return grid")
    return "\n".join(lines)


def compose_search(task_data: dict, dsl_namespace: dict, timeout: float = 5.0) -> str | None:
    """Search for a primitive chain matching all training pairs.

    Returns Python code string "def transform(grid): ..." or None.

    Search order (MDL preference = shorter chains first):
      Depth 1: all composable functions
      Depth 2: INTERESTING x INTERESTING (~1K chains)
      Depth 3: only if depth 1-2 found no match; guided by depth-2 partial matches
    """
    start = time.monotonic()
    deadline = start + timeout

    # Discover all composable functions
    all_composable = discover_composable(dsl_namespace)
    if not all_composable:
        return None

    all_by_name = {name: fn for name, fn in all_composable}

    # --- Depth 1: try all composable ---
    for name, fn in all_composable:
        if time.monotonic() > deadline:
            return None
        passed, _ = _eval_chain([fn], task_data)
        if passed:
            return _chain_to_code([name])

    # --- Depth 2: interesting x interesting ---
    interesting_fns = [(n, all_by_name[n]) for n in INTERESTING_PRIMITIVES if n in all_by_name]
    depth2_partials = []  # Track partial matches for depth-3 guidance

    for i, (n1, f1) in enumerate(interesting_fns):
        if time.monotonic() > deadline:
            return None
        for n2, f2 in interesting_fns:
            if (n1, n2) in CANCEL_PAIRS:
                continue
            passed, pa = _eval_chain([f1, f2], task_data)
            if passed:
                return _chain_to_code([n1, n2])
            if pa > 0.7:
                depth2_partials.append((n1, n2, f1, f2, pa))

    # --- Depth 3: use depth-2 partial matches as prefixes ---
    if not depth2_partials:
        return None

    # Sort by pixel accuracy descending -- best prefixes first
    depth2_partials.sort(key=lambda x: -x[4])
    # Limit to top 10 prefixes to stay within timeout
    for n1, n2, f1, f2, _ in depth2_partials[:10]:
        if time.monotonic() > deadline:
            return None
        for n3, f3 in interesting_fns:
            if (n2, n3) in CANCEL_PAIRS:
                continue
            if time.monotonic() > deadline:
                return None
            passed, _ = _eval_chain([f1, f2, f3], task_data)
            if passed:
                return _chain_to_code([n1, n2, n3])

    return None


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys

    # Load DSL namespace
    dsl_path = WORKSPACE / "dsl.py"
    dsl_ns = {}
    exec(compile(dsl_path.read_text(), str(dsl_path), "exec"), dsl_ns)

    composable = discover_composable(dsl_ns)
    interesting_available = [n for n in INTERESTING_PRIMITIVES if n in {c[0] for c in composable}]
    print(f"[mdl] Composable functions: {len(composable)}")
    print(f"[mdl] Interesting available: {len(interesting_available)}/{len(INTERESTING_PRIMITIVES)}")

    # Test on a task if provided
    if len(sys.argv) > 1:
        task_path = Path(sys.argv[1])
        task_data = json.loads(task_path.read_text())
        print(f"[mdl] Searching compositions for {task_path.stem}...")
        result = compose_search(task_data, dsl_ns, timeout=10.0)
        if result:
            print(f"[mdl] FOUND:\n{result}")
        else:
            print("[mdl] No composition found")
