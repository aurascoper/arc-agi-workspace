"""Precise provenance of pseudo-private solves.

The winning-attempt source recorded in run_pseudo_private_eval diagnostics is a
COMPOSITE pipeline path, e.g.:

    tta_color:bg_first:dsl:complete_sparse_periodic_marker_lines   -> TTA over a DSL base
    tta_color:bg_first:motif_ring:mirror_3x3_blocks_outward        -> TTA over an OPERATOR
    tta_d4:anti_transpose:dsl:reflect_through_marker               -> TTA(d4) over DSL
    dsl:isolate_unique_color_object                                -> bare DSL
    region_wire:adjacent_majority_recolor                          -> bare OPERATOR
    alignment:connect_same_color / holes:fill_surround_majority    -> bare GENERIC candidate
    mirror_h / rot90                                               -> bare SYMMETRY

This splits the "general pipeline" share into TTA / DSL / generic / symmetry, and
separates it from the promoted operator-library share (base name in operator_ledger),
which is further broken into loo-informative (learned) vs fixed.

Usage:
    python3 analyze_solve_provenance.py label=tmp/pp_cal_strict_fixed.json label2=tmp/pp_design_strict_fixed.json
    python3 analyze_solve_provenance.py tmp/pp_cal_strict_fixed.json     # label defaults to filename
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

D4_TOKENS = {
    "identity", "rot90", "rot180", "rot270", "mirror_h", "mirror_v",
    "transpose", "anti_transpose", "flip_h", "flip_v",
}
SYMMETRY_BASES = {"mirror_h", "mirror_v", "rot90", "rot180", "rot270", "transpose", "anti_transpose"}


def strip_tta(source: str) -> tuple[str | None, str]:
    """Return (tta_wrapper_or_None, base_source) by peeling the TTA prefix."""
    base = source
    tta = None
    if base.startswith("tta_color:"):
        tta = "tta_color"
        base = base[len("tta_color:"):]
        if base.startswith("bg_first:"):
            base = base[len("bg_first:"):]
    elif base.startswith("tta_d4:"):
        tta = "tta_d4"
        rest = base[len("tta_d4:"):]
        # next token is the d4 variant (e.g. anti_transpose) then ':'
        head, _, tail = rest.partition(":")
        base = tail if tail else rest
    return tta, base


def base_type(base: str, op_names: set[str]) -> tuple[str, str]:
    """(coarse_type, detail). coarse_type in {dsl, operator, generic, symmetry}."""
    if base in op_names:
        return "operator", base
    if base.startswith("dsl:"):
        return "dsl", base.split(":", 1)[1].split(":")[0]
    head = base.split(":", 1)[0]
    if base in SYMMETRY_BASES or head in SYMMETRY_BASES:
        return "symmetry", head
    # An operator name can sometimes be wrapped further; final fallback by family head.
    return "generic", head


def winning_source(pair_row: dict, sources_by_pair: dict[int, dict]) -> str | None:
    idx = pair_row.get("pair_index")
    entry = sources_by_pair.get(idx, {})
    if pair_row.get("attempt_1_exact"):
        return entry.get("attempt_1")
    if pair_row.get("attempt_2_exact"):
        return entry.get("attempt_2")
    return None


def analyze(path: Path) -> dict:
    data = json.loads(path.read_text())
    rows = data.get("tasks", [])
    coarse = Counter()
    tta_wrap = Counter()
    crosstab = Counter()
    operator_kind = Counter()
    solved_pairs = 0
    solved_tasks = 0
    unattributed = 0
    for r in rows:
        if r.get("task_exact"):
            solved_tasks += 1
        rep = r.get("candidate_report", {})
        cs = rep.get("candidate_solver", {})
        sources_by_pair = {e.get("pair_index"): e for e in cs.get("test_attempt_sources", [])}
        op_ledger = {o.get("name"): o for o in rep.get("operator_ledger", []) if isinstance(o, dict) and "name" in o}
        op_names = set(op_ledger)
        for pr in r.get("pairs", []):
            if not pr.get("exact"):
                continue
            solved_pairs += 1
            src = winning_source(pr, sources_by_pair)
            if not src:
                unattributed += 1
                coarse["unattributed"] += 1
                continue
            tta, base = strip_tta(src)
            ctype, _detail = base_type(base, op_names)
            coarse[ctype] += 1
            tta_wrap["tta" if tta else "bare"] += 1
            crosstab[(("tta" if tta else "bare"), ctype)] += 1
            if ctype == "operator":
                op = op_ledger.get(base, {})
                if op.get("loo_informative"):
                    operator_kind["learned_loo_informative"] += 1
                else:
                    operator_kind[f"fixed_{op.get('generalization_tier', 'unknown')}"] += 1
    return {
        "solved_tasks": solved_tasks,
        "solved_pairs": solved_pairs,
        "unattributed": unattributed,
        "coarse": coarse,
        "tta_wrap": tta_wrap,
        "crosstab": crosstab,
        "operator_kind": operator_kind,
    }


def pct(n: int, d: int) -> str:
    return f"{100*n/d:5.1f}%" if d else "  n/a"


def report(label: str, a: dict) -> None:
    sp = a["solved_pairs"]
    print(f"\n=== {label} — {a['solved_tasks']} tasks, {sp} solved pairs "
          f"({a['unattributed']} unattributed) ===")
    gen = a["coarse"]["dsl"] + a["coarse"]["generic"] + a["coarse"]["symmetry"]
    op = a["coarse"]["operator"]
    print(f"  GENERAL pipeline : {gen:3}/{sp}  ({pct(gen, sp)})   "
          f"[dsl {a['coarse']['dsl']} | generic {a['coarse']['generic']} | symmetry {a['coarse']['symmetry']}]")
    print(f"  OPERATOR library : {op:3}/{sp}  ({pct(op, sp)})   "
          f"[{dict(a['operator_kind'])}]")
    print(f"  TTA-wrapped      : {a['tta_wrap']['tta']:3}/{sp}  ({pct(a['tta_wrap']['tta'], sp)})  "
          f"(bare {a['tta_wrap']['bare']})")
    print(f"  crosstab (wrapper x base):")
    for (w, c), n in sorted(a["crosstab"].items(), key=lambda kv: -kv[1]):
        print(f"     {w:4} x {c:9} : {n}")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    combined = None
    for arg in args:
        if "=" in arg:
            label, path = arg.split("=", 1)
        else:
            path = arg
            label = Path(arg).stem
        a = analyze(Path(path))
        report(label, a)


if __name__ == "__main__":
    main()
