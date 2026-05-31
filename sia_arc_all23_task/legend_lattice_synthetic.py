"""Synthetic legend/lattice invariance harness for the quarantined DSL lane.

This is not a live solver. It generates ARC-like legend/lattice tasks from a
small spec, fits the unchanged `legend_component_underfill` DSL program on
synthetic train pairs, and evaluates synthetic held-out pairs. The purpose is
to separate "one-task structural wrapper" from a reusable legend/lattice
abstraction without touching Kaggle attempts.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import dsl_interpreter as DSL


WORKSPACE = Path(__file__).resolve().parent.parent
OUT = WORKSPACE / "tmp" / "legend_lattice_synthetic_latest.json"

BACKGROUND = 8
SEPARATOR = 6
DRAW = 3
ALT = 2
GLYPH_COLORS = [0, 1, 4, 5, 7, 9]


def blank(h: int, w: int, fill: int = BACKGROUND) -> DSL.Grid:
    return [[fill for _ in range(w)] for _ in range(h)]


def shape_cells(kind: int, extent: int) -> set[tuple[int, int]]:
    mid = extent // 2
    if kind == 0:
        return {(r, 0) for r in range(extent)}
    if kind == 1:
        return {(0, c) for c in range(extent)} | {(r, mid) for r in range(extent)}
    if kind == 2:
        return {(r, 0) for r in range(extent)} | {(extent - 1, c) for c in range(extent)}
    if kind == 3:
        return {(r, min(r, extent - 1)) for r in range(extent)}
    if kind == 4:
        return {(0, c) for c in range(max(1, extent - 1))} | {
            (r, max(0, extent - 2)) for r in range(extent)
        }
    return {(r, c) for r in range(min(extent, 2)) for c in range(min(extent, 2))}


def glyph_key(kind: int, color: int, extent: int) -> tuple[tuple[int, ...], ...]:
    cells = shape_cells(kind, extent)
    rs = [r for r, _c in cells]
    cs = [c for _r, c in cells]
    r0, r1, c0, c1 = min(rs), max(rs), min(cs), max(cs)
    return tuple(
        tuple(color if (r, c) in cells else -1 for c in range(c0, c1 + 1))
        for r in range(r0, r1 + 1)
    )


def draw_glyph(grid: DSL.Grid, r0: int, c0: int, kind: int, color: int, extent: int) -> None:
    for dr, dc in shape_cells(kind, extent):
        grid[r0 + dr][c0 + dc] = color


def underfill_rect(grid: DSL.Grid, r0: int, c0: int, r1: int, c1: int, color: int) -> None:
    h = len(grid)
    w = len(grid[0]) if grid else 0
    for r in range(max(0, r0), min(h - 1, r1) + 1):
        for c in range(max(0, c0), min(w - 1, c1) + 1):
            if grid[r][c] == BACKGROUND:
                grid[r][c] = color


def choose_matched(mode: str, rows: int, cols: int, offset: int) -> set[tuple[int, int]]:
    if mode == "row":
        r = offset % rows
        return {(r, c) for c in range(cols)}
    if mode == "col":
        c = offset % cols
        return {(r, c) for r in range(rows)}
    out = set()
    for r in range(rows):
        c = (r * 2 + offset) % cols
        out.add((r, c))
    if len({r for r, _c in out}) == 1 or len({c for _r, c in out}) == 1:
        out.add(((offset + 1) % rows, (offset + 2) % cols))
    return out


def make_pair(
    *,
    extent: int,
    rows: int,
    cols: int,
    gap: int,
    footer_height: int,
    mode: str,
    offset: int,
    orientation: str,
) -> dict[str, Any]:
    step = extent + gap
    cmin = 1
    legend_count = max(rows, cols)
    content_slots = max(cols, legend_count)
    content_width = cmin + content_slots * extent + (content_slots - 1) * gap + 1
    width = content_width + 1
    legend_top = 1
    first_sep = legend_top + extent + 2
    body_top = first_sep + 2
    second_sep = body_top + rows * extent + (rows - 1) * gap + 1
    height = second_sep + footer_height + 2
    grid = blank(height, width)
    for c in range(cmin, width - 1):
        grid[first_sep][c] = SEPARATOR
        grid[second_sep][c] = SEPARATOR

    slot_specs: dict[tuple[int, int], tuple[int, int]] = {}
    used: set[tuple[int, int]] = set()
    for r in range(rows):
        for c in range(cols):
            idx = r * cols + c + offset
            kind = idx % 6
            color = GLYPH_COLORS[(idx // 6) % len(GLYPH_COLORS)]
            while (kind, color) in used:
                idx += 1
                kind = idx % 6
                color = GLYPH_COLORS[(idx // 6) % len(GLYPH_COLORS)]
            used.add((kind, color))
            slot_specs[(r, c)] = (kind, color)
            draw_glyph(grid, body_top + r * step, cmin + c * step, kind, color, extent)

    matched_slots = choose_matched(mode, rows, cols, offset)
    legend_items = [slot_specs[pos] for pos in sorted(matched_slots)]
    for i, (kind, color) in enumerate(legend_items):
        draw_glyph(grid, legend_top, cmin + i * step, kind, color, extent)

    out = deepcopy(grid)
    render_bboxes = []
    for r, c in sorted(matched_slots):
        r0 = body_top + r * step
        c0 = cmin + c * step
        render_bboxes.append((r0, c0, r0 + extent - 1, c0 + extent - 1))
    aligned = len({r for r, _c in matched_slots}) == 1 or len({c for _r, c in matched_slots}) == 1
    if aligned:
        r0 = min(box[0] for box in render_bboxes) - 1
        c0 = min(box[1] for box in render_bboxes) - 1
        r1 = max(box[2] for box in render_bboxes) + 1
        c1 = max(box[3] for box in render_bboxes) + 1
        underfill_rect(out, r0, c0, r1, c1, DRAW)
        underfill_rect(out, legend_top - 1, cmin, legend_top + extent, width - 2, DRAW)
    else:
        for r0, c0, r1, c1 in render_bboxes:
            underfill_rect(out, r0 - 1, c0 - 1, r1 + 1, c1 + 1, DRAW)
    footer = DRAW if aligned else ALT
    for r in range(second_sep + 1, second_sep + footer_height + 1):
        for c in range(cmin, width - 1):
            if out[r][c] == BACKGROUND:
                out[r][c] = footer

    if orientation != "identity":
        grid = DSL.d4_apply(grid, orientation)
        out = DSL.d4_apply(out, orientation)
    return {
        "input": grid,
        "output": out,
        "meta": {
            "extent": extent,
            "rows": rows,
            "cols": cols,
            "gap": gap,
            "footer_height": footer_height,
            "mode": mode,
            "offset": offset,
            "orientation": orientation,
            "matched_slots": sorted(matched_slots),
        },
    }


def make_task(task_id: str, extent: int, rows: int, cols: int, gap: int, footer_height: int, orientations: list[str]):
    modes = ["row", "col", "scatter", "row", "scatter"]
    pairs = [
        make_pair(
            extent=extent,
            rows=rows,
            cols=cols,
            gap=gap,
            footer_height=footer_height,
            mode=modes[i],
            offset=i + extent + rows,
            orientation=orientations[i % len(orientations)],
        )
        for i in range(5)
    ]
    return {
        "task_id": task_id,
        "train": [{k: pair[k] for k in ("input", "output")} for pair in pairs[:3]],
        "test": [{k: pair[k] for k in ("input", "output")} for pair in pairs[3:]],
        "meta": [pair["meta"] for pair in pairs],
    }


def legend_program() -> DSL.Program:
    for program in DSL.DEFAULT_PROGRAMS:
        if program.get("name") == "legend_component_underfill":
            return program
    raise RuntimeError("legend_component_underfill program not found")


def diff(pred: DSL.Grid, gold: DSL.Grid) -> int | None:
    if DSL.dims(pred) != DSL.dims(gold):
        return None
    return sum(
        pred[r][c] != gold[r][c]
        for r in range(len(gold))
        for c in range(len(gold[0]))
    )


def eval_task(task: dict[str, Any]) -> dict[str, Any]:
    compiled = DSL.compile_program(legend_program(), task["train"])
    if compiled is None:
        return {
            "task_id": task["task_id"],
            "compiled": False,
            "train_exact": False,
            "test_exact": False,
            "meta": task["meta"],
        }
    signature, transform = compiled
    train_diffs = [diff(transform(deepcopy(pair["input"])), pair["output"]) for pair in task["train"]]
    test_diffs = [diff(transform(deepcopy(pair["input"])), pair["output"]) for pair in task["test"]]
    return {
        "task_id": task["task_id"],
        "signature": signature,
        "compiled": True,
        "train_diffs": train_diffs,
        "test_diffs": test_diffs,
        "train_exact": train_diffs == [0] * len(train_diffs),
        "test_exact": test_diffs == [0] * len(test_diffs),
        "meta": task["meta"],
    }


def main() -> None:
    specs = [
        ("legend_lat_a", 2, 3, 4, 2, 1, ["identity", "hflip"]),
        ("legend_lat_b", 3, 4, 3, 2, 2, ["identity", "vflip", "rot90"]),
        ("legend_lat_c", 4, 3, 3, 3, 2, ["rot180", "rot270", "anti_diag"]),
        ("legend_lat_d", 3, 2, 5, 3, 3, ["identity", "rot90", "hflip"]),
        ("legend_lat_e", 5, 3, 2, 2, 1, ["vflip", "rot180", "anti_diag"]),
    ]
    tasks = [make_task(*spec) for spec in specs]
    results = [eval_task(task) for task in tasks]
    out = {
        "artifact": "legend_lattice_synthetic_latest",
        "purpose": "spec-generated held-out variation for unchanged legend_component_underfill",
        "tasks": len(results),
        "train_exact_tasks": [row["task_id"] for row in results if row["train_exact"]],
        "test_exact_tasks": [row["task_id"] for row in results if row["test_exact"]],
        "all_train_exact": all(row["train_exact"] for row in results),
        "all_test_exact": all(row["test_exact"] for row in results),
        "results": results,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {OUT}")
    print(
        f"tasks={out['tasks']} all_train_exact={out['all_train_exact']} "
        f"all_test_exact={out['all_test_exact']} test_exact={out['test_exact_tasks']}"
    )


if __name__ == "__main__":
    main()
