"""Current-state coverage audit (Claude lane) — corrects the stale exact-only bottleneck snapshot.

For each DESIGN 'miss' from ARC2_COVERAGE_BOTTLENECKS_EXACTONLY.md, regenerate candidates with the
LIVE, hidden-faithful (scrubbed) factory and classify into:
  - solved_now            : a hidden-safe candidate is train-exact AND design-test-exact
  - train_exact_test_wrong: train-exact candidate exists but misses test (verifier-leak / overfit)
  - genuine_coverage_miss : no train-exact candidate at all

Test-exactness is used ONLY to classify the current solver's coverage (a design diagnostic), never to
implement an operator. Output: tmp/claude_current_coverage_audit.json.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from copy import deepcopy
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKSPACE))
import run_pseudo_private_eval as RP  # noqa: E402
import arc2_candidate_solver as S  # noqa: E402

EVAL = WORKSPACE / "arc_agi_2_data" / "evaluation"

# DESIGN-split misses from the exact-only bottleneck snapshot (calibration tasks excluded).
DESIGN_MISSES = [
    "5dbc8537", "edb79dae", "dd6b8c4b", "88bcf3b4", "cb2d8a2c", "142ca369", "3dc255db",
    "195c6913", "36a08778", "981571dc", "2b83f449", "4a21e3da", "16b78196", "446ef5d2",
    "7b0280bc", "abc82100", "d8e07eb2", "db695cfb", "64efde09", "271d71e2", "8f3a5a89",
    "faa9f03d", "35ab12c3", "898e7135", "da515329", "20a9e565", "2d0172a1", "6ffbe589",
    "e87109e9", "89565ca0",
]


def norm(g):
    return S.normalize_grid(g)


def audit_task(tid, ns):
    task = json.loads((EVAL / f"{tid}.json").read_text())
    tr, te = task["train"], task["test"]
    td = {"train": tr, "test": [{"input": te[0]["input"]}]}
    cands = S.generate_candidates(td, ns=ns, task_id=f"probe_{tid}")

    train_exact_names = []
    test_exact_names = []
    for c in cands:
        try:
            ok = all(norm(c.transform(deepcopy(p["input"]))) == norm(p["output"]) for p in tr)
        except Exception:
            ok = False
        if not ok:
            continue
        train_exact_names.append(c.name)
        try:
            tex = all(p.get("output") is not None and norm(c.transform(deepcopy(p["input"]))) == norm(p["output"]) for p in te)
        except Exception:
            tex = False
        if tex:
            test_exact_names.append(c.name)

    if test_exact_names:
        status = "solved_now"
    elif train_exact_names:
        status = "train_exact_test_wrong"
    else:
        status = "genuine_coverage_miss"
    return {
        "task_id": tid,
        "n_candidates": len(cands),
        "n_train_exact": len(train_exact_names),
        "n_test_exact": len(test_exact_names),
        "status": status,
        "solver_names": test_exact_names[:3] or train_exact_names[:3],
    }


def main():
    RP.configure_hidden_environment()
    ns, removed = RP.build_namespace(scrub_task_solvers=True)
    print(f"hidden-faithful ns: {len(removed)} task solvers scrubbed\n")
    rows = []
    t0 = time.time()
    for tid in DESIGN_MISSES:
        r = audit_task(tid, ns)
        rows.append(r)
        print(f"  {tid}: {r['status']:24} train_exact={r['n_train_exact']} test_exact={r['n_test_exact']}"
              + (f"  via {r['solver_names'][0]}" if r["solver_names"] else ""))
    counts = Counter(r["status"] for r in rows)
    out = {
        "summary": dict(counts),
        "n_design_misses_in_snapshot": len(rows),
        "now_solved": [r["task_id"] for r in rows if r["status"] == "solved_now"],
        "verifier_leak": [r["task_id"] for r in rows if r["status"] == "train_exact_test_wrong"],
        "genuine_coverage_miss": [r["task_id"] for r in rows if r["status"] == "genuine_coverage_miss"],
        "rows": rows,
        "wall_time_sec": round(time.time() - t0, 1),
    }
    (WORKSPACE / "tmp").mkdir(exist_ok=True)
    (WORKSPACE / "tmp" / "claude_current_coverage_audit.json").write_text(json.dumps(out, indent=2))
    print(f"\nSTATUS COUNTS: {dict(counts)}")
    print(f"now_solved ({len(out['now_solved'])}): {out['now_solved']}")
    print(f"verifier_leak ({len(out['verifier_leak'])}): {out['verifier_leak']}")
    print(f"genuine_coverage_miss ({len(out['genuine_coverage_miss'])}): {out['genuine_coverage_miss']}")
    print(f"wrote tmp/claude_current_coverage_audit.json ({out['wall_time_sec']}s)")


if __name__ == "__main__":
    main()
