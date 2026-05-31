"""Mine target-conditioned SIA-lite generations for train-residual reductions."""

from __future__ import annotations

import json
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parent.parent
RUNS = WORKSPACE / "runs"
OUT = WORKSPACE / "tmp" / "sia_lite_residual_mining.json"


def _load(path: Path) -> dict:
    meta = path.parent / "generation_meta.json"
    return json.loads((meta if meta.exists() else path).read_text())


def _target_from_meta(report: dict, fallback: str | None = None) -> str | None:
    pre = report.get("pre_score_gate") or {}
    seed = pre.get("seed") or {}
    summary = seed.get("summary") or {}
    return summary.get("target_task") or fallback


def _target_row(report: dict, target: str | None) -> dict | None:
    if not target:
        return None
    for row in report.get("tasks", []) or []:
        if isinstance(row, dict) and row.get("task_id") == target:
            return row
    return None


def _row(run_id: str, result: Path, fallback_target: str | None = None) -> dict | None:
    report = _load(result)
    target = _target_from_meta(report, fallback_target)
    row = _target_row(report, target)
    if not row:
        return None
    best = row.get("best_shape_train_diff") or {}
    diff = best.get("diff")
    if diff is None:
        return None
    return {
        "run_id": run_id,
        "generation": result.parent.name,
        "target_task": target,
        "fitness": report.get("fitness"),
        "leaks": len(report.get("leakage_hits", []) or []),
        "cross": report.get("cross_task_firing", {}) or {},
        "target_train_exact": row.get("n_train_exact", 0),
        "target_informative_loo": bool(row.get("informative_loo")),
        "target_shape_exact": row.get("n_shape_exact", 0),
        "target_best_diff": diff,
        "target_best_name": best.get("name"),
        "per_pair_diff": best.get("per_pair_diff"),
    }


def main() -> None:
    rows = []
    baselines: dict[tuple[str, str], int] = {}
    if RUNS.exists():
        for run_dir in sorted(p for p in RUNS.iterdir() if p.is_dir()):
            state_path = run_dir / "state.json"
            state = json.loads(state_path.read_text()) if state_path.exists() else {}
            state_target = None
            state_seed_diff = None
            for item in state.get("population", []) or []:
                summary = item.get("summary") or {}
                if summary.get("target_task"):
                    state_target = summary.get("target_task")
                    if str(item.get("path", "")).endswith("/seed/target_agent.py"):
                        state_seed_diff = summary.get("target_best_shape_diff")
                    break
            seed_result = run_dir / "seed" / "results.json"
            if seed_result.exists() and state_target:
                seed = _row(run_dir.name, seed_result, state_target)
                if seed:
                    baselines[(run_dir.name, seed["target_task"])] = seed["target_best_diff"]
            if state_target and state_seed_diff is not None:
                baselines[(run_dir.name, state_target)] = int(state_seed_diff)
            for result in sorted(run_dir.glob("gen_*/results.json")):
                mined = _row(run_dir.name, result, state_target)
                if mined:
                    base = baselines.get((run_dir.name, mined["target_task"]))
                    mined["run_seed_diff"] = base
                    mined["run_delta"] = (base - mined["target_best_diff"]) if base is not None else None
                    rows.append(mined)
    best_by_target: dict[str, dict] = {}
    for row in rows:
        cur = best_by_target.get(row["target_task"])
        if cur is None or row["target_best_diff"] < cur["target_best_diff"]:
            best_by_target[row["target_task"]] = row
    positive = [r for r in rows if isinstance(r.get("run_delta"), int) and r["run_delta"] > 0]
    positive.sort(key=lambda r: (-r["run_delta"], r["target_best_diff"], r["run_id"], r["generation"]))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "positive_reductions": positive,
        "best_by_target": dict(sorted(best_by_target.items())),
        "n_rows": len(rows),
    }, indent=2) + "\n")
    print(f"wrote {OUT}")
    for row in positive[:20]:
        print(
            f"{row['target_task']} {row['run_id']}/{row['generation']} "
            f"delta={row['run_delta']} diff={row['target_best_diff']} name={row['target_best_name']}"
        )


if __name__ == "__main__":
    main()
