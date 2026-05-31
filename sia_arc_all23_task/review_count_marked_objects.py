"""Cold review for Claude's count_marked_objects synthetic family.

This is a coordination-only verifier. It imports only the newest
``generate_family`` dropped in ``~/Downloads/count_marked_objects*v*.py`` and
reimplements the oracle plus sibling integer solvers independently from the text
spec. It never edits the live ARC solver.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from types import ModuleType
from zoneinfo import ZoneInfo


WORKSPACE = Path(__file__).resolve().parent.parent
OUT = WORKSPACE / "tmp" / "count_marked_objects_latest_review.json"
DEFAULT_GENERATOR_GLOB = "count_marked_objects*v*.py"

N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
N8 = N4 + ((1, 1), (1, -1), (-1, 1), (-1, -1))
ROWCONN = ((0, 1), (0, -1))
COLCONN = ((1, 0), (-1, 0))


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
        return Path.home() / "Downloads" / "count_marked_objects_v5.py"
    return candidates[-1]


def available_generators() -> list[dict]:
    return [
        file_fingerprint(path)
        for path in sorted((Path.home() / "Downloads").glob(DEFAULT_GENERATOR_GLOB), key=version_key)
    ]


def load_generator(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("count_marked_objects_generator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not import generator at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "generate_family"):
        raise RuntimeError(f"{path} does not expose generate_family")
    return module


def modal_bg(grid):
    return Counter(v for row in grid for v in row).most_common(1)[0][0]


def interior_bounds(grid):
    return 2, len(grid) - 1, 1, len(grid[0]) - 1


def components(grid, color, rmin, rmax, cmin, cmax, neigh=N4):
    h, w = len(grid), len(grid[0])
    rmin = max(0, rmin)
    cmin = max(0, cmin)
    rmax = min(rmax, h - 1)
    cmax = min(cmax, w - 1)
    if rmin > rmax or cmin > cmax:
        return []
    seen = [[False] * w for _ in range(h)]
    out = []
    for r in range(rmin, rmax + 1):
        for c in range(cmin, cmax + 1):
            if seen[r][c] or grid[r][c] != color:
                continue
            stack = [(r, c)]
            seen[r][c] = True
            cells = []
            while stack:
                rr, cc = stack.pop()
                cells.append((rr, cc))
                for dr, dc in neigh:
                    nr, nc = rr + dr, cc + dc
                    if rmin <= nr <= rmax and cmin <= nc <= cmax and not seen[nr][nc] and grid[nr][nc] == color:
                        seen[nr][nc] = True
                        stack.append((nr, nc))
            out.append(frozenset(cells))
    return out


def count_target(grid):
    return len(components(grid, grid[0][0], *interior_bounds(grid), N4))


def render(inp, n, tally_color):
    out = [row[:] for row in inp]
    for idx in range(n):
        out[0][2 + idx] = tally_color
    return out


def tally_len(out, tally):
    return sum(1 for v in out[0] if v == tally)


def cells_color(grid, color):
    return sum(row.count(color) for row in grid)


def all_object_count(grid, bg):
    h, w = len(grid), len(grid[0])
    colors = set(v for row in grid for v in row) - {bg}
    return sum(len(components(grid, color, 0, h - 1, 0, w - 1, N4)) for color in colors)


def obj_count_color_whole(grid, color):
    return len(components(grid, color, 0, len(grid) - 1, 0, len(grid[0]) - 1, N4))


def max_run(grid, color):
    h, w = len(grid), len(grid[0])
    best = 0
    for r in range(h):
        run = 0
        for c in range(w):
            run = run + 1 if grid[r][c] == color else 0
            best = max(best, run)
    for c in range(w):
        run = 0
        for r in range(h):
            run = run + 1 if grid[r][c] == color else 0
            best = max(best, run)
    return best


def selectors(grid, bg, nonbg, rlo, rhi, clo, chi):
    if not nonbg:
        return []
    obj_by = {color: len(components(grid, color, rlo, rhi, clo, chi, N4)) for color in nonbg}
    cell_by = {color: cells_color(grid, color) for color in nonbg}
    top_left = None
    for r in range(rlo, rhi + 1):
        for c in range(clo, chi + 1):
            if grid[r][c] != bg:
                top_left = grid[r][c]
                break
        if top_left is not None:
            break
    return [
        ("rarest_by_objects", min(obj_by, key=lambda color: (obj_by[color], color))),
        ("commonest_by_objects", max(obj_by, key=lambda color: (obj_by[color], -color))),
        ("rarest_by_cells", min(cell_by, key=lambda color: (cell_by[color], color))),
        ("commonest_by_cells", max(cell_by, key=lambda color: (cell_by[color], -color))),
        ("topleft", top_left),
        ("min_index", min(nonbg)),
        ("max_index", max(nonbg)),
    ]


def sibling_counts(grid):
    bg = modal_bg(grid)
    target = grid[0][0]
    rlo, rhi, clo, chi = interior_bounds(grid)
    nonbg = set(v for row in grid for v in row) - {bg}
    n_true = count_target(grid)
    target_objs = components(grid, target, rlo, rhi, clo, chi, N4)
    out = {}

    out["all_objects_wholegrid"] = all_object_count(grid, bg)
    out["target_objects_wholegrid"] = obj_count_color_whole(grid, target)
    out["distractor_objects"] = all_object_count(grid, bg) - obj_count_color_whole(grid, target)
    out["target_objects_8conn"] = len(components(grid, target, rlo, rhi, clo, chi, N8))
    out["target_objects_rowconn"] = len(components(grid, target, rlo, rhi, clo, chi, ROWCONN))
    out["target_objects_colconn"] = len(components(grid, target, rlo, rhi, clo, chi, COLCONN))
    out["region_drop_top"] = len(components(grid, target, rlo + 1, rhi, clo, chi, N4))
    out["region_drop_bottom"] = len(components(grid, target, rlo, rhi - 1, clo, chi, N4))
    out["region_drop_left"] = len(components(grid, target, rlo, rhi, clo + 1, chi, N4))
    out["region_drop_right"] = len(components(grid, target, rlo, rhi, clo, chi - 1, N4))

    target_cells = cells_color(grid, target)
    out["target_cells"] = target_cells
    for k in (2, 3, 4):
        out[f"target_cells_div{k}"] = target_cells // k
    out["total_nonbg_cells"] = sum(1 for row in grid for value in row if value != bg)
    interior_objs = []
    for color in nonbg:
        interior_objs.extend(components(grid, color, rlo, rhi, clo, chi, N4))
    if interior_objs:
        out["largest_obj_size"] = max(len(obj) for obj in interior_objs)
        out["smallest_obj_size"] = min(len(obj) for obj in interior_objs)
    out["num_distinct_nonbg_colors"] = len(nonbg)
    out["max_run_target"] = max_run(grid, target)

    cells = [(r, c) for r in range(rlo, rhi + 1) for c in range(clo, chi + 1) if grid[r][c] != bg]
    if cells:
        rs = [r for r, _ in cells]
        cs = [c for _, c in cells]
        out["bbox_h_interior"] = max(rs) - min(rs) + 1
        out["bbox_w_interior"] = max(cs) - min(cs) + 1
    target_cells_rc = [(r, c) for r in range(rlo, rhi + 1) for c in range(clo, chi + 1) if grid[r][c] == target]
    out["distinct_target_rows"] = len(set(r for r, _ in target_cells_rc))
    out["distinct_target_cols"] = len(set(c for _, c in target_cells_rc))

    for selector_name, selector_color in selectors(grid, bg, nonbg, rlo, rhi, clo, chi):
        out[f"selcount_{selector_name}"] = len(components(grid, selector_color, rlo, rhi, clo, chi, N4))

    for color in range(10):
        out[f"count_color_{color}"] = len(components(grid, color, rlo, rhi, clo, chi, N4))
    for k in (4, 5, 6, 7):
        out[f"cap_at_{k}"] = min(n_true, k)
    for k in (1, 2, 3, 4, 5, 6):
        out[f"count_size_le_{k}"] = sum(1 for obj in target_objs if len(obj) <= k)
    for k in (2, 3, 5, 6):
        out[f"count_size_ge_{k}"] = sum(1 for obj in target_objs if len(obj) >= k)
    out.update(region_grow_counts(grid, target))
    return out


def region_grow_counts(grid, target):
    h, w = len(grid), len(grid[0])
    return {
        "grow_keep_row1": len(components(grid, target, 1, h - 1, 1, w - 1, N4)),
        "grow_keep_col0": len(components(grid, target, 2, h - 1, 0, w - 1, N4)),
        "grow_keep_both": len(components(grid, target, 1, h - 1, 0, w - 1, N4)),
    }


def literal_dim_counts(task):
    dims = sorted({(len(inp), len(inp[0])) for inp, _out in task["train"]})
    max_h = max(h for h, _ in dims)
    max_w = max(w for _, w in dims)
    candidates = []
    for h in range(8, max_h + 1):
        for w in range(8, max_w + 1):
            if h >= max_h and w >= max_w:
                continue
            candidates.append((h, w))
    return candidates


def task_ns(task):
    tally = task["meta"].get("tally")
    return [tally_len(out, tally) for _inp, out in task["train"]]


def disagreements(task, int_fn):
    ns = task_ns(task)
    vals = [int_fn(inp) for inp, _out in task["train"]]
    return sum(1 for got, want in zip(vals, ns) if got != want), vals, ns


def task_domain(task):
    return {
        "dims": sorted({(len(inp), len(inp[0])) for inp, _out in task["train"]}),
        "targets": [inp[0][0] for inp, _out in task["train"]],
        "train_N": task_ns(task),
    }


def main() -> None:
    generator_path = Path(os.environ["COUNT_MARKED_OBJECTS_GENERATOR"]).expanduser() \
        if os.environ.get("COUNT_MARKED_OBJECTS_GENERATOR") else default_generator_path()
    module = load_generator(generator_path)
    seeds = list(range(40))
    num_tasks = 8
    total_tasks = len(seeds) * num_tasks

    admitted = Counter()
    fragile = Counter()
    literal_dim_admitted_cases = 0
    literal_dim_fragile_cases = 0
    literal_dim_admitted_tasks = set()
    literal_dim_fragile_tasks = set()
    examples = {}
    fragile_examples = {}
    literal_examples = {"admitted": [], "fragile": []}
    oracle_mismatches = 0
    output_count_mismatches = 0

    documented_scope = {
        "grow_keep_row1": "category-c region-grow: reserved margin is load-bearing by spec",
        "grow_keep_col0": "category-c region-grow: reserved margin is load-bearing by spec",
        "grow_keep_both": "category-c region-grow: reserved margin is load-bearing by spec",
        "cap_at_7": "finite N tail: family domain has N<=7",
        "count_size_le_6": "finite object-size tail: family domain has target object size<=6",
    }
    near_tail = {
        "cap_at_6": "one-pair N=7 distinguisher in every task; exact-train rejected but not a two-pair LOO floor",
    }

    for seed in seeds:
        family = module.generate_family(seed=seed, num_tasks=num_tasks)
        for task_index, task in enumerate(family):
            tally = task["meta"].get("tally")
            for inp, out in task["train"] + task.get("test", []):
                n = count_target(inp)
                if tally_len(out, tally) != n:
                    output_count_mismatches += 1
                if render(inp, n, tally) != out:
                    oracle_mismatches += 1
            names = sorted(sibling_counts(task["train"][0][0]))
            for name in names:
                diff, vals, ns = disagreements(task, lambda inp, name=name: sibling_counts(inp)[name])
                if diff == 0:
                    admitted[name] += 1
                    examples.setdefault(name, [])
                    if len(examples[name]) < 5:
                        examples[name].append({"seed": seed, "task_index": task_index, "vals": vals, "Ns": ns, "domain": task_domain(task)})
                elif diff < 2:
                    fragile[name] += 1
                    fragile_examples.setdefault(name, [])
                    if len(fragile_examples[name]) < 5:
                        fragile_examples[name].append({"seed": seed, "task_index": task_index, "diffs": diff, "vals": vals, "Ns": ns, "domain": task_domain(task)})
            for h, w in literal_dim_counts(task):
                diff, vals, ns = disagreements(
                    task,
                    lambda inp, h=h, w=w: len(components(inp, inp[0][0], 2, h - 1, 1, w - 1, N4)),
                )
                if diff == 0:
                    literal_dim_admitted_cases += 1
                    literal_dim_admitted_tasks.add((seed, task_index))
                    if len(literal_examples["admitted"]) < 5:
                        literal_examples["admitted"].append({"seed": seed, "task_index": task_index, "box": [h, w], "vals": vals, "Ns": ns, "domain": task_domain(task)})
                elif diff < 2:
                    literal_dim_fragile_cases += 1
                    literal_dim_fragile_tasks.add((seed, task_index))
                    if len(literal_examples["fragile"]) < 5:
                        literal_examples["fragile"].append({"seed": seed, "task_index": task_index, "box": [h, w], "diffs": diff, "vals": vals, "Ns": ns, "domain": task_domain(task)})

    blocking = []
    scope_survivors = []
    weak_tail = []
    for name, count in sorted(admitted.items()):
        if name in documented_scope:
            scope_survivors.append({"name": name, "admitted_tasks": count, "scope": documented_scope[name]})
        else:
            blocking.append({
                "name": name,
                "kind": "train_exact_sibling",
                "admitted_tasks": count,
                "fix": "force this sibling to disagree on train or document it as a scoped tail/category-c survivor",
            })
    for name, count in sorted(fragile.items()):
        if name in documented_scope or name in near_tail:
            weak_tail.append({"name": name, "fragile_tasks": count, "scope": documented_scope.get(name) or near_tail.get(name)})
        else:
            blocking.append({
                "name": name,
                "kind": "loo_fragile_sibling",
                "admitted_tasks": count,
                "fix": "force this sibling to disagree on >=2 train pairs/task or document why one-pair rejection is sufficient",
            })
    if literal_dim_admitted_cases:
        blocking.append({
            "name": "literal_dim_admitted",
            "kind": "domain/dimension",
            "admitted_tasks": len(literal_dim_admitted_tasks),
            "admitted_cases": literal_dim_admitted_cases,
            "fix": "ensure every literal interior box smaller than max train dimensions undercounts on train",
        })
    if literal_dim_fragile_cases:
        blocking.append({
            "name": "literal_dim_fragile",
            "kind": "domain/dimension",
            "admitted_tasks": len(literal_dim_fragile_tasks),
            "admitted_cases": literal_dim_fragile_cases,
            "fix": "force every smaller literal interior box to disagree on >=2 train pairs/task",
        })

    if oracle_mismatches or output_count_mismatches:
        verdict = "oracle_mismatch"
    elif blocking:
        verdict = "not_ledger_safe"
    elif scope_survivors or weak_tail:
        verdict = "passes_review_with_scope"
    else:
        verdict = "passes_review"

    out = {
        "artifact": "count_marked_objects_latest_review",
        "generated_cdt": datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "generator_path": str(generator_path),
        "generator_name": generator_path.name,
        "generator_version": version_key(generator_path)[0],
        "generator_sha256": file_fingerprint(generator_path)["sha256"],
        "available_generators": available_generators(),
        "seeds": seeds,
        "num_tasks_per_seed": num_tasks,
        "total_tasks": total_tasks,
        "oracle_mismatches": oracle_mismatches,
        "output_count_mismatches": output_count_mismatches,
        "admitted_counts": dict(sorted(admitted.items())),
        "fragile_lt2_counts": dict(sorted(fragile.items())),
        "literal_dim_admitted_cases": literal_dim_admitted_cases,
        "literal_dim_fragile_cases": literal_dim_fragile_cases,
        "literal_dim_admitted_tasks": len(literal_dim_admitted_tasks),
        "literal_dim_fragile_tasks": len(literal_dim_fragile_tasks),
        "blocking_findings": blocking,
        "scope_survivors": scope_survivors,
        "weak_tail": weak_tail,
        "examples": examples,
        "fragile_examples": fragile_examples,
        "literal_dim_examples": literal_examples,
        "verdict": verdict,
        "review_scope": {
            "imports": "Only generate_family is imported; oracle and siblings are reimplemented independently.",
            "seeds": "40 seeds x 8 tasks = 320 tasks, matching the v5 stated cross-seed scale.",
            "documented_scope": documented_scope,
            "near_tail": near_tail,
        },
        "notes": [
            "This is method-track synthetic evidence only; it is not a live solver candidate.",
            "Blocking findings include exact-train siblings and non-tail one-pair/LOO-fragile siblings.",
            "Documented region-grow and finite-domain cap/size tails are reported separately.",
        ],
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(
        f"wrote {OUT.relative_to(WORKSPACE)} verdict={verdict} "
        f"blockers={[(row['name'], row['admitted_tasks']) for row in blocking]} "
        f"scope={[(row['name'], row['admitted_tasks']) for row in scope_survivors]}"
    )


if __name__ == "__main__":
    main()
