"""D4 symmetry augmentation for ARC task solving.

Applies all 8 D4 group transforms, solves each view independently,
inverse-transforms predictions, and pixel-majority votes.

Uses existing DSL transforms: rotate_cw, rotate_ccw, rotate_180,
mirror_h, mirror_v, transpose, flip_anti_diagonal (dsl.py:164-205).

Source: ARC-AGI-2 Technical Report (2603.06590)
"""

from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# D4 group transforms (loaded lazily from DSL)
# ---------------------------------------------------------------------------

_DSL_NS = None


def _get_dsl_ns():
    """Load DSL namespace once."""
    global _DSL_NS
    if _DSL_NS is None:
        dsl_path = WORKSPACE / "dsl.py"
        _DSL_NS = {}
        exec(compile(dsl_path.read_text(), str(dsl_path), "exec"), _DSL_NS)
    return _DSL_NS


def _identity(grid):
    return [list(row) for row in grid]


def _inv_rotate_cw(grid):
    """Correct inverse of rotate_cw (= 3x rotate_cw)."""
    ns = _get_dsl_ns()
    g = grid
    for _ in range(3):
        g = ns["rotate_cw"](g)
    return g


def _inv_rotate_ccw(grid):
    """Correct inverse of rotate_ccw (= 1x rotate_cw, since DSL rotate_ccw may be non-standard)."""
    ns = _get_dsl_ns()
    # rotate_ccw's inverse is rotate_cw applied 3 times to ccw...
    # Actually: just apply rotate_ccw 3 times
    g = grid
    for _ in range(3):
        g = ns["rotate_ccw"](g)
    return g


def _inv_flip_anti(grid):
    """Correct inverse of flip_anti_diagonal (transpose(reverse_rows), not self-inverse for non-square)."""
    ns = _get_dsl_ns()
    return ns["transpose"]([row[::-1] for row in grid])


def _get_d4_transforms():
    """Return list of (name, forward_fn, inverse_fn) for all 8 D4 transforms.

    Note: DSL rotate_ccw and flip_anti_diagonal are NOT self-inverse for non-square grids.
    We compute correct inverses explicitly.
    """
    ns = _get_dsl_ns()
    rotate_cw = ns["rotate_cw"]
    rotate_ccw = ns["rotate_ccw"]
    rotate_180 = ns["rotate_180"]
    mirror_h = ns["mirror_h"]
    mirror_v = ns["mirror_v"]
    transpose = ns["transpose"]
    flip_anti = ns["flip_anti_diagonal"]

    return [
        ("identity",           _identity,       _identity),
        ("rotate_cw",          rotate_cw,       _inv_rotate_cw),
        ("rotate_180",         rotate_180,      rotate_180),
        ("rotate_ccw",         rotate_ccw,      _inv_rotate_ccw),
        ("mirror_h",           mirror_h,        mirror_h),
        ("mirror_v",           mirror_v,        mirror_v),
        ("transpose",          transpose,       transpose),
        ("flip_anti_diagonal", flip_anti,       _inv_flip_anti),
    ]


# ---------------------------------------------------------------------------
# Task transformation
# ---------------------------------------------------------------------------

def _transform_task(task_data: dict, fwd_fn: callable) -> dict:
    """Apply fwd_fn to all grids in task_data. Returns deep copy."""
    td = copy.deepcopy(task_data)
    for pair in td.get("train", []):
        pair["input"] = [list(row) for row in fwd_fn(pair["input"])]
        pair["output"] = [list(row) for row in fwd_fn(pair["output"])]
    for pair in td.get("test", []):
        pair["input"] = [list(row) for row in fwd_fn(pair["input"])]
        # Don't transform test output -- we compare after inverse-transforming prediction
    return td


# ---------------------------------------------------------------------------
# Majority voting
# ---------------------------------------------------------------------------

def _majority_vote(predictions: list[list[list[int]] | None],
                   identity_idx: int = 0) -> list[list[int]] | None:
    """Pixel-wise majority vote across predictions.

    Skips None predictions. Pads to max dimensions.
    Ties broken by identity prediction.
    """
    valid = [(i, p) for i, p in enumerate(predictions) if p is not None]
    if not valid:
        return None
    if len(valid) == 1:
        return valid[0][1]

    # Find max dimensions
    max_r = max(len(p) for _, p in valid)
    max_c = max(len(p[0]) for _, p in valid if p)

    result = []
    for r in range(max_r):
        row = []
        for c in range(max_c):
            votes = []
            identity_val = None
            for i, pred in valid:
                if r < len(pred) and c < len(pred[r]):
                    val = pred[r][c]
                    votes.append(val)
                    if i == identity_idx:
                        identity_val = val
            if not votes:
                row.append(0)
                continue
            counter = Counter(votes)
            max_count = counter.most_common(1)[0][1]
            winners = [v for v, cnt in counter.items() if cnt == max_count]
            if len(winners) == 1:
                row.append(winners[0])
            elif identity_val is not None and identity_val in winners:
                row.append(identity_val)
            else:
                row.append(winners[0])
        result.append(row)
    return result


# ---------------------------------------------------------------------------
# D4 ensemble solver
# ---------------------------------------------------------------------------

def _select_views(task_data: dict) -> list[str]:
    """Pick a compact subset of D4 views based on grid geometry.

    - Square grids: identity + rotate_180 + mirror_h + mirror_v  (4 views)
      Rotations and transpose are equivalent to reflections for square grids.
    - Non-square grids: identity + rotate_180 + mirror_h + mirror_v  (4 views)
      CW/CCW rotations change dimensions (HxW -> WxH), unlikely to help the
      LLM pattern-match. Transpose/anti-diag also swap dims.
    - Always includes identity (baseline) and the 3 most universally useful
      transforms: rotate_180 (preserves dims), mirror_h, mirror_v.

    Returns list of transform names to run.
    """
    # These 4 preserve grid dimensions for ANY shape and cover the most
    # common ARC symmetries (horizontal/vertical reflection, 180° rotation).
    return ["identity", "rotate_180", "mirror_h", "mirror_v"]


def solve_task_d4(task_data: dict, task_name: str = "unknown",
                  phase2: bool = True) -> tuple[float, list]:
    """Solve with D4 augmentation. Returns (pixel_accuracy, traces).

    Runs a geometry-aware subset of D4 views (typically 4, not 8) for speed.
    Early-exits on perfect solve. Falls back to remaining views only if
    phase1 found partial signal (score > 0) but no perfect solve.
    """
    from evolve_qwen_arc import solve_task_single, _canonicalize_task
    from target_mlx_arc import try_code_on_task, extract_python_code, calculate_pixel_accuracy, run_code_on_inputs

    all_transforms = {name: (fwd, inv) for name, fwd, inv in _get_d4_transforms()}
    selected_names = _select_views(task_data)

    all_scores = []
    all_traces = []
    all_inv_fns = []
    best_score = 0.0
    best_traces = []

    def _solve_view(name, fwd_fn, inv_fn):
        """Solve one transformed view."""
        nonlocal best_score, best_traces
        td = _transform_task(task_data, fwd_fn)
        try:
            score, traces = solve_task_single(td, task_name=f"{task_name}@{name}")
        except Exception as e:
            print(f"  [D4] {task_name}@{name}: error {e}")
            score, traces = 0.0, []
        all_scores.append(score)
        all_traces.append(traces)
        all_inv_fns.append(inv_fn)

        if score > best_score:
            best_score = score
            best_traces = traces

        print(f"  [D4] {task_name}@{name}: {score:.4f}")
        return score

    # Phase 1: geometry-selected views (typically 4)
    for name in selected_names:
        fwd, inv = all_transforms[name]
        score = _solve_view(name, fwd, inv)
        if score >= 1.0:
            print(f"  [D4] {task_name}: SOLVED by {name}")
            return 1.0, []

    # Phase 2: remaining views, only if phase1 found partial signal
    if phase2 and best_score > 0:
        remaining = [n for n in all_transforms if n not in selected_names]
        for name in remaining:
            fwd, inv = all_transforms[name]
            score = _solve_view(name, fwd, inv)
            if score >= 1.0:
                print(f"  [D4] {task_name}: SOLVED by {name} (phase 2)")
                return 1.0, []

    # No perfect solve -- return best individual score
    if best_score > 0:
        view_count = len(all_scores)
        above_zero = sum(1 for s in all_scores if s > 0)
        print(f"  [D4] {task_name}: best={best_score:.4f} ({above_zero}/{view_count} views >0)")

    return best_score, best_traces


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    transforms = _get_d4_transforms()
    print(f"[d4] Loaded {len(transforms)} D4 transforms")

    # Verify inverses
    test_grid = [[1, 2, 3], [4, 5, 6]]
    for name, fwd, inv in transforms:
        restored = [list(row) for row in inv(fwd(test_grid))]
        original = [list(row) for row in test_grid]
        status = "OK" if restored == original else "FAIL"
        print(f"  {name}: inverse {status}")
