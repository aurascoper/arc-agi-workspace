"""Design-only host-apex router probe for 3dc255db-like tasks.

This script formalizes the narrow hypothesis raised by the relational lane:
erased marker fragments select adjacent host objects, the host object's sparse
bbox side gives a ray direction, and the marker component count gives a clipped
ray length.

It is not a Kaggle candidate. It uses train outputs to fit and audit the marker
selector, and uses the local test output only as a readout after fitting.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

WORKSPACE = Path(__file__).resolve().parent
TASK_ID = "3dc255db"
TASK_PATH = WORKSPACE / "arc_agi_2_data" / "evaluation" / f"{TASK_ID}.json"
OUT_PATH = WORKSPACE / "tmp" / "codex_host_apex_router_probe.json"

Grid = list[list[int]]
Predicate = Callable[[dict[str, int]], bool]


def background(grid: Grid) -> int:
    return Counter(value for row in grid for value in row).most_common(1)[0][0]


def colors(grid: Grid) -> list[int]:
    bg = background(grid)
    return sorted({value for row in grid for value in row if value != bg})


def cells_of_color(grid: Grid, color: int) -> set[tuple[int, int]]:
    return {
        (r, c)
        for r, row in enumerate(grid)
        for c, value in enumerate(row)
        if value == color
    }


def components(cells: set[tuple[int, int]], conn: int = 8) -> list[set[tuple[int, int]]]:
    todo = set(cells)
    out: list[set[tuple[int, int]]] = []
    dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    if conn == 8:
        dirs += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    while todo:
        start = todo.pop()
        stack = [start]
        comp = {start}
        while stack:
            r, c = stack.pop()
            for dr, dc in dirs:
                nb = (r + dr, c + dc)
                if nb in todo:
                    todo.remove(nb)
                    comp.add(nb)
                    stack.append(nb)
        out.append(comp)
    return out


def bbox(cells: set[tuple[int, int]]) -> tuple[int, int, int, int]:
    rows = [r for r, _c in cells]
    cols = [c for _r, c in cells]
    return min(rows), min(cols), max(rows), max(cols)


def color_features(grid: Grid, color: int) -> dict[str, int]:
    bg = background(grid)
    h, w = len(grid), len(grid[0])
    cells = cells_of_color(grid, color)
    r0, c0, r1, c1 = bbox(cells)
    area = (r1 - r0 + 1) * (c1 - c0 + 1)
    comps4 = components(cells, 4)
    comps8 = components(cells, 8)
    adjacent_colors: set[int] = set()
    adjacent_cell_count = 0
    for r, c in cells:
        touches_other = False
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if not (dr or dc):
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < h and 0 <= nc < w and grid[nr][nc] not in (bg, color):
                    adjacent_colors.add(grid[nr][nc])
                    touches_other = True
        adjacent_cell_count += int(touches_other)
    edge_counts = {
        "above": sum((r0, c) in cells for c in range(c0, c1 + 1)),
        "below": sum((r1, c) in cells for c in range(c0, c1 + 1)),
        "left": sum((r, c0) in cells for r in range(r0, r1 + 1)),
        "right": sum((r, c1) in cells for r in range(r0, r1 + 1)),
    }
    edge_min = min(edge_counts.values())
    return {
        "size": len(cells),
        "bbox_h": r1 - r0 + 1,
        "bbox_w": c1 - c0 + 1,
        "area": area,
        "ncomp4": len(comps4),
        "ncomp8": len(comps8),
        "maxcomp4": max(len(comp) for comp in comps4),
        "maxcomp8": max(len(comp) for comp in comps8),
        "adj_color_count": len(adjacent_colors),
        "adj_cell_count": adjacent_cell_count,
        "sparse_side_count": sum(count == edge_min for count in edge_counts.values()),
        "edge_min": edge_min,
        "edge_max": max(edge_counts.values()),
        "touch_border": int(any(r in (0, h - 1) or c in (0, w - 1) for r, c in cells)),
    }


def marker_labels(pair: dict[str, Grid]) -> set[int]:
    inp, out = pair["input"], pair["output"]
    bg = background(inp)
    labels: set[int] = set()
    for r in range(len(inp)):
        for c in range(len(inp[0])):
            if inp[r][c] != bg and out[r][c] == bg:
                labels.add(inp[r][c])
    return labels


def atom_bank(pairs: list[dict[str, Grid]]) -> list[tuple[tuple[str, str, int], Predicate]]:
    rows = []
    for pair in pairs:
        labels = marker_labels(pair)
        for color in colors(pair["input"]):
            rows.append((color_features(pair["input"], color), color in labels))
    keys = list(rows[0][0])
    atoms: list[tuple[tuple[str, str, int], Predicate]] = []
    for key in keys:
        for threshold in sorted({features[key] for features, _label in rows}):
            for op in ("<=", ">=", "=="):
                def predicate(features: dict[str, int], key: str = key, threshold: int = threshold, op: str = op) -> bool:
                    if op == "<=":
                        return features[key] <= threshold
                    if op == ">=":
                        return features[key] >= threshold
                    return features[key] == threshold

                if any(predicate(features) for features, _label in rows):
                    atoms.append(((key, op, threshold), predicate))
    return atoms


def fit_marker_predicates(pairs: list[dict[str, Grid]]) -> list[tuple[tuple[str, str, int], Predicate]]:
    rows = []
    for pair in pairs:
        labels = marker_labels(pair)
        for color in colors(pair["input"]):
            rows.append((color_features(pair["input"], color), color in labels))
    return [
        (desc, predicate)
        for desc, predicate in atom_bank(pairs)
        if all(predicate(features) == label for features, label in rows)
    ]


def sparse_sides(cells: set[tuple[int, int]]) -> tuple[list[str], tuple[int, int, int, int]]:
    r0, c0, r1, c1 = bbox(cells)
    edge_counts = {
        "above": sum((r0, c) in cells for c in range(c0, c1 + 1)),
        "below": sum((r1, c) in cells for c in range(c0, c1 + 1)),
        "left": sum((r, c0) in cells for r in range(r0, r1 + 1)),
        "right": sum((r, c1) in cells for r in range(r0, r1 + 1)),
    }
    edge_min = min(edge_counts.values())
    return [side for side, count in edge_counts.items() if count == edge_min], (r0, c0, r1, c1)


def choose_side(
    sides: list[str],
    marker_cells: set[tuple[int, int]],
    host_bbox: tuple[int, int, int, int],
    mode: str,
) -> str:
    r0, c0, r1, c1 = host_bbox
    marker_r = sum(r for r, _c in marker_cells) / len(marker_cells)
    marker_c = sum(c for _r, c in marker_cells) / len(marker_cells)
    if mode == "top_left":
        for side in ("above", "left", "right", "below"):
            if side in sides:
                return side
    scores = {
        "above": marker_r - r0,
        "below": r1 - marker_r,
        "left": marker_c - c0,
        "right": c1 - marker_c,
    }
    tie_break = {"left": 3, "above": 2, "right": 1, "below": 0}
    return max(sides, key=lambda side: (scores[side], tie_break[side]))


def ray_anchor(side: str, host_cells: set[tuple[int, int]], host_bbox: tuple[int, int, int, int]) -> tuple[int, int]:
    r0, c0, r1, c1 = host_bbox
    if side in ("left", "right"):
        col = c0 if side == "left" else c1
        edge_rows = [r for r, c in host_cells if c == col]
        row = round(sum(edge_rows) / len(edge_rows))
        return row, col - 1 if side == "left" else col + 1
    row = r0 if side == "above" else r1
    edge_cols = [c for r, c in host_cells if r == row]
    col = round(sum(edge_cols) / len(edge_cols))
    return row - 1 if side == "above" else row + 1, col


def ray_cells(side: str, start: tuple[int, int], length: int, h: int, w: int) -> list[tuple[int, int]]:
    r, c = start
    out = []
    for i in range(length):
        rr, cc = r, c
        if side == "left":
            cc -= i
        elif side == "right":
            cc += i
        elif side == "above":
            rr -= i
        else:
            rr += i
        if 0 <= rr < h and 0 <= cc < w:
            out.append((rr, cc))
    return out


def apply_router(grid: Grid, predicate: Predicate, side_mode: str) -> Grid:
    bg = background(grid)
    h, w = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    color_cells = {color: cells_of_color(grid, color) for color in colors(grid)}
    marker_colors = [
        color
        for color in color_cells
        if predicate(color_features(grid, color))
    ]
    for marker in marker_colors:
        marker_cells = color_cells[marker]
        host_groups: dict[int, set[tuple[int, int]]] = defaultdict(set)
        for comp in components(marker_cells, 8):
            adjacent_hosts: set[int] = set()
            for r, c in comp:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if not (dr or dc):
                            continue
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < h and 0 <= nc < w and grid[nr][nc] not in (bg, marker):
                            adjacent_hosts.add(grid[nr][nc])
            for host in adjacent_hosts:
                host_groups[host] |= comp
        for host, assigned_markers in host_groups.items():
            if host not in color_cells:
                continue
            host_cells = color_cells[host]
            sides, host_bbox = sparse_sides(host_cells)
            side = choose_side(sides, assigned_markers, host_bbox, side_mode)
            start = ray_anchor(side, host_cells, host_bbox)
            border_distance = (
                w - start[1]
                if side == "right"
                else start[1] + 1
                if side == "left"
                else start[0] + 1
                if side == "above"
                else h - start[0]
            )
            length = max(0, min(len(assigned_markers), border_distance))
            for r, c in assigned_markers:
                out[r][c] = bg
            for r, c in ray_cells(side, start, length, h, w):
                out[r][c] = marker
    return out


def diff_count(a: Grid, b: Grid) -> int | None:
    if len(a) != len(b) or len(a[0]) != len(b[0]):
        return None
    return sum(a[r][c] != b[r][c] for r in range(len(b)) for c in range(len(b[0])))


def exact_candidates(pairs: list[dict[str, Grid]]) -> list[dict[str, Any]]:
    candidates = []
    for desc, predicate in fit_marker_predicates(pairs):
        for side_mode in ("farthest_lex", "top_left"):
            diffs = [
                diff_count(apply_router(pair["input"], predicate, side_mode), pair["output"])
                for pair in pairs
            ]
            if diffs and sum(diff or 0 for diff in diffs) == 0:
                candidates.append({"predicate": desc, "side_mode": side_mode, "train_diffs": diffs})
    return candidates


def main() -> None:
    task = json.loads(TASK_PATH.read_text())
    train = task["train"]
    candidates = exact_candidates(train)
    loo = []
    for hold_idx in range(len(train)):
        fit_pairs = [pair for idx, pair in enumerate(train) if idx != hold_idx]
        held = train[hold_idx]
        held_ok = []
        for candidate in exact_candidates(fit_pairs):
            desc = tuple(candidate["predicate"])
            predicate = dict(fit_marker_predicates(fit_pairs))[desc]
            diff = diff_count(apply_router(held["input"], predicate, candidate["side_mode"]), held["output"])
            if diff == 0:
                held_ok.append({"predicate": desc, "side_mode": candidate["side_mode"]})
        loo.append({"heldout_index": hold_idx, "passing_candidates": held_ok, "passed": bool(held_ok)})

    test_readout = []
    for candidate in candidates:
        desc = tuple(candidate["predicate"])
        predicate = dict(fit_marker_predicates(train))[desc]
        test_readout.append({
            "predicate": desc,
            "side_mode": candidate["side_mode"],
            "test_diffs": [
                diff_count(apply_router(test["input"], predicate, candidate["side_mode"]), test["output"])
                for test in task["test"]
                if "output" in test
            ],
            "test_marker_colors": [
                sorted(
                    color
                    for color in colors(test["input"])
                    if predicate(color_features(test["input"], color))
                )
                for test in task["test"]
            ],
        })

    report = {
        "task_id": TASK_ID,
        "probe": "host_apex_router",
        "train_exact_candidates": candidates,
        "loo": loo,
        "loo_passed": all(row["passed"] for row in loo),
        "test_readout": test_readout,
        "promotion_status": (
            "rejected: train-exact candidates fail leave-one-train-out"
            if candidates and not all(row["passed"] for row in loo)
            else "no_train_exact_candidate"
            if not candidates
            else "candidate_needs_independent_invariance_checks"
        ),
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2))
    print(json.dumps({
        "train_exact_candidate_count": len(candidates),
        "loo_passed": report["loo_passed"],
        "promotion_status": report["promotion_status"],
        "test_readout": test_readout[:3],
        "out": str(OUT_PATH),
    }, indent=2))


if __name__ == "__main__":
    main()
