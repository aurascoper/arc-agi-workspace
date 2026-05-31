"""Write a stable, committed SIA-lite run summary for agent coordination."""

from __future__ import annotations

import json
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parent.parent
RUNS = WORKSPACE / "runs"
OUT = WORKSPACE / "tmp" / "sia_lite_latest.json"


def _task_count(report: dict, key: str) -> int:
    return sum(int(t.get(key, 0) or 0) for t in report.get("tasks", []) if isinstance(t, dict))


def _loo_tasks(report: dict) -> int:
    return sum(1 for t in report.get("tasks", []) if isinstance(t, dict) and t.get("informative_loo"))


def _target_row(report: dict) -> dict | None:
    pre = report.get("pre_score_gate") or {}
    seed = pre.get("seed") or {}
    summary = seed.get("summary") or {}
    target = summary.get("target_task")
    if not target:
        return None
    for row in report.get("tasks", []) or []:
        if isinstance(row, dict) and row.get("task_id") == target:
            return row
    return None


def _summarize_result(path: Path) -> dict:
    meta_path = path.parent / "generation_meta.json"
    report_path = meta_path if meta_path.exists() else path
    report = json.loads(report_path.read_text())
    row = _target_row(report) or {}
    best = row.get("best_shape_train_diff") or {}
    return {
        "generation": path.parent.name,
        "status": report.get("status"),
        "fitness": report.get("fitness"),
        "leaks": len(report.get("leakage_hits", []) or []),
        "loo_tasks": _loo_tasks(report),
        "cross": report.get("cross_task_firing", {}) or {},
        "train_exact": _task_count(report, "n_train_exact"),
        "shape_exact": _task_count(report, "n_shape_exact"),
        "target_train_exact": row.get("n_train_exact"),
        "target_informative_loo": row.get("informative_loo"),
        "target_shape_exact": row.get("n_shape_exact"),
        "target_best_diff": best.get("diff"),
        "target_best_name": best.get("name"),
    }


def main() -> None:
    runs = []
    if RUNS.exists():
        for run_dir in sorted(RUNS.iterdir()):
            if not run_dir.is_dir():
                continue
            gens = []
            last_result_mtime = 0.0
            for result in sorted(run_dir.glob("gen_*/results.json")):
                last_result_mtime = max(last_result_mtime, result.stat().st_mtime)
                gens.append(_summarize_result(result))
            state_path = run_dir / "state.json"
            state = json.loads(state_path.read_text()) if state_path.exists() else {}
            if state_path.exists():
                last_result_mtime = max(last_result_mtime, state_path.stat().st_mtime)
            runs.append({
                "run_id": run_dir.name,
                "tripwire": bool(state.get("tripwire")),
                "last_generation": state.get("last_generation"),
                "target_task": state.get("target_task"),
                "updated_at": state.get("updated_at"),
                "last_result_mtime": last_result_mtime,
                "generations": gens,
            })
    runs.sort(key=lambda row: (row.get("last_result_mtime") or 0.0, row.get("run_id") or ""))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"runs": runs[-20:]}, indent=2) + "\n")


if __name__ == "__main__":
    main()
