"""Dead function pruner for dsl.py HELPER_CODE_PREFIX.

Identifies and removes functions that are:
1. Not in any hardcoded safelist (CORE_FUNCTIONS, select_relevant_helpers, etc.)
2. Not called by any other function in the DSL
3. Not referenced in any successful solution

Designed to run periodically (every 10 rounds) from the evolution loop.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
DSL_PATH = WORKSPACE / "dsl.py"
SUCCESSFUL_PROGRAMS_PATH = WORKSPACE / "evolution_results" / "successful_programs.jsonl"
HYPOTHESES_PATH = WORKSPACE / "evolution_results" / "hypotheses.jsonl"

# Functions that must NEVER be pruned
CORE_FUNCTIONS = {
    "detect_background_color", "get_objects", "shape", "palette",
    "color_counts", "copy_grid", "rotate_cw", "mirror_h",
}

# Functions referenced in build_prompt / select_relevant_helpers / exact_helper_order
# Extracted from dsl.py lines 20484-20579 and 20826-20839
PROMPT_REFERENCED = {
    "detect_background_color", "dominant_non_background_color", "non_background_colors",
    "find_cells", "get_bbox", "get_bbox_of_color", "get_objects", "get_objects_by_color",
    "get_shapes", "objects_by_color", "object_colors", "object_color_counts",
    "object_dimensions", "flood_fill", "crop", "crop_foreground", "crop_object",
    "object_to_grid", "fit_grid_to_size", "foreground_in_place", "overlay",
    "union", "intersect", "difference", "rotate_cw", "rotate_ccw", "rotate_180",
    "transpose", "flip_anti_diagonal", "mirror_h", "mirror_v", "symmetrize_h",
    "symmetrize_v", "fill_from_mirror_h", "fill_from_mirror_v", "repair_symmetry",
    "best_axis_completion", "shift_grid", "move_object", "transform_object",
    "transform_objects_in_place", "scale_grid", "tile_grid", "apply_gravity",
    "project", "project_all", "raycast", "remap_colors", "extract_color",
    "remove_color", "remove_colors", "remove_noise", "infer_noise_color",
    "infer_noise_colors", "remove_small_objects", "remove_small_shapes",
    "remove_border_objects_by_size", "remove_border_shapes_by_size",
    "keep_most_common_colors", "fill_enclosed_background", "best_enclosed_fill",
    "fill_holes", "repair_holes", "filter_by_color", "filter_by_size",
    "filter_by_dimensions", "filter_by_position", "sort_objects",
    "manhattan_distance", "overlaps", "touching", "same_shape", "same_dimensions",
    "same_color", "is_square_object", "is_line_object", "is_rectangle_object",
    "touches_border", "border_objects", "interior_objects", "count_objects",
    "topmost_object", "bottommost_object", "leftmost_object", "rightmost_object",
    "nearest_object", "farthest_object", "extract_main_shape",
    "repair_main_shape_symmetry", "repair_main_shape_in_place",
    "denoise_and_repair_symmetry", "best_symmetry_repair", "best_pattern_repair",
    "best_pattern_repair_in_place", "solve_occlusion",
    # Also from fallback and exact_helper_order
    "make_grid", "recolor", "largest_object", "smallest_object",
    "color_counts", "palette", "shape", "copy_grid",
    "histogram_of_colors", "count_color_frequencies",
    # Functions used by classify_problem_class and analyze_task_deeply
    "classify_problem_class", "analyze_task_deeply", "select_relevant_helpers",
    "build_prompt",
}

SAFELIST = CORE_FUNCTIONS | PROMPT_REFERENCED


def _extract_helper_code() -> str:
    """Extract HELPER_CODE_PREFIX content from dsl.py."""
    dsl_text = DSL_PATH.read_text()
    m = re.search(r"HELPER_CODE_PREFIX\s*=\s*r?'''(.*?)'''", dsl_text, re.DOTALL)
    if not m:
        m = re.search(r'HELPER_CODE_PREFIX\s*=\s*r?"""(.*?)"""', dsl_text, re.DOTALL)
    return m.group(1) if m else ""


def _build_call_graph(helper_code: str) -> tuple[dict[str, set[str]], dict[str, tuple[int, int]]]:
    """Parse HELPER_CODE_PREFIX and build internal call graph.

    Returns:
        call_graph: {func_name: set of functions it calls}
        func_spans: {func_name: (start_line, end_line)} for removal
    """
    try:
        tree = ast.parse(helper_code)
    except SyntaxError:
        return {}, {}

    all_funcs = set()
    func_spans = {}
    call_graph = {}

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            all_funcs.add(node.name)
            func_spans[node.name] = (node.lineno, node.end_lineno or node.lineno)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            callees = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name) and child.func.id in all_funcs:
                        callees.add(child.func.id)
                    elif isinstance(child.func, ast.Attribute) and isinstance(child.func.value, ast.Name):
                        # Handle calls like np.array() — not internal DSL calls
                        pass
            callees.discard(node.name)  # remove self-recursion from deps
            call_graph[node.name] = callees

    return call_graph, func_spans


def _get_all_callers(call_graph: dict[str, set[str]]) -> dict[str, set[str]]:
    """Invert call graph to get: {func: set of functions that call it}."""
    callers: dict[str, set[str]] = {f: set() for f in call_graph}
    for caller, callees in call_graph.items():
        for callee in callees:
            if callee in callers:
                callers[callee].add(caller)
    return callers


def _get_transitive_deps(func: str, call_graph: dict[str, set[str]], seen=None) -> set[str]:
    """Get all functions transitively called by func."""
    if seen is None:
        seen = set()
    if func in seen:
        return set()
    seen.add(func)
    deps = set()
    for callee in call_graph.get(func, set()):
        deps.add(callee)
        deps |= _get_transitive_deps(callee, call_graph, seen)
    return deps


def _functions_in_solutions() -> set[str]:
    """Extract function names referenced in successful solutions and hypotheses."""
    referenced = set()

    # From successful_programs.jsonl
    if SUCCESSFUL_PROGRAMS_PATH.exists():
        try:
            for line in SUCCESSFUL_PROGRAMS_PATH.read_text().strip().split("\n"):
                if not line.strip():
                    continue
                entry = json.loads(line)
                code = entry.get("code", "")
                # Extract function calls from the solution code
                referenced.update(re.findall(r'\b(\w+)\s*\(', code))
        except (json.JSONDecodeError, OSError):
            pass

    # From hypotheses.jsonl — proposed function names
    if HYPOTHESES_PATH.exists():
        try:
            for line in HYPOTHESES_PATH.read_text().strip().split("\n"):
                if not line.strip():
                    continue
                entry = json.loads(line)
                for fn in entry.get("proposed_functions", []):
                    referenced.add(fn)
        except (json.JSONDecodeError, OSError):
            pass

    return referenced


def find_dead_functions(dry_run=True) -> list[str]:
    """Identify dead functions in HELPER_CODE_PREFIX.

    A function is dead if it is:
    1. Not in the safelist (CORE + prompt-referenced)
    2. Not called by any safelist function (transitively)
    3. Not referenced in any successful solution or hypothesis

    Returns list of dead function names.
    """
    helper_code = _extract_helper_code()
    if not helper_code:
        print("[prune] Could not extract HELPER_CODE_PREFIX")
        return []

    call_graph, func_spans = _build_call_graph(helper_code)
    callers = _get_all_callers(call_graph)
    solution_refs = _functions_in_solutions()

    # Compute reachable set: everything transitively called by safelist functions
    reachable = set(SAFELIST)
    for safe_func in list(SAFELIST):
        if safe_func in call_graph:
            reachable |= _get_transitive_deps(safe_func, call_graph)

    # Also protect anything referenced in solutions
    reachable |= solution_refs

    dead = []
    for func_name in sorted(call_graph.keys()):
        if func_name in reachable:
            continue
        # Check if ANY reachable function calls this one
        if callers.get(func_name, set()) & reachable:
            continue
        dead.append(func_name)

    return dead


def prune_dsl(dry_run=True) -> int:
    """Remove dead functions from dsl.py HELPER_CODE_PREFIX.

    Args:
        dry_run: If True, only report what would be removed.

    Returns:
        Number of functions removed.
    """
    helper_code = _extract_helper_code()
    if not helper_code:
        print("[prune] Could not extract HELPER_CODE_PREFIX")
        return 0

    dead = find_dead_functions()
    if not dead:
        print("[prune] No dead functions found")
        return 0

    print(f"[prune] Found {len(dead)} dead functions")
    if dry_run:
        for fn in dead[:20]:
            print(f"  [dry-run] Would remove: {fn}")
        if len(dead) > 20:
            print(f"  ... and {len(dead) - 20} more")
        return len(dead)

    # Actually remove dead functions from HELPER_CODE_PREFIX
    lines = helper_code.split("\n")
    _, func_spans = _build_call_graph(helper_code)

    # Build set of line ranges to remove (1-indexed from ast)
    remove_ranges = []
    for fn in dead:
        if fn in func_spans:
            start, end = func_spans[fn]
            # Extend to include preceding blank lines and comments
            while start > 1 and (lines[start - 2].strip() == "" or lines[start - 2].strip().startswith("#")):
                start -= 1
            remove_ranges.append((start, end))

    # Sort and merge overlapping ranges
    remove_ranges.sort()
    remove_lines = set()
    for start, end in remove_ranges:
        for i in range(start, end + 1):
            remove_lines.add(i)

    # Rebuild helper code without dead functions
    new_lines = []
    for i, line in enumerate(lines, 1):
        if i not in remove_lines:
            new_lines.append(line)

    new_helper = "\n".join(new_lines)

    # Verify the pruned code still parses
    try:
        ast.parse(new_helper)
    except SyntaxError as e:
        print(f"[prune] ERROR: Pruned code has syntax error: {e}")
        print("[prune] Aborting — dsl.py unchanged")
        return 0

    # Write back to dsl.py
    dsl_text = DSL_PATH.read_text()
    # Replace HELPER_CODE_PREFIX content
    old_prefix = re.search(r"(HELPER_CODE_PREFIX\s*=\s*r?''')(.+?)(''')", dsl_text, re.DOTALL)
    if not old_prefix:
        print("[prune] ERROR: Could not find HELPER_CODE_PREFIX boundaries")
        return 0

    new_dsl = dsl_text[:old_prefix.start(2)] + new_helper + dsl_text[old_prefix.end(2):]
    DSL_PATH.write_text(new_dsl)

    removed = len(dead)
    old_lines = len(lines)
    new_line_count = len(new_lines)
    print(f"[prune] Removed {removed} functions ({old_lines - new_line_count} lines)")
    print(f"[prune] HELPER_CODE_PREFIX: {old_lines} → {new_line_count} lines")

    # Invalidate recognition model cache
    try:
        from dsl_recognition import invalidate_cache
        invalidate_cache()
    except ImportError:
        pass

    return removed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    dry = "--apply" not in sys.argv

    print(f"[prune] Mode: {'DRY RUN' if dry else 'APPLYING CHANGES'}")
    print(f"[prune] Safelist: {len(SAFELIST)} functions protected")

    helper_code = _extract_helper_code()
    call_graph, func_spans = _build_call_graph(helper_code)
    print(f"[prune] Total functions in HELPER_CODE_PREFIX: {len(call_graph)}")

    solution_refs = _functions_in_solutions()
    print(f"[prune] Functions referenced in solutions/hypotheses: {len(solution_refs)}")

    dead = find_dead_functions()
    print(f"[prune] Dead functions: {len(dead)}")

    if dead:
        print("\nDead functions:")
        for fn in sorted(dead):
            print(f"  {fn}")

    if not dry and dead:
        print(f"\nProceeding to remove {len(dead)} functions...")
        removed = prune_dsl(dry_run=False)
        print(f"\nDone. Removed {removed} functions.")
    elif dead:
        print(f"\nRun with --apply to actually remove these functions.")
