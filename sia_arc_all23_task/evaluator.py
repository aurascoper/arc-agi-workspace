"""Quarantined SIA evaluator wrapper for the all-23 design-miss task.

This reuses the hardened `sia_arc_shape_task/evaluator.py` gate, but points it at
this directory's public/private split and expands the task-ID leakage pattern to
all 23 current genuine design misses. Private outputs remain log-only; they do
not enter fitness.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_EVAL = HERE.parent / "sia_arc_shape_task" / "evaluator.py"
TARGETS = [
    "5dbc8537", "edb79dae", "dd6b8c4b", "88bcf3b4", "cb2d8a2c", "142ca369",
    "3dc255db", "195c6913", "36a08778", "4a21e3da", "16b78196", "446ef5d2",
    "7b0280bc", "abc82100", "d8e07eb2", "271d71e2", "faa9f03d", "35ab12c3",
    "20a9e565", "2d0172a1", "6ffbe589", "e87109e9", "89565ca0",
]


def _load_base():
    spec = importlib.util.spec_from_file_location("sia_shape_base_evaluator", BASE_EVAL)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    mod.HERE = HERE
    mod.PUBLIC = HERE / "data" / "public"
    mod.PRIVATE = HERE / "data" / "private"
    task_re = r"\b(" + "|".join(re.escape(t) for t in TARGETS) + r")\b"
    mod.FORBIDDEN = [
        item for item in mod.FORBIDDEN
        if item[1] != "hardcoded target task id"
    ] + [(task_re, "hardcoded target task id")]
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="../sia_arc_shape_task/strong_seed_agent.py")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    base = _load_base()
    agent = Path(args.agent)
    if not agent.is_absolute():
        agent = HERE / agent
    rep = base.evaluate(agent)
    rep["task"] = "all23"
    rep["n_targets"] = len(TARGETS)
    if args.json:
        print(json.dumps(rep, indent=2))
        return
    print(f"FITNESS: {rep['fitness']}   (leakage hits: {len(rep['leakage_hits'])})")
    for t in rep["tasks"]:
        print(f"  {t['task_id']}: train_exact={t.get('n_train_exact', 0)} "
              f"loo={t.get('informative_loo')} vacuous={t.get('vacuous_loo_names', [])} "
              f"shape_exact={t.get('n_shape_exact', 0)} names={t.get('train_exact_names', [])}")
    print(f"cross-task firing >=2: {rep.get('cross_task_firing', {})}")
    print(f"PRIVATE readout (LOG ONLY, not in fitness): {rep['private_readout']}")
    if rep["leakage_hits"]:
        print("LEAKAGE HITS:", rep["leakage_hits"])


if __name__ == "__main__":
    main()
