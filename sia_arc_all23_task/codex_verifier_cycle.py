"""Codex ARC2 verifier heartbeat cycle.

Runs the quarantined verifier/sentinel refresh, appends a mailbox heartbeat,
commits only coordination/research artifacts, and optionally mirrors them to the
slim shared handoff branch. This script deliberately never touches the live
solver or Kaggle packaging paths.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


TASK_DIR = Path(__file__).resolve().parent
WORKSPACE = TASK_DIR.parent
MIRROR_DIR = Path("/tmp/arc_agi_handoff_sync")
MIRROR_BRANCH = "research/deep-research-handoff-2026-05-30"

SAFE_PATHS = [
    ".gitignore",
    "ARC2_AGENT_COORDINATION_STATUS.md",
    "ARC2_PROGRAM_SYNTHESIS_TARGET_QUEUE.md",
    "arc2_typed_sketch_enumerator.py",
    "arc2_sia_all23_sentinel.py",
    "sia_arc_all23_task",
    "tmp/claude_sketch_enumeration.json",
    "tmp/sia_lite_latest.json",
    "tmp/sia_lite_residual_mining.json",
    "tmp/dsl_enumeration_latest.json",
    "tmp/codex_sia_all23_sentinel.json",
]


def run(cmd: list[str], cwd: Path = WORKSPACE, timeout: int = 300, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout, check=check)


def now() -> tuple[str, str]:
    dt = datetime.now(ZoneInfo("America/Chicago"))
    return dt.strftime("%Y-%m-%d %H:%M %Z"), dt.strftime("%H:%M %Z")


def refresh() -> dict:
    outputs = {}
    commands = {
        "compile": ["python3", "-m", "py_compile", "sia_arc_all23_task/dsl_interpreter.py",
                    "sia_arc_all23_task/enumerate_dsl.py", "sia_arc_all23_task/sia_lite_harness.py",
                    "arc2_sia_all23_sentinel.py"],
        "dsl_enum": ["python3", "sia_arc_all23_task/enumerate_dsl.py"],
        "sia_latest": ["python3", "sia_arc_all23_task/write_sia_lite_latest.py"],
        "sia_mine": ["python3", "sia_arc_all23_task/mine_sia_residuals.py"],
        "sketch_enum": ["python3", "arc2_typed_sketch_enumerator.py"],
        "sentinel": ["python3", "arc2_sia_all23_sentinel.py"],
    }
    for label, cmd in commands.items():
        proc = run(cmd, timeout=600 if label == "sentinel" else 300, check=False)
        outputs[label] = {
            "returncode": proc.returncode,
            "stdout_tail": proc.stdout[-2000:],
            "stderr_tail": proc.stderr[-2000:],
        }
    return outputs


def load_json(path: str):
    p = WORKSPACE / path
    if not p.exists():
        return None
    return json.loads(p.read_text())


def heartbeat_text(refresh_outputs: dict) -> str:
    ts, _hm = now()
    dsl = load_json("tmp/dsl_enumeration_latest.json") or {}
    sentinel = load_json("tmp/codex_sia_all23_sentinel.json") or {}
    sia_latest = load_json("tmp/sia_lite_latest.json") or {}
    exact = dsl.get("train_exact_tasks", [])
    informative = dsl.get("informative_loo_tasks", [])
    cross = dsl.get("cross_task_firing", {})
    ready = sentinel.get("integration_ready", [])
    latest_run = None
    runs = sia_latest.get("runs", [])
    if runs:
        latest_run = max(runs, key=lambda row: (row.get("last_result_mtime") or 0.0, row.get("run_id") or ""))
    failed = [k for k, v in refresh_outputs.items() if v["returncode"] != 0]
    lines = [
        f"\nCodex heartbeat — {ts}:\n",
        "- Verifier cycle refreshed DSL/SIA/sketch/sentinel artifacts.",
        f"- Shared mirror branch: `{MIRROR_BRANCH}`.",
        f"- DSL frontier: train_exact={exact}, informative_loo={informative}, cross={cross}.",
        f"- SIA sentinel integration_ready={ready}.",
    ]
    if latest_run:
        lines.append(
            "- Latest SIA-lite summary: "
            f"run_id={latest_run.get('run_id')}, last_generation={latest_run.get('last_generation')}, "
            f"target_task={latest_run.get('target_task')}, "
            f"tripwire={latest_run.get('tripwire')}."
        )
    if failed:
        lines.append(f"- WARNING: refresh command failures={failed}; see cycle stdout/stderr tails in local logs.")
    else:
        lines.append("- Refresh commands all returned 0.")
    lines.append("- No automatic live-solver promotion without informative LOO/cross plus manual verification.\n")
    return "\n".join(lines)


def append_heartbeat(refresh_outputs: dict) -> None:
    mailbox = WORKSPACE / "ARC2_AGENT_COORDINATION_STATUS.md"
    with mailbox.open("a") as fh:
        fh.write(heartbeat_text(refresh_outputs))


def commit_current() -> bool:
    _ts, hm = now()
    run(["git", "add", *SAFE_PATHS], check=False)
    proc = run(["git", "commit", "-m", f"chore(sync): heartbeat {hm}"], check=False)
    return proc.returncode == 0


def mirror_push() -> None:
    if not MIRROR_DIR.exists():
        return
    head = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    run(["git", "fetch", "origin", MIRROR_BRANCH], cwd=MIRROR_DIR, check=False)
    run(["git", "merge", "--ff-only", f"origin/{MIRROR_BRANCH}"], cwd=MIRROR_DIR, check=False)
    run(["git", "checkout", head, "--", *SAFE_PATHS], cwd=MIRROR_DIR)
    run(["git", "add", *SAFE_PATHS], cwd=MIRROR_DIR, check=False)
    _ts, hm = now()
    run(["git", "commit", "-m", f"chore(sync): heartbeat {hm}"], cwd=MIRROR_DIR, check=False)
    run(["git", "push", "origin", MIRROR_BRANCH], cwd=MIRROR_DIR, check=False)


def cycle(push: bool, commit: bool) -> None:
    outputs = refresh()
    append_heartbeat(outputs)
    made_commit = commit_current() if commit else False
    if push and commit and made_commit:
        mirror_push()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true", help="Run forever.")
    ap.add_argument("--interval", type=int, default=300)
    ap.add_argument("--no-commit", action="store_true")
    ap.add_argument("--push", action="store_true")
    args = ap.parse_args()
    while True:
        cycle(push=args.push, commit=not args.no_commit)
        if not args.loop:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
