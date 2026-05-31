"""Write a coordination-only SIA-lite search policy artifact.

The SIA-lite lane is useful when there is a bounded, non-duplicative target to
probe. Once every finite residual target has completed a clean reloaded run
without train exactness, informative LOO, or cross-task firing, an idle worker is
not itself a failure. This script makes that distinction explicit for Codex and
Claude polling.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


WORKSPACE = Path(__file__).resolve().parent.parent
OUT = WORKSPACE / "tmp" / "sia_search_policy_latest.json"
MIN_COMPLETED_GEN = 8


def load_json(rel: str) -> dict:
    path = WORKSPACE / rel
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        return {"_error": repr(exc)}


def generation_signal(gen: dict) -> dict:
    cross = gen.get("cross") or {}
    return {
        "generation": gen.get("generation"),
        "fitness": gen.get("fitness"),
        "leaks": gen.get("leaks", 0),
        "loo_tasks": gen.get("loo_tasks", 0),
        "cross": cross,
        "target_train_exact": gen.get("target_train_exact") or 0,
        "target_informative_loo": bool(gen.get("target_informative_loo")),
        "target_best_diff": gen.get("target_best_diff"),
        "target_best_name": gen.get("target_best_name"),
        "admissible": bool(
            (gen.get("leaks", 0) == 0)
            and (
                (gen.get("target_train_exact") or 0) > 0
                or bool(gen.get("target_informative_loo"))
                or bool(cross)
                or (gen.get("loo_tasks") or 0) > 0
            )
        ),
    }


def summarize_run(run: dict) -> dict:
    gens = [generation_signal(g) for g in run.get("generations", []) or []]
    best = None
    finite = [g for g in gens if g.get("target_best_diff") is not None]
    if finite:
        best = min(finite, key=lambda g: (g["target_best_diff"], str(g.get("generation") or "")))
    leaks = sum(int(g.get("leaks") or 0) for g in gens)
    max_train_exact = max([int(g.get("target_train_exact") or 0) for g in gens] or [0])
    has_loo = any(g.get("target_informative_loo") or (g.get("loo_tasks") or 0) > 0 for g in gens)
    has_cross = any(bool(g.get("cross")) for g in gens)
    complete = int(run.get("last_generation") or 0) >= MIN_COMPLETED_GEN
    return {
        "run_id": run.get("run_id"),
        "target_task": run.get("target_task"),
        "last_generation": run.get("last_generation"),
        "tripwire": bool(run.get("tripwire")),
        "updated_at": run.get("updated_at"),
        "complete": complete,
        "leaks": leaks,
        "max_target_train_exact": max_train_exact,
        "has_informative_loo": has_loo,
        "has_cross_task_firing": has_cross,
        "best_target_residual": {
            "diff": best.get("target_best_diff"),
            "generation": best.get("generation"),
            "name": best.get("target_best_name"),
        } if best else None,
        "admissible_signal": bool(leaks == 0 and (max_train_exact > 0 or has_loo or has_cross)),
        "flat_non_promotable": bool(
            complete
            and not run.get("tripwire")
            and leaks == 0
            and max_train_exact == 0
            and not has_loo
            and not has_cross
        ),
    }


def main() -> None:
    now = datetime.now(ZoneInfo("America/Chicago"))
    latest = load_json("tmp/sia_lite_latest.json")
    residuals = load_json("tmp/sia_lite_residual_mining.json")
    sentinel = load_json("tmp/codex_sia_all23_sentinel.json")
    dsl = load_json("tmp/dsl_enumeration_latest.json")

    runs = latest.get("runs", []) or []
    reloaded = [summarize_run(r) for r in runs if str(r.get("run_id") or "").startswith("sia_lite_reloaded_")]
    by_target: dict[str, dict] = {}
    for row in reloaded:
        target = row.get("target_task")
        if not target:
            continue
        cur = by_target.get(target)
        if cur is None or str(row.get("updated_at") or "") > str(cur.get("updated_at") or ""):
            by_target[target] = row

    best_targets = sorted((residuals.get("best_by_target") or {}).keys())
    exhausted = sorted(t for t, row in by_target.items() if row.get("flat_non_promotable"))
    admissible = sorted(t for t, row in by_target.items() if row.get("admissible_signal"))
    incomplete = sorted(t for t, row in by_target.items() if not row.get("complete"))
    unprobed = sorted(t for t in best_targets if t not in by_target)

    integration_ready = sentinel.get("integration_ready", []) or []
    manual_review = sentinel.get("manual_review_candidates", []) or []
    parked = sentinel.get("parked_candidates", dsl.get("parked_candidates", [])) or []

    if integration_ready or manual_review or admissible:
        recommendation = "verify_candidates"
        worker_expected = False
        next_action = "Do not launch new SIA-lite work; manually verify candidate evidence first."
    elif incomplete:
        recommendation = "poll_active_or_incomplete"
        worker_expected = True
        next_action = f"Continue/poll incomplete SIA-lite targets: {incomplete}."
    elif unprobed:
        recommendation = "launch_unprobed_residual_target"
        worker_expected = True
        next_action = f"Launch a bounded SIA-lite probe only if target is not already closed: {unprobed[0]}."
    else:
        recommendation = "idle_exhausted_sia_queue"
        worker_expected = False
        next_action = (
            "Do not restart flat SIA-lite residual runs. Move upstream to typed DSL/enumerator/"
            "library-learning or Claude method-track family two."
        )

    out = {
        "artifact": "sia_search_policy_latest",
        "generated_cdt": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "promotion_gate": "train-exact plus informative LOO or cross-task firing; leakage clean; manual verification",
        "recommendation": recommendation,
        "sia_worker_expected": worker_expected,
        "next_action": next_action,
        "integration_ready_count": len(integration_ready),
        "manual_review_count": len(manual_review),
        "parked_count": len(parked),
        "reloaded_targets": dict(sorted(by_target.items())),
        "exhausted_flat_targets": exhausted,
        "admissible_signal_targets": admissible,
        "incomplete_targets": incomplete,
        "unprobed_residual_targets": unprobed,
        "positive_residual_reductions": residuals.get("positive_reductions", []) or [],
        "notes": [
            "Flat means completed, no tripwire/leaks, no target train exactness, no informative LOO, and no cross-task firing.",
            "Finite residual reductions are diagnostic only and never promotion evidence by themselves.",
        ],
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(WORKSPACE)} recommendation={recommendation} worker_expected={worker_expected}")


if __name__ == "__main__":
    main()
