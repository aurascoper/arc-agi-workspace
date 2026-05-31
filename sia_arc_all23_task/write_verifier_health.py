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
SAFE_STATUS_PATHS = [
    ".gitignore",
    "ARC2_AGENT_COORDINATION_STATUS.md",
    "arc2_sia_all23_sentinel.py",
    "sia_arc_all23_task",
    "tmp/dsl_enumeration_latest.json",
    "tmp/codex_sia_all23_sentinel.json",
    "tmp/sia_lite_latest.json",
    "tmp/sia_lite_residual_mining.json",
    "tmp/claude_sketch_enumeration.json",
    "tmp/legend_lattice_synthetic_latest.json",
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


def main() -> None:
    dsl = load_json("tmp/dsl_enumeration_latest.json") or {}
    sentinel = load_json("tmp/codex_sia_all23_sentinel.json") or {}
    synth = load_json("tmp/legend_lattice_synthetic_latest.json") or {}
    status = git_lines(["status", "--short", "--", *SAFE_STATUS_PATHS])
    sessions = tmux_sessions()
    integration_ready = sentinel.get("integration_ready", [])
    manual_review = sentinel.get("manual_review_candidates", dsl.get("manual_review_candidates", [])) or []
    parked = sentinel.get("parked_candidates", dsl.get("parked_candidates", [])) or []
    warnings = []
    if not any(line.startswith("arc2_codex_verifier:") for line in sessions):
        warnings.append("arc2_codex_verifier tmux session not visible")
    if status:
        warnings.append("safe coordination paths have uncommitted changes")
    if integration_ready:
        warnings.append("integration-ready candidate requires manual verification")
    if manual_review:
        warnings.append("manual-review candidate present")
    out = {
        "artifact": "verifier_health_latest",
        "generated_cdt": datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "branch": (run(["git", "branch", "--show-current"]).stdout.strip() or None),
        "head": (run(["git", "rev-parse", "--short", "HEAD"]).stdout.strip() or None),
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
        "status": "attention" if warnings else "ok",
        "warnings": warnings,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(WORKSPACE)} status={out['status']} warnings={warnings}")


if __name__ == "__main__":
    main()
