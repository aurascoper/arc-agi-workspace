"""Codex sentinel for the quarantined SIA ARC shape task.

This script does not run SIA. It watches/evaluates the artifacts SIA is expected
to produce inside `sia_arc_shape_task/`:

- `reference_agent.py`
- optional `target_agent.py`
- optional `runs/run_*/gen_*/target_agent.py`

Each agent is scored with `sia_arc_shape_task/evaluator.py`, whose fitness is
hidden-safe: train exactness, same-name informative LOO, cross-task firing, and
leakage penalties. Private design-test readout is recorded but not part of
fitness. Nothing here edits the live Kaggle solver.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parent
TASK_DIR = WORKSPACE / "sia_arc_shape_task"
EVALUATOR = TASK_DIR / "evaluator.py"
OUT_JSON = WORKSPACE / "tmp" / "codex_sia_shape_sentinel.json"
RUN_DIRS = (TASK_DIR / "runs", WORKSPACE / "runs")


def agent_paths() -> list[Path]:
    paths: list[Path] = []
    for rel in ("reference_agent.py", "strong_seed_agent.py", "target_agent.py"):
        path = TASK_DIR / rel
        if path.exists():
            paths.append(path)
    for run_dir in RUN_DIRS:
        for path in sorted(run_dir.glob("run_*/gen_*/target_agent.py")):
            paths.append(path)
    seen: set[Path] = set()
    out: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            out.append(path)
    return out


def run_eval(agent: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(EVALUATOR), "--agent", str(agent), "--json"],
        cwd=WORKSPACE,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
    )
    report: dict[str, Any] = {
        "agent": str(agent.relative_to(WORKSPACE)),
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
        "stderr_tail": proc.stderr[-2000:],
    }
    if proc.returncode != 0:
        report["stdout_tail"] = proc.stdout[-2000:]
        return report
    try:
        data = json.loads(proc.stdout)
    except Exception as exc:  # pragma: no cover - diagnostic path
        report["ok"] = False
        report["parse_error"] = repr(exc)
        report["stdout_tail"] = proc.stdout[-2000:]
        return report
    tasks = data.get("tasks", [])
    report.update({
        "fitness": data.get("fitness"),
        "leakage_hits": data.get("leakage_hits", []),
        "n_leakage_hits": len(data.get("leakage_hits", [])),
        "train_exact_total": sum(t.get("n_train_exact", 0) for t in tasks if isinstance(t, dict)),
        "shape_exact_total": sum(t.get("n_shape_exact", 0) for t in tasks if isinstance(t, dict)),
        "shape_residuals": {
            t.get("task_id"): t.get("best_shape_train_diff")
            for t in tasks
            if isinstance(t, dict) and t.get("best_shape_train_diff")
        },
        "loo_task_total": sum(1 for t in tasks if isinstance(t, dict) and t.get("informative_loo")),
        "vacuous_loo_total": sum(
            len(t.get("vacuous_loo_names", []))
            for t in tasks
            if isinstance(t, dict)
        ),
        "loo_names": {
            t.get("task_id"): t.get("informative_loo_names", [])
            for t in tasks
            if isinstance(t, dict) and t.get("informative_loo_names")
        },
        "cross_task_firing": data.get("cross_task_firing", {}),
        "private_true_total": sum(
            1 for v in data.get("private_readout", {}).values()
            if v is True
        ),
        "private_readout": data.get("private_readout", {}),
    })
    return report


def integration_ready(report: dict[str, Any]) -> bool:
    if not report.get("ok") or report.get("n_leakage_hits"):
        return False
    if report.get("loo_task_total", 0) > 0:
        return True
    return bool(report.get("cross_task_firing"))


def main() -> None:
    if not EVALUATOR.exists():
        raise SystemExit(f"missing evaluator: {EVALUATOR}")
    OUT_JSON.parent.mkdir(exist_ok=True)
    reports = [run_eval(path) for path in agent_paths()]
    for report in reports:
        report["integration_ready"] = integration_ready(report)
    ready = [r for r in reports if r.get("integration_ready")]
    out = {
        "lane": "sia_shape_sentinel",
        "agents": reports,
        "integration_ready": [r["agent"] for r in ready],
        "integration_ready_bool": bool(ready),
    }
    OUT_JSON.write_text(json.dumps(out, indent=2))
    print("Codex SIA shape sentinel")
    for report in reports:
        print(
            f"  {report['agent']}: ok={report.get('ok')} fitness={report.get('fitness')} "
            f"leaks={report.get('n_leakage_hits')} train_exact={report.get('train_exact_total')} "
            f"shape_exact={report.get('shape_exact_total')} loo_tasks={report.get('loo_task_total')} "
            f"vacuous_loo={report.get('vacuous_loo_total')} cross={len(report.get('cross_task_firing', {}))} "
            f"private_true={report.get('private_true_total')} ready={report.get('integration_ready')}"
        )
        if report.get("shape_residuals"):
            print(f"    shape_residuals={report['shape_residuals']}")
    print(f"integration_ready={[r['agent'] for r in ready]}")
    print(f"wrote {OUT_JSON.relative_to(WORKSPACE)}")


if __name__ == "__main__":
    main()
