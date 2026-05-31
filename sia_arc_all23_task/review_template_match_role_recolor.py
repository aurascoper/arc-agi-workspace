"""Cold review for Claude's template_match_role_recolor synthetic family.

This is coordination-only validation for a generator dropped outside the repo
(default: newest ~/Downloads/template_match_role_recolor_v*.py). It imports only the
generator's `generate_family`, then reimplements the oracle and diagnostic
siblings independently from the text spec:

- rule: match neutral work objects to legend entries by exact canonical shape;
- definition sibling: match by bounding-box shape instead;
- domain sibling: use a literal row bound H=13;
- baseline siblings: size/slot/nearest and pair-0 memorized mapping.
- blind sibling floor: enumerate simple shape-feature match keys and literal
  row/column bounds that were not named by Claude's note.

The output is a stable JSON readout for Codex/Claude polling. It separates
blocking findings from declared deferred surfaces so a family can be reviewed
without pretending every intentionally unforced primitive has been certified. It
is not a live candidate and never edits the solver.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import hashlib
from collections import Counter
from pathlib import Path
from types import ModuleType
from zoneinfo import ZoneInfo
from datetime import datetime


WORKSPACE = Path(__file__).resolve().parent.parent
DEFAULT_GENERATOR_GLOB = "template_match_role_recolor_v*.py"
OUT = WORKSPACE / "tmp" / "template_match_role_recolor_latest_review.json"

N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
N8 = N4 + ((1, 1), (1, -1), (-1, 1), (-1, -1))
LEG_CLO = 0
LEG_CHI = 2
WORK_CLO = 4
HARDCODED_H = 13
HARDCODED_W = 15


def version_key(path: Path) -> tuple[int, float, str]:
    match = re.search(r"_v(\d+)\.py$", path.name)
    version = int(match.group(1)) if match else -1
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (version, mtime, path.name)


def file_fingerprint(path: Path) -> dict:
    data = path.read_bytes()
    return {
        "name": path.name,
        "path": str(path),
        "version": version_key(path)[0],
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "mtime_cdt": datetime.fromtimestamp(path.stat().st_mtime, ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M:%S %Z"),
    }


def default_generator_path() -> Path:
    candidates = sorted((Path.home() / "Downloads").glob(DEFAULT_GENERATOR_GLOB), key=version_key)
    if not candidates:
        return Path.home() / "Downloads" / "template_match_role_recolor_v1.py"
    return candidates[-1]


def available_generators() -> list[dict]:
    return [
        file_fingerprint(path)
        for path in sorted((Path.home() / "Downloads").glob(DEFAULT_GENERATOR_GLOB), key=version_key)
    ]


def load_generator(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("template_match_role_recolor_generator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not import generator at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "generate_family"):
        raise RuntimeError(f"{path} does not expose generate_family")
    return module


def canon(cells):
    mr = min(r for r, _ in cells)
    mc = min(c for _, c in cells)
    return frozenset((r - mr, c - mc) for r, c in cells)


def bbox(cells):
    rs = [r for r, _ in cells]
    cs = [c for _, c in cells]
    return (max(rs) - min(rs) + 1, max(cs) - min(cs) + 1)


def perimeter(cells):
    pts = set(cells)
    return sum(1 for r, c in pts for dr, dc in N4 if (r + dr, c + dc) not in pts)


def row_profile(cells):
    pts = canon(cells)
    counts = Counter(r for r, _ in pts)
    return tuple(counts[r] for r in range(max(counts) + 1))


def col_profile(cells):
    pts = canon(cells)
    counts = Counter(c for _, c in pts)
    return tuple(counts[c] for c in range(max(counts) + 1))


def holes(cells):
    pts = set(canon(cells))
    h, w = bbox(pts)
    outside = set()
    stack = [(-1, -1)]
    while stack:
        r, c = stack.pop()
        if (r, c) in outside or (r, c) in pts or not (-1 <= r <= h and -1 <= c <= w):
            continue
        outside.add((r, c))
        for dr, dc in N4:
            stack.append((r + dr, c + dc))
    return sum(1 for r in range(h) for c in range(w) if (r, c) not in pts and (r, c) not in outside)


def canon_d4(cells):
    pts = list(canon(cells))

    def variants(r, c):
        return [
            (r, c), (r, -c), (-r, c), (-r, -c),
            (c, r), (c, -r), (-c, r), (-c, -r),
        ]

    forms = []
    for idx in range(8):
        transformed = [variants(r, c)[idx] for r, c in pts]
        forms.append(tuple(sorted(canon(transformed))))
    return min(forms)


def centroid(cells):
    return (sum(r for r, _ in cells) / len(cells), sum(c for _, c in cells) / len(cells))


def objects(grid, bg, rlo, rhi, clo, chi, neigh=N4):
    h, w = len(grid), len(grid[0])
    rhi = min(rhi, h - 1)
    chi = min(chi, w - 1)
    seen = [[False] * w for _ in range(h)]
    out = []
    for r in range(rlo, rhi + 1):
        for c in range(clo, chi + 1):
            if seen[r][c] or grid[r][c] == bg:
                continue
            color = grid[r][c]
            stack = [(r, c)]
            seen[r][c] = True
            cells = []
            while stack:
                rr, cc = stack.pop()
                cells.append((rr, cc))
                for dr, dc in neigh:
                    nr, nc = rr + dr, cc + dc
                    if rlo <= nr <= rhi and clo <= nc <= chi and not seen[nr][nc] and grid[nr][nc] == color:
                        seen[nr][nc] = True
                        stack.append((nr, nc))
            out.append({"color": color, "cells": frozenset(cells)})
    return out


def legend_entries(grid, bg, rhi=None, chi=LEG_CHI, neigh=N4):
    if rhi is None:
        rhi = len(grid) - 1
    entries = []
    for obj in objects(grid, bg, 0, rhi, LEG_CLO, chi, neigh=neigh):
        cells = obj["cells"]
        entries.append({
            "color": obj["color"],
            "cells": cells,
            "canon": canon(cells),
            "bbox": bbox(cells),
            "top": min(r for r, _ in cells),
            "centroid": centroid(cells),
        })
    entries.sort(key=lambda row: row["top"])
    return entries


def work_objects(grid, bg, query, rhi=None, chi=None, neigh=N4):
    if rhi is None:
        rhi = len(grid) - 1
    if chi is None:
        chi = len(grid[0]) - 1
    rows = []
    for obj in objects(grid, bg, 0, rhi, WORK_CLO, chi, neigh=neigh):
        if obj["color"] == query:
            cells = obj["cells"]
            rows.append({"cells": cells, "canon": canon(cells), "bbox": bbox(cells), "centroid": centroid(cells)})
    rows.sort(key=lambda row: (min(r for r, _ in row["cells"]), min(c for _, c in row["cells"])))
    return rows


def apply_recolor(inp, work_rows, color_of):
    out = [row[:] for row in inp]
    for row in work_rows:
        color = color_of(row)
        if color is None:
            continue
        for r, c in row["cells"]:
            out[r][c] = color
    return out


def solve_by_shape(inp, bg, query):
    legend = legend_entries(inp, bg)
    by_shape = {row["canon"]: row["color"] for row in legend}
    work = work_objects(inp, bg, query)
    return apply_recolor(inp, work, lambda row: by_shape.get(row["canon"]))


def solve_by_bbox(inp, bg, query):
    legend = legend_entries(inp, bg)
    by_box = {}
    for row in legend:
        by_box.setdefault(row["bbox"], row["color"])
    work = work_objects(inp, bg, query)
    return apply_recolor(inp, work, lambda row: by_box.get(row["bbox"]))


def solve_by_width(inp, bg, query):
    legend = legend_entries(inp, bg)
    by_width = {}
    for row in legend:
        by_width.setdefault(row["bbox"][1], row["color"])
    work = work_objects(inp, bg, query)
    return apply_recolor(inp, work, lambda row: by_width.get(row["bbox"][1]))


def solve_by_height(inp, bg, query):
    legend = legend_entries(inp, bg)
    by_height = {}
    for row in legend:
        by_height.setdefault(row["bbox"][0], row["color"])
    work = work_objects(inp, bg, query)
    return apply_recolor(inp, work, lambda row: by_height.get(row["bbox"][0]))


def solve_by_shape_d4(inp, bg, query):
    legend = legend_entries(inp, bg)
    by_d4 = {}
    for row in legend:
        by_d4.setdefault(canon_d4(row["cells"]), row["color"])
    work = work_objects(inp, bg, query)
    return apply_recolor(inp, work, lambda row: by_d4.get(canon_d4(row["cells"])))


def solve_by_shape_8conn(inp, bg, query):
    legend = legend_entries(inp, bg, neigh=N8)
    by_shape = {row["canon"]: row["color"] for row in legend}
    work = work_objects(inp, bg, query, neigh=N8)
    return apply_recolor(inp, work, lambda row: by_shape.get(row["canon"]))


def solve_by_size(inp, bg, query):
    legend = legend_entries(inp, bg)
    by_size = {}
    for row in legend:
        by_size.setdefault(len(row["cells"]), row["color"])
    work = work_objects(inp, bg, query)
    return apply_recolor(inp, work, lambda row: by_size.get(len(row["cells"])))


def solve_by_slot(inp, bg, query):
    legend = legend_entries(inp, bg)
    work = work_objects(inp, bg, query)
    return apply_recolor(inp, work, lambda row: legend[work.index(row) % len(legend)]["color"])


def solve_by_nearest(inp, bg, query):
    legend = legend_entries(inp, bg)
    work = work_objects(inp, bg, query)

    def nearest(row):
        rr, cc = row["centroid"]
        best = min(legend, key=lambda entry: (entry["centroid"][0] - rr) ** 2 + (entry["centroid"][1] - cc) ** 2)
        return best["color"]

    return apply_recolor(inp, work, nearest)


def solve_hardcoded_h(inp, bg, query):
    rhi = HARDCODED_H - 1
    legend = legend_entries(inp, bg, rhi=rhi)
    by_shape = {row["canon"]: row["color"] for row in legend}
    work = work_objects(inp, bg, query, rhi=rhi)
    return apply_recolor(inp, work, lambda row: by_shape.get(row["canon"]))


def solve_hardcoded_w(inp, bg, query):
    chi = min(HARDCODED_W - 1, len(inp[0]) - 1)
    legend = legend_entries(inp, bg, chi=min(LEG_CHI, chi))
    by_shape = {row["canon"]: row["color"] for row in legend}
    work = work_objects(inp, bg, query, chi=chi)
    return apply_recolor(inp, work, lambda row: by_shape.get(row["canon"]))


def solve_literal_col_bound(inp, bg, query, chi):
    literal_chi = min(chi, len(inp[0]) - 1)
    legend = legend_entries(inp, bg, chi=min(LEG_CHI, literal_chi))
    by_shape = {row["canon"]: row["color"] for row in legend}
    work = work_objects(inp, bg, query, chi=literal_chi)
    return apply_recolor(inp, work, lambda row: by_shape.get(row["canon"]))


def solve_literal_row_bound(inp, bg, query, rhi):
    literal_rhi = min(rhi, len(inp) - 1)
    legend = legend_entries(inp, bg, rhi=literal_rhi)
    by_shape = {row["canon"]: row["color"] for row in legend}
    work = work_objects(inp, bg, query, rhi=literal_rhi)
    return apply_recolor(inp, work, lambda row: by_shape.get(row["canon"]))


def solve_unique_role_once(inp, bg, query):
    legend = legend_entries(inp, bg)
    by_shape = {row["canon"]: row["color"] for row in legend}
    work = work_objects(inp, bg, query)
    used = set()

    def color_of(row):
        color = by_shape.get(row["canon"])
        if color is None or color in used:
            return None
        used.add(color)
        return color

    return apply_recolor(inp, work, color_of)


def solve_bijection_next_unused(inp, bg, query):
    """Greedy injective role assignment.

    Use the exact matched role if it has not been used yet; otherwise assign the
    next unused legend role in slot order. This checks the looser joint-constraint
    family Claude discussed separately from the stricter skip-if-used sibling.
    """
    legend = legend_entries(inp, bg)
    by_shape = {row["canon"]: row["color"] for row in legend}
    work = work_objects(inp, bg, query)
    used = set()

    def color_of(row):
        exact = by_shape.get(row["canon"])
        if exact is None:
            return None
        if exact not in used:
            used.add(exact)
            return exact
        for entry in legend:
            color = entry["color"]
            if color not in used:
                used.add(color)
                return color
        return None

    return apply_recolor(inp, work, color_of)


def pair0_table_solver(task):
    bg = task["meta"]["bg"]
    query = task["meta"]["query"]
    first_inp = task["train"][0][0]
    table = {row["canon"]: row["color"] for row in legend_entries(first_inp, bg)}

    def solve(inp, _bg, _query):
        work = work_objects(inp, bg, query)
        return apply_recolor(inp, work, lambda row: table.get(row["canon"]))

    return solve


def shape_key_functions():
    return {
        "blind_by_size": lambda row: len(row["cells"]),
        "blind_by_bbox": lambda row: row["bbox"],
        "blind_by_width": lambda row: row["bbox"][1],
        "blind_by_height": lambda row: row["bbox"][0],
        "blind_by_bbox_area": lambda row: row["bbox"][0] * row["bbox"][1],
        "blind_by_extent_sum": lambda row: row["bbox"][0] + row["bbox"][1],
        "blind_by_perimeter": lambda row: perimeter(row["cells"]),
        "blind_by_row_profile": lambda row: row_profile(row["cells"]),
        "blind_by_col_profile": lambda row: col_profile(row["cells"]),
        "blind_by_sorted_profiles": lambda row: tuple(sorted((row_profile(row["cells"]), col_profile(row["cells"])))),
        "blind_by_holes": lambda row: holes(row["cells"]),
        "blind_by_d4": lambda row: canon_d4(row["cells"]),
    }


def shape_key_solvers():
    key_fns = shape_key_functions()

    def make_solver(key_fn):
        def solve(inp, bg, query):
            legend = legend_entries(inp, bg)
            table = {}
            for row in legend:
                table.setdefault(key_fn(row), row["color"])
            work = work_objects(inp, bg, query)
            return apply_recolor(inp, work, lambda row: table.get(key_fn(row)))

        return solve

    return {name: make_solver(fn) for name, fn in key_fns.items()}


def collision_groups(entries, key_fn):
    groups = {}
    for row in entries:
        groups.setdefault(key_fn(row), set()).add(row["canon"])
    return {repr(key): sorted([sorted(cells) for cells in canons]) for key, canons in groups.items() if len(canons) > 1}


def admits_task(task, solver) -> bool:
    bg = task["meta"]["bg"]
    query = task["meta"]["query"]
    return all(solver(inp, bg, query) == out for inp, out in task["train"])


def admitted_literal_bounds(task):
    bg = task["meta"]["bg"]
    query = task["meta"]["query"]
    max_h = max(len(inp) for inp, _ in task["train"])
    max_w = max(len(inp[0]) for inp, _ in task["train"])
    cols = []
    rows = []
    for chi in range(WORK_CLO, max_w - 1):
        if admits_task(task, lambda inp, bg, query, chi=chi: solve_literal_col_bound(inp, bg, query, chi)):
            cols.append(chi)
    for rhi in range(max_h - 1):
        if admits_task(task, lambda inp, bg, query, rhi=rhi: solve_literal_row_bound(inp, bg, query, rhi)):
            rows.append(rhi)
    return {"cols": cols, "rows": rows}


def task_domain(task):
    dims = sorted({(len(inp), len(inp[0])) for inp, _out in task["train"]})
    legend_boxes = []
    for inp, _out in task["train"]:
        bg = task["meta"]["bg"]
        boxes = [row["bbox"] for row in legend_entries(inp, bg)]
        legend_boxes.append(boxes)
    return {"dims": dims, "legend_bboxes": legend_boxes}


def main() -> None:
    generator_path = Path(os.environ["TEMPLATE_MATCH_ROLE_RECOLOR_GENERATOR"]).expanduser() \
        if os.environ.get("TEMPLATE_MATCH_ROLE_RECOLOR_GENERATOR") else default_generator_path()
    module = load_generator(generator_path)
    seeds = list(range(30))
    num_tasks = 8
    solvers = {
        "by_shape_rule": solve_by_shape,
        "by_bbox": solve_by_bbox,
        "by_width": solve_by_width,
        "by_height": solve_by_height,
        "by_shape_d4": solve_by_shape_d4,
        "by_shape_8conn": solve_by_shape_8conn,
        "by_size": solve_by_size,
        "by_slot": solve_by_slot,
        "by_nearest": solve_by_nearest,
        "hardcoded_H": solve_hardcoded_h,
        "hardcoded_W": solve_hardcoded_w,
        "unique_role_once": solve_unique_role_once,
        "bijection_next_unused": solve_bijection_next_unused,
    }
    admitted = {name: 0 for name in solvers}
    admitted["pair0_table"] = 0
    blind_key_fns = shape_key_functions()
    blind_solvers = shape_key_solvers()
    blind_admitted = {name: 0 for name in blind_solvers}
    blind_task_collision_counts = {name: 0 for name in blind_solvers}
    blind_pair_collision_counts = {name: 0 for name in blind_solvers}
    blind_collision_examples = {name: [] for name in blind_solvers}
    blind_global_collision_keys = {name: {} for name in blind_solvers}
    literal_bound_admitted = {"literal_col_bound_any": 0, "literal_row_bound_any": 0}
    per_seed = []
    oracle_mismatches = 0
    all_dims = Counter()
    examples = {name: [] for name in admitted}
    blind_examples = {name: [] for name in blind_solvers}
    literal_bound_examples = {name: [] for name in literal_bound_admitted}

    for seed in seeds:
        family = module.generate_family(seed=seed, num_tasks=num_tasks)
        seed_counts = {name: 0 for name in admitted}
        for task_index, task in enumerate(family):
            for inp, out in task["train"] + task.get("test", []):
                if solve_by_shape(inp, task["meta"]["bg"], task["meta"]["query"]) != out:
                    oracle_mismatches += 1
            for dim in task_domain(task)["dims"]:
                all_dims[str(dim)] += 1
            task_collision_seen = {name: False for name in blind_solvers}
            for pair_index, (inp, _out) in enumerate(task["train"]):
                entries = legend_entries(inp, task["meta"]["bg"])
                for name, key_fn in blind_key_fns.items():
                    collisions = collision_groups(entries, key_fn)
                    for key, canons in collisions.items():
                        blind_global_collision_keys[name].setdefault(key, set()).update(
                            tuple(tuple(cell) for cell in canon_cells) for canon_cells in canons
                        )
                    if collisions:
                        blind_pair_collision_counts[name] += 1
                        task_collision_seen[name] = True
                        if len(blind_collision_examples[name]) < 5:
                            blind_collision_examples[name].append({
                                "seed": seed,
                                "task_index": task_index,
                                "pair_index": pair_index,
                                "collisions": collisions,
                                "domain": task_domain(task),
                            })
            for name, seen in task_collision_seen.items():
                if seen:
                    blind_task_collision_counts[name] += 1
            for name, solver in solvers.items():
                if admits_task(task, solver):
                    admitted[name] += 1
                    seed_counts[name] += 1
                    if name != "by_shape_rule" and len(examples[name]) < 5:
                        examples[name].append({"seed": seed, "task_index": task_index, "domain": task_domain(task)})
            table_solver = pair0_table_solver(task)
            if admits_task(task, table_solver):
                admitted["pair0_table"] += 1
                seed_counts["pair0_table"] += 1
                if len(examples["pair0_table"]) < 5:
                    examples["pair0_table"].append({"seed": seed, "task_index": task_index, "domain": task_domain(task)})
            for name, solver in blind_solvers.items():
                if admits_task(task, solver):
                    blind_admitted[name] += 1
                    if len(blind_examples[name]) < 5:
                        blind_examples[name].append({"seed": seed, "task_index": task_index, "domain": task_domain(task)})
            bounds = admitted_literal_bounds(task)
            if bounds["cols"]:
                literal_bound_admitted["literal_col_bound_any"] += 1
                if len(literal_bound_examples["literal_col_bound_any"]) < 5:
                    literal_bound_examples["literal_col_bound_any"].append({
                        "seed": seed,
                        "task_index": task_index,
                        "bounds": bounds["cols"],
                        "domain": task_domain(task),
                    })
            if bounds["rows"]:
                literal_bound_admitted["literal_row_bound_any"] += 1
                if len(literal_bound_examples["literal_row_bound_any"]) < 5:
                    literal_bound_examples["literal_row_bound_any"].append({
                        "seed": seed,
                        "task_index": task_index,
                        "bounds": bounds["rows"],
                        "domain": task_domain(task),
                    })
        per_seed.append({"seed": seed, "admitted": seed_counts})

    total_tasks = len(seeds) * num_tasks
    blocking_findings = []
    deferred_survivors = []
    if admitted["by_size"]:
        blocking_findings.append({
            "name": "by_size",
            "axis": "definition/correspondence",
            "admitted_tasks": admitted["by_size"],
            "distinguishing_grid": "legend/work shapes where size collision does not imply exact shape match",
            "fix": "force size-collision pairs on >=2 train instances per task",
        })
    if admitted["by_slot"]:
        blocking_findings.append({
            "name": "by_slot",
            "axis": "definition/correspondence",
            "admitted_tasks": admitted["by_slot"],
            "distinguishing_grid": "work object reading order diverges from legend slot order",
            "fix": "force slot/order divergence on >=2 train instances per task",
        })
    if admitted["by_nearest"]:
        blocking_findings.append({
            "name": "by_nearest",
            "axis": "definition/correspondence",
            "admitted_tasks": admitted["by_nearest"],
            "distinguishing_grid": "nearest legend entry differs from exact shape match",
            "fix": "force spatial-nearest divergence on >=2 train instances per task",
        })
    if admitted["pair0_table"]:
        blocking_findings.append({
            "name": "pair0_table",
            "axis": "domain/mapping",
            "admitted_tasks": admitted["pair0_table"],
            "distinguishing_grid": "shape->colour legend assignment differs from pair 0",
            "fix": "force mapping variation for every shape used by work objects",
        })
    if admitted["unique_role_once"]:
        blocking_findings.append({
            "name": "unique_role_once",
            "axis": "binding/global",
            "admitted_tasks": admitted["unique_role_once"],
            "distinguishing_grid": "repeated work shapes require repeated role colour, not one-use bijection",
            "fix": "force repeated matched shapes/roles on >=2 train instances per task",
        })
    if admitted["bijection_next_unused"]:
        blocking_findings.append({
            "name": "bijection_next_unused",
            "axis": "binding/global",
            "admitted_tasks": admitted["bijection_next_unused"],
            "distinguishing_grid": "repeated work shapes require repeated role colour, not a greedy injective fallback",
            "fix": "force repeated matched shapes/roles on >=2 train instances per task",
        })
    if admitted["by_bbox"]:
        blocking_findings.append({
            "name": "by_bbox",
            "axis": "definition/correspondence",
            "admitted_tasks": admitted["by_bbox"],
            "distinguishing_grid": "legend contains two shapes with same bbox but different canonical cells",
            "fix": "force bbox-collision pairs on >=2 train instances per task",
        })
    if admitted["by_width"]:
        blocking_findings.append({
            "name": "by_width",
            "axis": "definition/correspondence",
            "admitted_tasks": admitted["by_width"],
            "distinguishing_grid": "legend contains two shapes with same width but different canonical cells",
            "fix": "force width-collision pairs on >=2 train instances per task",
        })
    if admitted["by_height"]:
        blocking_findings.append({
            "name": "by_height",
            "axis": "definition/correspondence",
            "admitted_tasks": admitted["by_height"],
            "distinguishing_grid": "legend contains two shapes with same height but different canonical cells",
            "fix": "force height-collision pairs on >=2 train instances per task",
        })
    if admitted["hardcoded_H"]:
        blocking_findings.append({
            "name": "hardcoded_H",
            "axis": "domain/dimension",
            "admitted_tasks": admitted["hardcoded_H"],
            "distinguishing_grid": "vary grid height and place a work object in rows outside the literal H=13 bound",
            "fix": "vary H as well as W",
        })
    if admitted["hardcoded_W"]:
        blocking_findings.append({
            "name": "hardcoded_W",
            "axis": "domain/dimension",
            "admitted_tasks": admitted["hardcoded_W"],
            "distinguishing_grid": "place work objects in columns outside a literal W=15 bound",
            "fix": "force work-area occupancy beyond the smallest width on >=2 train instances per task",
        })
    for name, count in literal_bound_admitted.items():
        if count:
            blocking_findings.append({
                "name": name,
                "axis": "domain/dimension",
                "admitted_tasks": count,
                "distinguishing_grid": "literal work-area row/column bounds survive when every train object stays inside them",
                "fix": "force extremal work-area occupancy on >=2 train instances/task for both row and column axes",
            })
    blind_blocking_findings = []
    blind_tail_findings = []
    blind_deferred_names = {"blind_by_d4"}
    blind_floor_names = {"blind_by_size", "blind_by_bbox", "blind_by_width", "blind_by_height"}
    for name, count in blind_admitted.items():
        if name in blind_deferred_names:
            continue
        if count:
            forceability = {
                "task_collision_count": blind_task_collision_counts.get(name, 0),
                "pair_collision_count": blind_pair_collision_counts.get(name, 0),
                "global_collision_keys": {
                    key: [list(canon_cells) for canon_cells in sorted(canons)]
                    for key, canons in blind_global_collision_keys.get(name, {}).items()
                },
            }
            finding = {
                "name": name,
                "axis": "definition/correspondence",
                "admitted_tasks": count,
                "distinguishing_grid": "blind shape-feature key matches legend/work where exact canonical shape should be required",
                "fix": "add >=2 train collisions for this feature key or document it as an explicit deferred tail",
                "floor_feature": name in blind_floor_names,
                "forceability": forceability,
            }
            if forceability["task_collision_count"] == 0:
                finding["declared_scope"] = (
                    "No generated train task co-locates a collision for this feature key; "
                    "treat as a tail/unforced-domain surface rather than a forceable blocker "
                    "until a same-task collision is shown."
                )
                blind_tail_findings.append(finding)
            else:
                blind_blocking_findings.append(finding)
                blocking_findings.append(finding)
    if admitted["by_shape_d4"]:
        deferred_survivors.append({
            "name": "by_shape_d4",
            "axis": "definition/correspondence",
            "admitted_tasks": admitted["by_shape_d4"],
            "distinguishing_grid": "legend/work shapes whose D4-canonical identity differs from exact canonical identity",
            "fix": "force orientation-sensitive correspondence collisions on >=2 train instances per task",
            "declared_scope": "D4-canonical shape matching is documented as deferred in the generator spec.",
        })
    if admitted["by_shape_8conn"]:
        deferred_survivors.append({
            "name": "by_shape_8conn",
            "axis": "definition/individuation",
            "admitted_tasks": admitted["by_shape_8conn"],
            "distinguishing_grid": "diagonally touching same-colour objects where 4-connectivity and 8-connectivity disagree",
            "fix": "force diagonal-touch individuation cases on >=2 train instances per task",
            "declared_scope": "8-connected object individuation is documented as deferred in the generator spec.",
        })
    deferred_survivors.extend(blind_tail_findings)
    if oracle_mismatches:
        verdict = "oracle_mismatch"
    elif blocking_findings:
        verdict = "not_ledger_safe"
    elif deferred_survivors:
        verdict = "passes_review_with_deferred_scope"
    else:
        verdict = "passes_review"

    out = {
        "artifact": "template_match_role_recolor_latest_review",
        "generated_cdt": datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "generator_path": str(generator_path),
        "generator_name": generator_path.name,
        "generator_version": version_key(generator_path)[0],
        "generator_sha256": file_fingerprint(generator_path)["sha256"],
        "available_generators": available_generators(),
        "seeds": seeds,
        "num_tasks_per_seed": num_tasks,
        "total_tasks": total_tasks,
        "review_scope": {
            "v1": "reproduces and extends named sibling checks; not a full blind sibling enumerator",
            "open_ended_additions": [
                "D4-canonical shape matching",
                "8-connected object individuation",
                "literal width bound",
                "unique-role-once binding constraint",
                "blind shape-feature key grammar",
                "literal row/column bound enumeration",
            ],
            "v2_requirement": (
                "If Claude provides v2, treat this reviewer as a starting floor and add any new "
                "surfaces suggested by v2's generator, especially transfer and unmatched-object semantics."
            ),
        },
        "oracle_mismatches": oracle_mismatches,
        "admitted_counts": admitted,
        "admitted_rates": {name: admitted[name] / total_tasks for name in sorted(admitted)},
        "blind_admitted_counts": blind_admitted,
        "blind_admitted_rates": {name: blind_admitted[name] / total_tasks for name in sorted(blind_admitted)},
        "blind_blocking_findings": blind_blocking_findings,
        "blind_tail_findings": blind_tail_findings,
        "blind_collision_diagnostics": {
            name: {
                "task_collision_count": blind_task_collision_counts[name],
                "pair_collision_count": blind_pair_collision_counts[name],
                "examples": blind_collision_examples[name],
                "global_collision_keys": {
                    key: [list(canon_cells) for canon_cells in sorted(canons)]
                    for key, canons in blind_global_collision_keys[name].items()
                },
            }
            for name in sorted(blind_solvers)
        },
        "literal_bound_admitted_counts": literal_bound_admitted,
        "literal_bound_examples": literal_bound_examples,
        "dimension_histogram": dict(sorted(all_dims.items())),
        "examples": examples,
        "blind_examples": blind_examples,
        "findings": blocking_findings,
        "blocking_findings": blocking_findings,
        "deferred_survivors": deferred_survivors,
        "verdict": verdict,
        "notes": [
            "This reviewer imports only generate_family and reimplements oracle/siblings independently.",
            "The artifact is method-track evidence only and never a live candidate.",
            "Nonzero D4/8conn counts are reported as deferred survivors when the generator declares those surfaces out of scope.",
        ],
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(
        f"wrote {OUT.relative_to(WORKSPACE)} verdict={out['verdict']} "
        f"findings={[f['name'] for f in blocking_findings]} "
        f"deferred={[f['name'] for f in deferred_survivors]}"
    )
    print(f"admitted={admitted} oracle_mismatches={oracle_mismatches}/{total_tasks}")


if __name__ == "__main__":
    main()
