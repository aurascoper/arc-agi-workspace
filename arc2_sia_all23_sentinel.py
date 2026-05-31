"""Codex sentinel for the quarantined all-23 SIA task."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

WORKSPACE = Path(__file__).resolve().parent
TASK_DIR = WORKSPACE / "sia_arc_all23_task"
EVALUATOR = TASK_DIR / "evaluator.py"
OUT_JSON = WORKSPACE / "tmp" / "codex_sia_all23_sentinel.json"
RUN_DIRS = (TASK_DIR / "runs", WORKSPACE / "runs")
DSL_FRONTIER_JSON = WORKSPACE / "tmp" / "dsl_enumeration_latest.json"
LEGEND_SYNTH_JSON = WORKSPACE / "tmp" / "legend_lattice_synthetic_latest.json"


def agent_paths() -> list[Path]:
    paths: list[Path] = []
    for rel in ("reference_agent.py", "../sia_arc_shape_task/strong_seed_agent.py", "target_agent.py"):
        path = (TASK_DIR / rel).resolve()
        if path.exists():
            paths.append(path)
    for run_dir in RUN_DIRS:
        for pattern in ("run_*/gen_*/target_agent.py", "*/gen_*/target_agent.py"):
            for path in sorted(run_dir.glob(pattern)):
                paths.append(path.resolve())
    seen: set[Path] = set()
    out: list[Path] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            out.append(path)
    return out


def run_eval(agent: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(EVALUATOR), "--agent", str(agent), "--json"],
        cwd=WORKSPACE,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=240,
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
    except Exception as exc:
        report["ok"] = False
        report["parse_error"] = repr(exc)
        report["stdout_tail"] = proc.stdout[-2000:]
        return report
    tasks = data.get("tasks", [])
    train_exact_name_tasks: dict[str, list[str]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        tid = task.get("task_id")
        for name in task.get("train_exact_names_all", task.get("train_exact_names", [])):
            train_exact_name_tasks.setdefault(name, []).append(tid)
    top_train_exact_names = {
        name: tids
        for name, tids in sorted(
            train_exact_name_tasks.items(),
            key=lambda kv: (-len(kv[1]), kv[0]),
        )[:20]
    }
    report.update({
        "fitness": data.get("fitness"),
        "n_leakage_hits": len(data.get("leakage_hits", [])),
        "leakage_hits": data.get("leakage_hits", []),
        "train_exact_total": sum(t.get("n_train_exact", 0) for t in tasks if isinstance(t, dict)),
        "shape_exact_total": sum(t.get("n_shape_exact", 0) for t in tasks if isinstance(t, dict)),
        "loo_task_total": sum(1 for t in tasks if isinstance(t, dict) and t.get("informative_loo")),
        "vacuous_loo": {
            t.get("task_id"): t.get("vacuous_loo_names", [])
            for t in tasks
            if isinstance(t, dict) and t.get("vacuous_loo_names")
        },
        "cross_task_firing": data.get("cross_task_firing", {}),
        "train_exact_name_tasks": train_exact_name_tasks,
        "top_train_exact_names": top_train_exact_names,
        "private_true_total": sum(1 for v in data.get("private_readout", {}).values() if v is True),
    })
    return report


def integration_ready(report: dict[str, Any]) -> bool:
    if not report.get("ok") or report.get("n_leakage_hits"):
        return False
    if report.get("loo_task_total", 0) > 0:
        return True
    return bool(report.get("cross_task_firing"))


def dsl_manual_review_candidates() -> list[dict[str, Any]]:
    if not DSL_FRONTIER_JSON.exists():
        return []
    try:
        data = json.loads(DSL_FRONTIER_JSON.read_text())
    except Exception:
        return []
    out = []
    for row in data.get("manual_review_candidates", []) or []:
        if not isinstance(row, dict):
            continue
        out.append({
            "task_id": row.get("task_id"),
            "signature": row.get("signature"),
            "promotion_blockers": row.get("promotion_blockers", []),
            "manual_review_reason": row.get("manual_review_reason"),
        })
    return out


def legend_synthetic_summary() -> dict[str, Any] | None:
    if not LEGEND_SYNTH_JSON.exists():
        return None
    try:
        data = json.loads(LEGEND_SYNTH_JSON.read_text())
    except Exception:
        return None
    return {
        "tasks": data.get("tasks"),
        "all_train_exact": data.get("all_train_exact"),
        "all_test_exact": data.get("all_test_exact"),
        "train_exact_tasks": data.get("train_exact_tasks", []),
        "test_exact_tasks": data.get("test_exact_tasks", []),
    }


def main() -> None:
    OUT_JSON.parent.mkdir(exist_ok=True)
    reports = [run_eval(path) for path in agent_paths()]
    for report in reports:
        report["integration_ready"] = integration_ready(report)
    ready = [r for r in reports if r.get("integration_ready")]
    manual_review = dsl_manual_review_candidates()
    legend_synth = legend_synthetic_summary()
    out = {
        "lane": "sia_all23_sentinel",
        "agents": reports,
        "integration_ready": [r["agent"] for r in ready],
        "integration_ready_bool": bool(ready),
        "manual_review_candidates": manual_review,
        "manual_review_bool": bool(manual_review),
        "legend_lattice_synthetic": legend_synth,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2))
    print("Codex SIA all-23 sentinel")
    for report in reports:
        print(
            f"  {report['agent']}: ok={report.get('ok')} fitness={report.get('fitness')} "
            f"leaks={report.get('n_leakage_hits')} train_exact={report.get('train_exact_total')} "
            f"shape_exact={report.get('shape_exact_total')} loo_tasks={report.get('loo_task_total')} "
            f"vacuous={report.get('vacuous_loo')} cross={len(report.get('cross_task_firing', {}))} "
            f"private_true={report.get('private_true_total')} ready={report.get('integration_ready')}"
        )
        if report.get("top_train_exact_names"):
            print(f"    train_exact_name_tasks={report['top_train_exact_names']}")
    print(f"integration_ready={[r['agent'] for r in ready]}")
    print(f"manual_review_candidates={[(r.get('task_id'), r.get('signature')) for r in manual_review]}")
    print(f"legend_lattice_synthetic={legend_synth}")
    print(f"wrote {OUT_JSON.relative_to(WORKSPACE)}")


if __name__ == "__main__":
    main()
