"""
tests_dsl.py — Correctness tests for dsl.py (codopt --test target).
Ensures dsl.py is valid Python, has required exports, and core invariants hold.
"""

import sys


def test_loads():
    """dsl.py must load without errors."""
    ns = {}
    exec(open("dsl.py").read(), ns)
    assert "HELPER_CODE_PREFIX" in ns, "Missing HELPER_CODE_PREFIX"
    print("PASS: dsl.py loads and exports HELPER_CODE_PREFIX")
    return ns


def test_helpers_exec(ns):
    """HELPER_CODE_PREFIX must be valid Python."""
    helper_code = ns["HELPER_CODE_PREFIX"]
    assert isinstance(helper_code, str), "HELPER_CODE_PREFIX is not a string"
    assert len(helper_code) > 100, "HELPER_CODE_PREFIX is too short"
    helper_ns = {}
    exec(helper_code, helper_ns)
    print(f"PASS: HELPER_CODE_PREFIX executes ({len(helper_code)} chars)")
    return helper_ns


def test_core_functions(helper_ns):
    """Core grid manipulation functions must exist."""
    required = [
        "get_objects", "detect_background_color", "copy_grid",
        "rotate_cw", "mirror_h", "shape", "palette",
        "color_counts", "get_bbox", "flood_fill",
    ]
    missing = [f for f in required if f not in helper_ns]
    assert not missing, f"Missing core functions: {missing}"
    print(f"PASS: All {len(required)} core functions present")


def test_grid_operations(helper_ns):
    """Basic grid operations must produce correct results."""
    grid = [[1, 2], [3, 4]]

    # copy_grid
    copy = helper_ns["copy_grid"](grid)
    assert copy == grid, "copy_grid failed"
    copy[0][0] = 99
    assert grid[0][0] == 1, "copy_grid is not a deep copy"

    # shape
    s = helper_ns["shape"](grid)
    assert s == (2, 2), f"shape returned {s}, expected (2, 2)"

    # rotate_cw (90 degrees)
    rotated = helper_ns["rotate_cw"](grid)
    assert len(rotated) == 2 and len(rotated[0]) == 2, "rotate_cw wrong dimensions"

    # mirror_h
    mirrored = helper_ns["mirror_h"](grid)
    assert mirrored == [[2, 1], [4, 3]], f"mirror_h returned {mirrored}"

    print("PASS: Grid operations produce correct results")


def test_no_syntax_cruft(ns):
    """HELPER_CODE_PREFIX should not contain unmatched quotes or broken syntax."""
    code = ns["HELPER_CODE_PREFIX"]
    # Quick check: try compiling
    compile(code, "<helper_code>", "exec")
    print("PASS: HELPER_CODE_PREFIX compiles cleanly")


def main():
    try:
        ns = test_loads()
        helper_ns = test_helpers_exec(ns)
        test_core_functions(helper_ns)
        test_grid_operations(helper_ns)
        test_no_syntax_cruft(ns)
        print("\nAll tests passed.")
        sys.exit(0)
    except Exception as e:
        print(f"\nFAIL: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
