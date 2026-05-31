"""Near-miss frontier for the 23 genuine design misses (Claude lane, design-only, hidden-safe).

For each genuine current miss, find the live factory's CLOSEST same-shape candidate (min total train
residual) and report its name/family + normalized residual. Ranks tasks by how close an existing
structured operator already gets — the actionable "one parameter away" frontier for the Codex solver lane.
No task ids / templates / test-output use in selection; design test output is not consulted at all here.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKSPACE))
import run_pseudo_private_eval as RP  # noqa: E402
import arc2_candidate_solver as S  # noqa: E402

EVAL = WORKSPACE / "arc_agi_2_data" / "evaluation"


def norm(g):
    return S.normalize_grid(g)


def shape(g):
    g = norm(g)
    return (len(g), len(g[0]))


def total_train_residual(transform, train):
    tot = 0
    cells = 0
    for p in train:
        try:
            a, b = norm(transform(deepcopy(p["input"]))), norm(p["output"])
        except Exception:
            return None, None
        if shape(a) != shape(b):
            return None, None
        tot += sum(a[r][c] != b[r][c] for r in range(len(a)) for c in range(len(a[0])))
        cells += len(b) * len(b[0])
    return tot, cells


def main():
    RP.configure_hidden_environment()
    ns, _ = RP.build_namespace(scrub_task_solvers=True)
    genuine = json.loads((WORKSPACE / "tmp" / "claude_current_coverage_audit.json").read_text())["genuine_coverage_miss"]
    rows = []
    for tid in genuine:
        task = json.loads((EVAL / f"{tid}.json").read_text())
        tr, te = task["train"], task["test"]
        td = {"train": tr, "test": [{"input": te[0]["input"]}]}
        cands = S.generate_candidates(td, ns=ns, task_id=f"probe_{tid}")
        best = None
        for c in cands:
            tot, cells = total_train_residual(c.transform, tr)
            if tot is None:
                continue
            rho = tot / max(1, cells)
            if best is None or tot < best[0]:
                best = (tot, rho, c.name, c.family)
        if best is None:
            rows.append({"task_id": tid, "closest_residual": None, "rho": None, "candidate": None, "family": None})
        else:
            rows.append({"task_id": tid, "closest_residual": best[0], "rho": round(best[1], 4),
                         "candidate": best[2], "family": best[3]})
    rows.sort(key=lambda r: (r["rho"] is None, r["rho"] if r["rho"] is not None else 9))
    out = {"n": len(rows), "frontier": rows}
    (WORKSPACE / "tmp" / "claude_nearmiss_frontier.json").write_text(json.dumps(out, indent=2))
    print(f"{'task':10} {'rho':>7} {'resid':>6}  closest candidate (family)")
    for r in rows:
        if r["rho"] is None:
            print(f"{r['task_id']:10} {'  n/a':>7} {'-':>6}  no same-shape candidate")
        else:
            print(f"{r['task_id']:10} {r['rho']:>7.3f} {r['closest_residual']:>6}  {r['candidate'][:46]} ({r['family']})")
    close = [r for r in rows if r["rho"] is not None and r["rho"] <= 0.05]
    print(f"\n<=5% normalized residual (tightest frontier, {len(close)}): {[r['task_id'] for r in close]}")
    print("wrote tmp/claude_nearmiss_frontier.json")


if __name__ == "__main__":
    main()
