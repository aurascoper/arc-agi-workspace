"""Write a compact coordination-health artifact for unattended polling.

This script summarizes the verifier loop's observable state without requiring
another agent to scrape the mailbox. It is coordination-only and never touches
the live solver or Kaggle packaging paths.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


TASK_DIR = Path(__file__).resolve().parent
WORKSPACE = TASK_DIR.parent
OUT = WORKSPACE / "tmp" / "verifier_health_latest.json"
MIRROR_DIR = Path("/tmp/arc_agi_handoff_sync")
MIRROR_BRANCH = "research/deep-research-handoff-2026-05-30"
FRESHNESS_STALE_SECONDS = 900
HEARTBEAT_STALE_SECONDS = 390
SIA_LITE_RESULT_STALE_SECONDS = 1800
FRESHNESS_PATHS = [
    "tmp/dsl_enumeration_latest.json",
    "tmp/codex_sia_all23_sentinel.json",
    "tmp/sia_lite_latest.json",
    "tmp/sia_lite_residual_mining.json",
    "tmp/sia_search_policy_latest.json",
    "tmp/claude_artifact_watch_latest.json",
    "tmp/template_match_role_recolor_latest_review.json",
    "tmp/template_match_role_recolor_v1_review.json",
    "tmp/claude_sketch_enumeration.json",
    "tmp/legend_lattice_synthetic_latest.json",
    "tmp/verifier_refresh_latest.json",
]
PROCESS_COMMAND_PATTERNS = {
    "verifier_loop": ["codex_verifier_cycle.py"],
    "sia_lite_worker": ["sia_lite_harness.py"],
    "active_branch_push": ["git push origin HEAD:research/operator-promotion"],
    "github_arc_agi_transfer": [
        "git-receive-pack 'aurascoper/arc-agi-workspace.git'",
        "git-upload-pack 'aurascoper/arc-agi-workspace.git'",
        "arc-agi-workspace.git",
    ],
}
SAFE_STATUS_PATHS = [
    ".gitignore",
    "ARC2_AGENT_COORDINATION_STATUS.md",
    "arc2_sia_all23_sentinel.py",
    "sia_arc_all23_task",
    "tmp/dsl_enumeration_latest.json",
    "tmp/codex_sia_all23_sentinel.json",
    "tmp/sia_lite_latest.json",
    "tmp/sia_lite_residual_mining.json",
    "tmp/sia_search_policy_latest.json",
    "tmp/claude_artifact_watch_latest.json",
    "tmp/template_match_role_recolor_latest_review.json",
    "tmp/template_match_role_recolor_v1_review.json",
    "tmp/claude_sketch_enumeration.json",
    "tmp/legend_lattice_synthetic_latest.json",
    "tmp/verifier_refresh_latest.json",
]


def run(cmd: list[str], cwd: Path = WORKSPACE) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def load_json(path: str):
    p = WORKSPACE / path
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as exc:
        return {"_error": repr(exc)}


def git_lines(args: list[str]) -> list[str]:
    proc = run(["git", *args])
    return [line for line in proc.stdout.splitlines() if line.strip()]


def tmux_sessions() -> list[str]:
    proc = run(["tmux", "list-sessions"])
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if "arc2" in line or "sia" in line or "codex" in line]


def mirror_state() -> dict:
    if not MIRROR_DIR.exists():
        return {"dir": str(MIRROR_DIR), "available": False}
    branch = run(["git", "branch", "--show-current"], cwd=MIRROR_DIR).stdout.strip() or None
    head = run(["git", "rev-parse", "--short", "HEAD"], cwd=MIRROR_DIR).stdout.strip() or None
    origin = run(["git", "rev-parse", "--short", f"origin/{MIRROR_BRANCH}"], cwd=MIRROR_DIR).stdout.strip() or None
    status = [
        line for line in run(["git", "status", "--short", "--", *SAFE_STATUS_PATHS], cwd=MIRROR_DIR).stdout.splitlines()
        if line.strip()
    ]
    return {
        "dir": str(MIRROR_DIR),
        "available": True,
        "branch": branch,
        "expected_branch": MIRROR_BRANCH,
        "head": head,
        "origin_head": origin,
        "head_matches_origin": bool(head and origin and head == origin),
        "safe_status": status,
    }


def cadence_state(generated_dt: datetime) -> dict:
    proc = run(["git", "log", "--format=%h%x09%cI%x09%s", "-60"])
    latest = {}
    if proc.returncode != 0:
        return {"available": False, "error": proc.stderr.strip()[-500:]}
    for line in proc.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        short_hash, commit_iso, subject = parts
        if "chore(sync): heartbeat" in subject:
            key = "heartbeat"
        elif "chore(sync): health" in subject:
            key = "health"
        else:
            continue
        if key in latest:
            continue
        try:
            commit_dt = datetime.fromisoformat(commit_iso).astimezone(ZoneInfo("America/Chicago"))
            age = max(0, int(generated_dt.timestamp() - commit_dt.timestamp()))
            commit_cdt = commit_dt.strftime("%Y-%m-%d %H:%M:%S %Z")
        except Exception:
            age = None
            commit_cdt = commit_iso
        latest[key] = {
            "hash": short_hash,
            "subject": subject,
            "commit_cdt": commit_cdt,
            "age_seconds_at_generation": age,
        }
    return {
        "available": True,
        "heartbeat_stale_seconds": HEARTBEAT_STALE_SECONDS,
        "latest": latest,
    }


def process_state() -> dict:
    proc = run(["ps", "-axo", "pid,ppid,etime,command"], cwd=WORKSPACE)
    rows = []
    counts = {key: 0 for key in PROCESS_COMMAND_PATTERNS}
    if proc.returncode != 0:
        return {"available": False, "error": proc.stderr.strip()[-500:]}
    for raw in proc.stdout.splitlines()[1:]:
        parts = raw.strip().split(None, 3)
        if len(parts) < 4:
            continue
        pid, ppid, etime, command = parts
        if command.startswith("tmux new-session"):
            continue
        if "write_verifier_health.py" in command or "ps -axo" in command:
            continue
        categories = []
        for category, patterns in PROCESS_COMMAND_PATTERNS.items():
            if any(pattern in command for pattern in patterns):
                categories.append(category)
        if not categories:
            continue
        for category in categories:
            counts[category] += 1
        rows.append({
            "pid": pid,
            "ppid": ppid,
            "etime": etime,
            "categories": categories,
            "command": command,
        })
    return {"available": True, "counts": counts, "matching_processes": rows}


def sia_latest_run_state(latest_run: dict | None, generated_dt: datetime) -> dict | None:
    if not latest_run:
        return None
    mtime = latest_run.get("last_result_mtime")
    age = None
    mtime_cdt = None
    if mtime:
        try:
            age = max(0, int(generated_dt.timestamp() - float(mtime)))
            mtime_cdt = datetime.fromtimestamp(float(mtime), ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M:%S %Z")
        except Exception:
            age = None
            mtime_cdt = str(mtime)
    return {
        "run_id": latest_run.get("run_id"),
        "target_task": latest_run.get("target_task"),
        "last_generation": latest_run.get("last_generation"),
        "tripwire": latest_run.get("tripwire"),
        "updated_at": latest_run.get("updated_at"),
        "last_result_mtime_cdt": mtime_cdt,
        "latest_result_age_seconds_at_generation": age,
        "stale_threshold_seconds": SIA_LITE_RESULT_STALE_SECONDS,
        "is_stale": bool(age is None or age > SIA_LITE_RESULT_STALE_SECONDS),
    }


def artifact_freshness(generated_dt: datetime) -> dict:
    artifacts = {}
    missing = []
    stale = []
    max_age = 0
    for rel in FRESHNESS_PATHS:
        path = WORKSPACE / rel
        if not path.exists():
            artifacts[rel] = {"exists": False}
            missing.append(rel)
            continue
        mtime = path.stat().st_mtime
        age = max(0, int(generated_dt.timestamp() - mtime))
        max_age = max(max_age, age)
        if age > FRESHNESS_STALE_SECONDS:
            stale.append(rel)
        artifacts[rel] = {
            "exists": True,
            "mtime_cdt": datetime.fromtimestamp(mtime, ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M:%S %Z"),
            "age_seconds_at_generation": age,
        }
    return {
        "stale_threshold_seconds": FRESHNESS_STALE_SECONDS,
        "max_age_seconds_at_generation": max_age,
        "missing": missing,
        "stale": stale,
        "artifacts": artifacts,
    }


def main() -> None:
    generated_dt = datetime.now(ZoneInfo("America/Chicago"))
    dsl = load_json("tmp/dsl_enumeration_latest.json") or {}
    sentinel = load_json("tmp/codex_sia_all23_sentinel.json") or {}
    synth = load_json("tmp/legend_lattice_synthetic_latest.json") or {}
    sia_latest = load_json("tmp/sia_lite_latest.json") or {}
    residuals = load_json("tmp/sia_lite_residual_mining.json") or {}
    sia_policy = load_json("tmp/sia_search_policy_latest.json") or {}
    claude_watch = load_json("tmp/claude_artifact_watch_latest.json") or {}
    template_match_review = load_json("tmp/template_match_role_recolor_latest_review.json") or load_json("tmp/template_match_role_recolor_v1_review.json") or {}
    refresh = load_json("tmp/verifier_refresh_latest.json") or {}
    freshness = artifact_freshness(generated_dt)
    status = git_lines(["status", "--short", "--", *SAFE_STATUS_PATHS])
    sessions = tmux_sessions()
    mirror = mirror_state()
    cadence = cadence_state(generated_dt)
    processes = process_state()
    integration_ready = sentinel.get("integration_ready", [])
    manual_review = sentinel.get("manual_review_candidates", dsl.get("manual_review_candidates", [])) or []
    parked = sentinel.get("parked_candidates", dsl.get("parked_candidates", [])) or []
    runs = sia_latest.get("runs", []) or []
    latest_run = None
    if runs:
        latest_run = max(runs, key=lambda row: (row.get("last_result_mtime") or 0.0, row.get("run_id") or ""))
    tripwire_runs = sorted(row.get("run_id") for row in runs if row.get("tripwire"))
    latest_generation = None
    if latest_run and latest_run.get("generations"):
        latest_generation = max(
            latest_run["generations"],
            key=lambda row: (row.get("fitness") if row.get("fitness") is not None else -1e9, row.get("generation") or ""),
        )
    latest_run_state = sia_latest_run_state(latest_run, generated_dt)
    warnings = []
    if not any(line.startswith("arc2_codex_verifier:") for line in sessions):
        warnings.append("arc2_codex_verifier tmux session not visible")
    if status:
        warnings.append("safe coordination paths have uncommitted changes")
    if integration_ready:
        warnings.append("integration-ready candidate requires manual verification")
    if manual_review:
        warnings.append("manual-review candidate present")
    if tripwire_runs:
        warnings.append("SIA-lite tripwire run present")
    if processes.get("counts", {}).get("sia_lite_worker", 0) == 0 and sia_policy.get("sia_worker_expected", True):
        warnings.append("SIA-lite search worker not active")
    if latest_run_state and latest_run_state["is_stale"]:
        warnings.append("SIA-lite latest run result stale")
    if refresh.get("failures"):
        warnings.append("refresh command failure")
    if refresh.get("timed_out"):
        warnings.append("refresh command timeout")
    latest_heartbeat = cadence.get("latest", {}).get("heartbeat", {})
    if latest_heartbeat.get("age_seconds_at_generation") is None:
        warnings.append("heartbeat cadence unavailable")
    elif latest_heartbeat.get("age_seconds_at_generation", 0) > HEARTBEAT_STALE_SECONDS:
        warnings.append("heartbeat cadence stale")
    if processes.get("counts", {}).get("active_branch_push"):
        warnings.append("active-branch push process visible at health generation")
    if processes.get("counts", {}).get("github_arc_agi_transfer"):
        warnings.append("arc-agi GitHub transfer process visible at health generation")
    align = claude_watch.get("template_match_review_alignment", {})
    if align and align.get("latest_template_exists") and not align.get("latest_is_reviewed"):
        warnings.append("latest template-match generator is not reviewed")
    if freshness["missing"]:
        warnings.append("refreshed artifact missing")
    if freshness["stale"]:
        warnings.append("refreshed artifact stale")
    if not mirror.get("available"):
        warnings.append("handoff mirror worktree not visible")
    elif mirror.get("branch") != MIRROR_BRANCH:
        warnings.append("handoff mirror on unexpected branch")
    elif mirror.get("safe_status"):
        warnings.append("handoff mirror has uncommitted safe-path changes")
    elif not mirror.get("head_matches_origin"):
        warnings.append("handoff mirror head differs from local origin ref")
    out = {
        "artifact": "verifier_health_latest",
        "generated_cdt": generated_dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "branch": (run(["git", "branch", "--show-current"]).stdout.strip() or None),
        "head": (run(["git", "rev-parse", "--short", "HEAD"]).stdout.strip() or None),
        "handoff_mirror": mirror,
        "cadence_state": cadence,
        "artifact_freshness": freshness,
        "last_refresh": {
            "generated_cdt": refresh.get("generated_cdt"),
            "failures": refresh.get("failures", []),
            "timed_out": refresh.get("timed_out", []),
            "returncodes": refresh.get("returncodes", {}),
            "durations_seconds": refresh.get("durations_seconds", {}),
        },
        "process_state": processes,
        "tmux_sessions": sessions,
        "safe_status": status,
        "integration_ready": integration_ready,
        "manual_review_candidates": [
            {"task_id": row.get("task_id"), "signature": row.get("signature")} for row in manual_review
        ],
        "parked_candidates": [
            {
                "task_id": row.get("task_id"),
                "signature": row.get("signature"),
                "promotion_blockers": row.get("promotion_blockers", []),
            }
            for row in parked
        ],
        "dsl_frontier": {
            "train_exact_tasks": dsl.get("train_exact_tasks", []),
            "informative_loo_tasks": dsl.get("informative_loo_tasks", []),
            "cross_task_firing": dsl.get("cross_task_firing", {}),
        },
        "legend_lattice_synthetic": {
            "all_train_exact": synth.get("all_train_exact"),
            "all_test_exact": synth.get("all_test_exact"),
            "test_exact_tasks": synth.get("test_exact_tasks", []),
        },
        "sia_lite": {
            "n_runs": len(runs),
            "latest_run": {
                "run_id": latest_run.get("run_id"),
                "target_task": latest_run.get("target_task"),
                "last_generation": latest_run.get("last_generation"),
                "tripwire": latest_run.get("tripwire"),
                "best_generation": latest_generation,
            } if latest_run else None,
            "latest_run_state": latest_run_state,
            "tripwire_runs": tripwire_runs,
            "positive_reductions": len(residuals.get("positive_reductions", []) or []),
        },
        "sia_search_policy": {
            "generated_cdt": sia_policy.get("generated_cdt"),
            "recommendation": sia_policy.get("recommendation"),
            "sia_worker_expected": sia_policy.get("sia_worker_expected"),
            "next_action": sia_policy.get("next_action"),
            "exhausted_flat_targets": sia_policy.get("exhausted_flat_targets", []),
            "unprobed_residual_targets": sia_policy.get("unprobed_residual_targets", []),
            "admissible_signal_targets": sia_policy.get("admissible_signal_targets", []),
        },
        "template_match_role_recolor_review": {
            "generated_cdt": template_match_review.get("generated_cdt"),
            "generator_name": template_match_review.get("generator_name"),
            "generator_version": template_match_review.get("generator_version"),
            "verdict": template_match_review.get("verdict"),
            "findings": template_match_review.get("findings", []),
            "admitted_counts": template_match_review.get("admitted_counts", {}),
        },
        "claude_artifact_watch": {
            "generated_cdt": claude_watch.get("generated_cdt"),
            "template_match_review_alignment": claude_watch.get("template_match_review_alignment", {}),
            "download_counts": {
                key: row.get("count")
                for key, row in (claude_watch.get("downloads", {}) or {}).items()
                if isinstance(row, dict)
            },
        },
        "status": "attention" if warnings else "ok",
        "warnings": warnings,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(WORKSPACE)} status={out['status']} warnings={warnings}")


if __name__ == "__main__":
    main()
