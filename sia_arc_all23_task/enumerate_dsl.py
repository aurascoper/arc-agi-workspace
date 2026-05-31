"""Deterministic quarantined DSL frontier scorer for the all-23 task.

This is not a live solver. It enumerates a small, audited set of typed DSL
program skeletons, fits their holes from train pairs, scores train residuals,
and records LOO admission type using the same hardened evaluator.
"""

from __future__ import annotations

import importlib.util
import ast
import inspect
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parent
OUT = WORKSPACE / "tmp" / "dsl_enumeration_latest.json"

import dsl_interpreter as DSL


ALLOWED_STRUCTURAL_INTS = {-1, 0, 1, 2}


def _load_base_evaluator():
    spec = importlib.util.spec_from_file_location("sia_all23_evaluator", HERE / "evaluator.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod._load_base()


def program_space() -> list[dict[str, Any]]:
    recolor_learns = [
        "color_transition_map",
        "dominant_transition_map",
        "full_color_transition_map",
    ]
    programs: list[dict[str, Any]] = []
    for learn in recolor_learns:
        programs.append({
            "name": f"enum_recolor:{learn}",
            "pipeline": [{"op": "recolor_map", "args": {"map": {"learn": learn}}}],
        })
    programs.extend([
        {
            "name": "enum_fill_enclosed:changed_output_color",
            "pipeline": [{"op": "fill_enclosed", "args": {"color": {"learn": "changed_output_color"}}}],
        },
        {
            "name": "enum_route_singletons:same",
            "pipeline": [{"op": "route_singletons", "args": {"color": "same"}}],
        },
        {
            "name": "enum_bar_route:bg_draw",
            "pipeline": [{"op": "bar_bracket_route", "args": {"color": {"learn": "bg_draw_color"}}}],
        },
        {
            "name": "enum_bar_marker_route:full_map+bg_draw",
            "pipeline": [{
                "op": "bar_marker_bracket_route",
                "args": {
                    "map": {"learn": "full_color_transition_map"},
                    "color": {"learn": "bg_draw_color"},
                },
            }],
        },
    ])
    for learn in recolor_learns:
        programs.append({
            "name": f"enum_recolor_then_bar_route:{learn}+bg_draw",
            "pipeline": [
                {"op": "recolor_map", "args": {"map": {"learn": learn}}},
                {"op": "bar_bracket_route", "args": {"color": {"learn": "bg_draw_color"}}},
            ],
        })
        programs.append({
            "name": f"enum_bar_route_then_recolor:bg_draw+{learn}",
            "pipeline": [
                {"op": "bar_bracket_route", "args": {"color": {"learn": "bg_draw_color"}}},
                {"op": "recolor_map", "args": {"map": {"learn": learn}}},
            ],
        })
    # Preserve any hand-authored defaults that are not already present.
    seen = {json.dumps(p, sort_keys=True) for p in programs}
    for program in DSL.DEFAULT_PROGRAMS:
        key = json.dumps(program, sort_keys=True)
        if key not in seen:
            programs.append(program)
            seen.add(key)
    return programs


def op_magic_ints(op_name: str) -> list[int]:
    fn = DSL.OPS.get(op_name)
    if fn is None:
        return []
    try:
        tree = ast.parse(inspect.getsource(fn))
    except Exception:
        return []
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            if node.value not in ALLOWED_STRUCTURAL_INTS:
                out.add(int(node.value))
    return sorted(out)


def program_generality(program: dict[str, Any]) -> dict[str, Any]:
    op_constants: dict[str, list[int]] = {}
    for step in program.get("pipeline", []):
        op = step.get("op")
        constants = op_magic_ints(op)
        if constants:
            op_constants[op] = constants
    blockers = []
    if op_constants:
        blockers.append("magic_int_constants")
    return {"magic_int_constants": op_constants, "blockers": blockers}


def _propose_for(program: dict[str, Any]):
    def propose(train):
        compiled = DSL.compile_program(program, train)
        return [compiled] if compiled is not None else []
    return propose


def _d4_variants(grid):
    def hflip(g):
        return [list(reversed(row)) for row in g]

    def vflip(g):
        return list(reversed([row[:] for row in g]))

    def rot90(g):
        return [list(row) for row in zip(*g[::-1])]

    def rot180(g):
        return rot90(rot90(g))

    def rot270(g):
        return rot90(rot180(g))

    return {
        "hflip": hflip(grid),
        "vflip": vflip(grid),
        "rot90": rot90(grid),
        "rot180": rot180(grid),
        "rot270": rot270(grid),
        "anti_diag": hflip(rot90(grid)),
    }


def synthetic_d4_exact(program: dict[str, Any], train: list[dict[str, Any]]) -> dict[str, bool]:
    labels = ["hflip", "vflip", "rot90", "rot180", "rot270", "anti_diag"]
    out = {}
    for label in labels:
        variant = []
        for pair in train:
            variant.append({
                "input": _d4_variants(pair["input"])[label],
                "output": _d4_variants(pair["output"])[label],
            })
        compiled = DSL.compile_program(program, variant)
        if compiled is None:
            out[label] = False
            continue
        _name, fn = compiled
        try:
            out[label] = all(fn(deepcopy(p["input"])) == p["output"] for p in variant)
        except Exception:
            out[label] = False
    return out


def score_task(task_id: str, task: dict[str, Any], evaluator: Any, programs: list[dict[str, Any]]) -> dict[str, Any]:
    train = task["train"]
    compiled = []
    for program in programs:
        candidate = DSL.compile_program(program, train)
        if candidate is not None:
            compiled.append((program, candidate[0], candidate[1]))
    diag = evaluator.candidate_train_diagnostics([(name, fn) for _p, name, fn in compiled], train)
    rows = []
    diag_by_name = {row["name"]: row for row in diag}
    for program, name, fn in compiled:
        row = dict(diag_by_name.get(name, {}))
        row["program_name"] = program.get("name")
        row["signature"] = name
        row["generality"] = program_generality(program)
        if row.get("shape_exact") and row.get("train_diff") == 0:
            ev = evaluator.loo_evidence(_propose_for(program), train, required_name=name, full_transform=fn)
            row["loo"] = {
                "passes": ev["passes"],
                "informative": ev["informative"],
                "admission_type": ev["admission_type"],
            }
            row["synthetic_d4_exact"] = synthetic_d4_exact(program, train)
        rows.append(row)
    rows.sort(key=lambda r: (
        r.get("train_diff") is None,
        r.get("train_diff", 10**9) if r.get("train_diff") is not None else 10**9,
        len(r.get("signature", "")),
    ))
    exact = [r for r in rows if r.get("shape_exact") and r.get("train_diff") == 0]
    return {
        "task_id": task_id,
        "n_compiled": len(compiled),
        "best": rows[0] if rows else None,
        "train_exact": exact[:10],
        "top": rows[:8],
    }


def main() -> None:
    evaluator = _load_base_evaluator()
    programs = program_space()
    results = []
    for path in sorted((HERE / "data" / "public").glob("*.json")):
        if path.name == "task.md":
            continue
        task = json.loads(path.read_text())
        results.append(score_task(path.stem, task, evaluator, programs))
    cross: dict[str, list[str]] = {}
    for row in results:
        for exact in row["train_exact"]:
            cross.setdefault(exact["signature"], []).append(row["task_id"])
    for row in results:
        for exact in row["train_exact"]:
            cross_count = len(cross.get(exact["signature"], []))
            blockers = list((exact.get("generality") or {}).get("blockers", []))
            if not (exact.get("loo") or {}).get("informative") and cross_count < 2:
                blockers.append("no_informative_loo_or_cross")
            exact["cross_task_count"] = cross_count
            exact["admission_ready"] = not blockers
            exact["promotion_blockers"] = blockers
    out = {
        "artifact": "dsl_enumeration_latest",
        "programs_enumerated": len(programs),
        "tasks": len(results),
        "train_exact_tasks": [r["task_id"] for r in results if r["train_exact"]],
        "informative_loo_tasks": [
            r["task_id"]
            for r in results
            if any((e.get("loo") or {}).get("informative") for e in r["train_exact"])
        ],
        "cross_task_firing": {k: v for k, v in cross.items() if len(v) >= 2},
        "results": results,
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT}")
    print(f"programs={out['programs_enumerated']} train_exact={out['train_exact_tasks']} "
          f"informative_loo={out['informative_loo_tasks']} cross={out['cross_task_firing']}")
    for row in results:
        if row["train_exact"]:
            print(row["task_id"], [e["signature"] for e in row["train_exact"]])


if __name__ == "__main__":
    main()
