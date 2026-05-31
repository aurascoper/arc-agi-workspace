"""Codex sentinel verifier for standalone ARC2 research artifacts.

This verifier is intentionally design-only. It does not edit the live Kaggle
solver, synthesize from held-out outputs, or promote candidates. Its job is to
turn Claude/Codex standalone-lane claims into a compact, repeatable readiness
record:

- compile and rerun the reusable research scripts,
- inspect their JSON outputs,
- run a conservative static leakage scan,
- decide whether anything is integration-ready under the current admission
  discipline.

Promotion remains manual and requires a concrete transform with train exactness,
informative LOO or cross-task firing, synthetic/invariance evidence, and no
public/frozen leakage.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parent
TMP = WORKSPACE / "tmp"
OUT_JSON = TMP / "codex_research_artifact_verifier.json"

ARTIFACTS = {
    "object_graph": {
        "script": "arc2_object_graph.py",
        "json": None,
        "kind": "infra",
    },
    "shape_decomposition": {
        "script": "arc2_shape_decomposition_synth.py",
        "json": "tmp/claude_shape_decomposition_results.json",
        "kind": "candidate_probe",
    },
    "typed_sketch_enumerator": {
        "script": "arc2_typed_sketch_enumerator.py",
        "json": "tmp/claude_sketch_enumeration.json",
        "kind": "infra",
    },
}

FORBIDDEN_PATTERNS = [
    r"arc_agi_2_data/test",
    r"pseudo_private",
    r"public_signature",
    r"signature_renderer",
    r"template_replay",
    r"\bsolve_[0-9a-f]{8}\b",
    r"\barc2_candidate_solver\.py\b",
    r"\bsubmission_helper\.py\b",
    r"\bkaggle_modules\b",
]

SELF_SCAN_CONTEXT = (
    "FORBIDDEN_PATTERNS",
    "forbidden",
    "leakage",
    "static scan",
    "static_scan",
    "Never edits Codex hot files",
    "does not edit the live Kaggle solver",
)


def run_cmd(args: list[str], timeout: int = 120) -> dict[str, Any]:
    proc = subprocess.run(
        args,
        cwd=WORKSPACE,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    return {
        "cmd": args,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
        "ok": proc.returncode == 0,
    }


def compile_script(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"ok": False, "missing": True, "path": str(path)}
    return run_cmd([sys.executable, "-m", "py_compile", path.name])


def run_script(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"ok": False, "missing": True, "path": str(path)}
    return run_cmd([sys.executable, path.name])


def parse_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"ok": True, "present": False, "summary": {}}
    if not path.exists():
        return {"ok": False, "present": False, "path": str(path), "summary": {}}
    try:
        data = json.loads(path.read_text())
    except Exception as exc:  # pragma: no cover - sentinel diagnostic
        return {"ok": False, "present": True, "path": str(path), "error": repr(exc), "summary": {}}
    return {"ok": True, "present": True, "path": str(path), "summary": summarize_json(data)}


def summarize_json(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"type": type(data).__name__}
    out: dict[str, Any] = {"keys": sorted(data)[:20]}
    if "flips" in data:
        out["flips"] = data.get("flips")
    if "claude_flips" in data:
        out["claude_flips"] = data.get("claude_flips")
    if "integration_ready" in data:
        out["integration_ready"] = data.get("integration_ready")
    if "rows" in data and isinstance(data["rows"], list):
        out["rows"] = len(data["rows"])
        out["train_exact_rows"] = sum(1 for r in data["rows"] if isinstance(r, dict) and r.get("train_exact"))
        out["loo_rows"] = sum(1 for r in data["rows"] if isinstance(r, dict) and r.get("informative_loo"))
    if "results" in data and isinstance(data["results"], list):
        out["results"] = len(data["results"])
        out["tasks_with_sketches"] = sum(
            1 for r in data["results"]
            if isinstance(r, dict) and r.get("n_sketches", 0) > 0
        )
    if "template_coverage" in data:
        out["template_coverage"] = data["template_coverage"]
    if "leakage_scan_hits" in data:
        out["leakage_scan_hits"] = data["leakage_scan_hits"]
    return out


def task_id_literals(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return []
    ids: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if re.fullmatch(r"[0-9a-f]{8}", node.value):
                ids.add(node.value)
    return sorted(ids)


def static_scan(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"ok": False, "missing": True, "hits": []}
    hits: list[dict[str, Any]] = []
    lines = path.read_text().splitlines()
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for pattern in FORBIDDEN_PATTERNS:
            if not re.search(pattern, line):
                continue
            if any(token in line for token in SELF_SCAN_CONTEXT):
                continue
            hits.append({"pattern": pattern, "line": lineno, "text": stripped[:160]})
    return {
        "ok": not hits,
        "hits": hits,
        "task_id_literals": task_id_literals(path),
    }


def artifact_ready(name: str, report: dict[str, Any]) -> bool:
    if not report["compile"].get("ok") or not report["run"].get("ok") or not report["static_scan"].get("ok"):
        return False
    meta = ARTIFACTS[name]
    if meta["kind"] != "candidate_probe":
        return False
    summary = report["json"].get("summary", {})
    flips = summary.get("flips") or summary.get("claude_flips") or []
    return bool(flips)


def verify_artifact(name: str, meta: dict[str, Any]) -> dict[str, Any]:
    script = WORKSPACE / meta["script"]
    json_path = WORKSPACE / meta["json"] if meta["json"] else None
    report = {
        "script": str(script.relative_to(WORKSPACE)),
        "kind": meta["kind"],
        "compile": compile_script(script),
        "run": run_script(script),
        "static_scan": static_scan(script),
        "json": parse_json(json_path),
    }
    report["integration_ready"] = artifact_ready(name, report)
    return report


def main() -> None:
    TMP.mkdir(exist_ok=True)
    artifacts = {name: verify_artifact(name, meta) for name, meta in ARTIFACTS.items()}
    integration_ready = [
        name for name, report in artifacts.items()
        if report.get("integration_ready")
    ]
    out = {
        "lane": "research_artifact_verifier",
        "artifacts": artifacts,
        "integration_ready": integration_ready,
        "integration_ready_bool": bool(integration_ready),
    }
    OUT_JSON.write_text(json.dumps(out, indent=2))
    print("Codex research artifact verifier")
    for name, report in artifacts.items():
        summary = report["json"].get("summary", {})
        print(
            f"  {name:24} compile={report['compile'].get('ok')} "
            f"run={report['run'].get('ok')} scan={report['static_scan'].get('ok')} "
            f"ready={report['integration_ready']} summary={summary}"
        )
    print(f"integration_ready={integration_ready}")
    print(f"wrote {OUT_JSON.relative_to(WORKSPACE)}")


if __name__ == "__main__":
    main()
