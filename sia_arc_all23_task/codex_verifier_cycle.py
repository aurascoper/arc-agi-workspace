"""Codex ARC2 verifier heartbeat cycle.

Runs the quarantined verifier/sentinel refresh, appends a mailbox heartbeat,
commits only coordination/research artifacts, and optionally mirrors them to the
slim shared handoff branch. This script deliberately never touches the live
solver or Kaggle packaging paths.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
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
    "tmp/legend_lattice_synthetic_latest.json",
    "tmp/verifier_health_latest.json",
    "tmp/verifier_refresh_latest.json",
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
                    "sia_arc_all23_task/legend_lattice_synthetic.py",
                    "sia_arc_all23_task/write_sia_lite_latest.py",
                    "sia_arc_all23_task/mine_sia_residuals.py",
                    "sia_arc_all23_task/write_verifier_health.py",
                    "arc2_typed_sketch_enumerator.py", "arc2_sia_all23_sentinel.py"],
        "legend_synth": ["python3", "sia_arc_all23_task/legend_lattice_synthetic.py"],
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


def write_refresh_artifact(refresh_outputs: dict) -> None:
    ts, _hm = now()
    out = {
        "artifact": "verifier_refresh_latest",
        "generated_cdt": ts,
        "failures": [label for label, row in refresh_outputs.items() if row["returncode"] != 0],
        "returncodes": {label: row["returncode"] for label, row in refresh_outputs.items()},
        "outputs": refresh_outputs,
    }
    (WORKSPACE / "tmp").mkdir(exist_ok=True)
    (WORKSPACE / "tmp" / "verifier_refresh_latest.json").write_text(json.dumps(out, indent=2) + "\n")


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
    legend_synth = load_json("tmp/legend_lattice_synthetic_latest.json") or {}
    exact = dsl.get("train_exact_tasks", [])
    informative = dsl.get("informative_loo_tasks", [])
    cross = dsl.get("cross_task_firing", {})
    review = dsl.get("manual_review_candidates", [])
    parked = dsl.get("parked_candidates", [])
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
        f"- DSL manual_review_candidates={[(r.get('task_id'), r.get('signature')) for r in review]}.",
        f"- DSL parked_candidates={[(r.get('task_id'), r.get('signature')) for r in parked]}.",
        f"- SIA sentinel integration_ready={ready}.",
    ]
    if legend_synth:
        lines.append(
            "- Legend-lattice synthetic: "
            f"all_train_exact={legend_synth.get('all_train_exact')}, "
            f"all_test_exact={legend_synth.get('all_test_exact')}, "
            f"test_exact_tasks={legend_synth.get('test_exact_tasks')}."
        )
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


def existing_safe_paths() -> list[str]:
    return [path for path in SAFE_PATHS if (WORKSPACE / path).exists()]


def commit_current(label: str = "heartbeat") -> bool:
    _ts, hm = now()
    run(["git", "add", *existing_safe_paths()], check=False)
    proc = run(["git", "commit", "-m", f"chore(sync): {label} {hm}"], check=False)
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


def push_active_branch() -> None:
    branch = run(["git", "branch", "--show-current"], check=False).stdout.strip()
    if not branch:
        return
    proc = subprocess.Popen(
        ["git", "push", "origin", f"HEAD:{branch}"],
        cwd=WORKSPACE,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        # The full research branch can be much heavier than the slim handoff
        # branch; kill the whole process group so orphan SSH pushes do not
        # accumulate and stall the heartbeat cadence.
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.communicate(timeout=5)
        except Exception:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                pass


def cycle(push: bool, commit: bool) -> None:
    outputs = refresh()
    write_refresh_artifact(outputs)
    append_heartbeat(outputs)
    made_commit = commit_current("heartbeat") if commit else False
    if push and commit and made_commit:
        mirror_push()
    health_commit = False
    if commit:
        run(["python3", "sia_arc_all23_task/write_verifier_health.py"], check=False)
        health_commit = commit_current("health")
    if push and commit and (made_commit or health_commit):
        push_active_branch()
        mirror_push()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true", help="Run forever.")
    ap.add_argument("--interval", type=int, default=300)
    ap.add_argument("--no-commit", action="store_true")
    ap.add_argument("--push", action="store_true")
    args = ap.parse_args()
    while True:
        cycle_started = time.monotonic()
        cycle(push=args.push, commit=not args.no_commit)
        if not args.loop:
            break
        time.sleep(max(0, args.interval - (time.monotonic() - cycle_started)))


if __name__ == "__main__":
    main()
