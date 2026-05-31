"""Cold review for Claude's template_match_role_recolor synthetic family.

This is coordination-only validation for a generator dropped outside the repo
(default: newest ~/Downloads/template_match_role_recolor_v*.py). It imports only the
generator's `generate_family`, then reimplements the oracle and diagnostic
siblings independently from the text spec:

- rule: match neutral work objects to legend entries by exact canonical shape;
- definition sibling: match by bounding-box shape instead;
- domain sibling: use a literal row bound H=13;
- baseline siblings: size/slot/nearest and pair-0 memorized mapping.

The output is a stable JSON readout for Codex/Claude polling. It is not a live
candidate and never edits the solver.
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


def pair0_table_solver(task):
    bg = task["meta"]["bg"]
    query = task["meta"]["query"]
    first_inp = task["train"][0][0]
    table = {row["canon"]: row["color"] for row in legend_entries(first_inp, bg)}

    def solve(inp, _bg, _query):
        work = work_objects(inp, bg, query)
        return apply_recolor(inp, work, lambda row: table.get(row["canon"]))

    return solve


def admits_task(task, solver) -> bool:
    bg = task["meta"]["bg"]
    query = task["meta"]["query"]
    return all(solver(inp, bg, query) == out for inp, out in task["train"])


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
        "by_shape_d4": solve_by_shape_d4,
        "by_shape_8conn": solve_by_shape_8conn,
        "by_size": solve_by_size,
        "by_slot": solve_by_slot,
        "by_nearest": solve_by_nearest,
        "hardcoded_H": solve_hardcoded_h,
        "hardcoded_W": solve_hardcoded_w,
        "unique_role_once": solve_unique_role_once,
    }
    admitted = {name: 0 for name in solvers}
    admitted["pair0_table"] = 0
    per_seed = []
    oracle_mismatches = 0
    all_dims = Counter()
    examples = {name: [] for name in admitted}

    for seed in seeds:
        family = module.generate_family(seed=seed, num_tasks=num_tasks)
        seed_counts = {name: 0 for name in admitted}
        for task_index, task in enumerate(family):
            for inp, out in task["train"] + task.get("test", []):
                if solve_by_shape(inp, task["meta"]["bg"], task["meta"]["query"]) != out:
                    oracle_mismatches += 1
            for dim in task_domain(task)["dims"]:
                all_dims[str(dim)] += 1
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
        per_seed.append({"seed": seed, "admitted": seed_counts})

    total_tasks = len(seeds) * num_tasks
    findings = []
    if admitted["by_bbox"]:
        findings.append({
            "name": "by_bbox",
            "axis": "definition/correspondence",
            "admitted_tasks": admitted["by_bbox"],
            "distinguishing_grid": "legend contains two shapes with same bbox but different canonical cells",
            "fix": "force bbox-collision pairs on >=2 train instances per task",
        })
    if admitted["hardcoded_H"]:
        findings.append({
            "name": "hardcoded_H",
            "axis": "domain/dimension",
            "admitted_tasks": admitted["hardcoded_H"],
            "distinguishing_grid": "vary grid height and place a work object in rows outside the literal H=13 bound",
            "fix": "vary H as well as W",
        })
    if admitted["hardcoded_W"]:
        findings.append({
            "name": "hardcoded_W",
            "axis": "domain/dimension",
            "admitted_tasks": admitted["hardcoded_W"],
            "distinguishing_grid": "place work objects in columns outside a literal W=15 bound",
            "fix": "force work-area occupancy beyond the smallest width on >=2 train instances per task",
        })
    if admitted["by_shape_d4"]:
        findings.append({
            "name": "by_shape_d4",
            "axis": "definition/correspondence",
            "admitted_tasks": admitted["by_shape_d4"],
            "distinguishing_grid": "legend/work shapes whose D4-canonical identity differs from exact canonical identity",
            "fix": "force orientation-sensitive correspondence collisions on >=2 train instances per task",
        })
    if admitted["by_shape_8conn"]:
        findings.append({
            "name": "by_shape_8conn",
            "axis": "definition/individuation",
            "admitted_tasks": admitted["by_shape_8conn"],
            "distinguishing_grid": "diagonally touching same-colour objects where 4-connectivity and 8-connectivity disagree",
            "fix": "force diagonal-touch individuation cases on >=2 train instances per task",
        })

    out = {
        "artifact": "template_match_role_recolor_v1_review",
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
            ],
            "v2_requirement": (
                "If Claude provides v2, treat this reviewer as a starting floor and add any new "
                "surfaces suggested by v2's generator, especially transfer and unmatched-object semantics."
            ),
        },
        "oracle_mismatches": oracle_mismatches,
        "admitted_counts": admitted,
        "admitted_rates": {name: admitted[name] / total_tasks for name in sorted(admitted)},
        "dimension_histogram": dict(sorted(all_dims.items())),
        "examples": examples,
        "findings": findings,
        "verdict": "not_ledger_safe" if findings or oracle_mismatches else "passes_review",
        "notes": [
            "This reviewer imports only generate_family and reimplements oracle/siblings independently.",
            "The artifact is method-track evidence only and never a live candidate.",
            "A zero count for D4/8conn on v1 is not closure if the generator deliberately deferred those surfaces.",
        ],
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(WORKSPACE)} verdict={out['verdict']} findings={[f['name'] for f in findings]}")
    print(f"admitted={admitted} oracle_mismatches={oracle_mismatches}/{total_tasks}")


if __name__ == "__main__":
    main()
