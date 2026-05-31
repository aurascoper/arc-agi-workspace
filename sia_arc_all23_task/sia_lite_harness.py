"""Minimal quarantined SIA-lite loop for ARC2 all-23.

This is a small generate/gate/score/select harness around the existing
`evaluate.py`. It never edits the live solver. Generated agents are written
under workspace-root `runs/<run_id>/gen_<n>/` and only count if they pass the
same evaluator gates used by the SIA task.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


TASK_DIR = Path(__file__).resolve().parent
WORKSPACE = TASK_DIR.parent
REFERENCE = TASK_DIR / "reference" / "reference_target_agent.py"
MUTATOR_PROMPT = TASK_DIR / "MUTATOR_SYSTEM_PROMPT.md"
EVALUATE = TASK_DIR / "evaluate.py"
EVALUATOR = TASK_DIR / "evaluator.py"


def _load_evaluator():
    spec = importlib.util.spec_from_file_location("sia_all23_evaluator", EVALUATOR)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod._load_base()


def _read_prompt() -> str:
    text = MUTATOR_PROMPT.read_text()
    marker = "## SYSTEM PROMPT"
    if marker in text:
        return text[text.index(marker):]
    return text


def _extract_python(text: str) -> str:
    blocks = re.findall(r"```(?:python)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    return (blocks[-1] if blocks else text).strip() + "\n"


def _call_openai(model: str, temperature: float, messages: list[dict[str, str]], max_tokens: int) -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:4000]
        raise RuntimeError(f"OpenAI HTTP {exc.code}: {detail}") from exc
    return data["choices"][0]["message"]["content"]


def _py_compile(path: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        cwd=WORKSPACE,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
    )
    return proc.returncode == 0, (proc.stderr or proc.stdout)[-4000:]


def _score(gen_dir: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(EVALUATE), "--gen-dir", str(gen_dir)],
        cwd=WORKSPACE,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=300,
    )
    result_path = gen_dir / "results.json"
    if result_path.exists():
        data = json.loads(result_path.read_text())
    else:
        data = {
            "status": "error",
            "fitness": -100.0,
            "reason": "evaluate.py did not write results.json",
        }
    data["evaluate_returncode"] = proc.returncode
    data["evaluate_stderr_tail"] = proc.stderr[-4000:]
    return data


def _loo_count(report: dict[str, Any]) -> int:
    return sum(1 for t in report.get("tasks", []) if isinstance(t, dict) and t.get("informative_loo"))


def _cross_count(report: dict[str, Any]) -> int:
    return len(report.get("cross_task_firing", {}) or {})


def _cross_task_max(report: dict[str, Any]) -> int:
    cross = report.get("cross_task_firing", {}) or {}
    return max((len(tids) for tids in cross.values()), default=0)


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "fitness": report.get("fitness"),
        "status": report.get("status"),
        "leaks": len(report.get("leakage_hits", [])),
        "loo_tasks": _loo_count(report),
        "cross_names": _cross_count(report),
        "cross_task_max": _cross_task_max(report),
        "train_exact_total": sum(
            t.get("n_train_exact", 0) for t in report.get("tasks", []) if isinstance(t, dict)
        ),
        "private_true_total": sum(1 for v in report.get("private_readout", {}).values() if v is True),
    }


def _prompt_for(seed_source: str, best_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    score_text = json.dumps(best_rows, indent=2)[:12000]
    user = f"""Mutate the current best ARC2 SIA target agent.

Current best score summaries:
```json
{score_text}
```

Current best module:
```python
{seed_source}
```

Return exactly one full Python module in a single fenced python block.
"""
    return [{"role": "system", "content": _read_prompt()}, {"role": "user", "content": user}]


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2))


def run(args: argparse.Namespace) -> dict[str, Any]:
    run_root = WORKSPACE / "runs" / args.run_id
    run_root.mkdir(parents=True, exist_ok=True)
    evaluator = _load_evaluator()
    population: list[dict[str, Any]] = []
    seed_source = REFERENCE.read_text()

    seed_dir = run_root / "seed"
    seed_dir.mkdir(exist_ok=True)
    (seed_dir / "target_agent.py").write_text(seed_source)
    seed_report = _score(seed_dir)
    population.append({"path": str(seed_dir / "target_agent.py"), "summary": _summary(seed_report)})

    if args.dry_run:
        out = {"run_id": args.run_id, "dry_run": True, "population": population}
        _write_json(run_root / "state.json", out)
        return out

    for gen in range(1, args.max_gen + 1):
        gen_dir = run_root / f"gen_{gen}"
        gen_dir.mkdir(exist_ok=True)
        best = max(population, key=lambda row: row["summary"].get("fitness", -999))
        seed_source = Path(best["path"]).read_text()
        gen_meta: dict[str, Any] = {"generation": gen, "seed": best}
        try:
            content = _call_openai(
                args.model,
                args.temperature,
                _prompt_for(seed_source, [p["summary"] for p in population]),
                args.max_tokens,
            )
            code = _extract_python(content)
            gen_meta["raw_response"] = content
        except Exception as exc:
            gen_meta.update({"status": "generation_error", "error": str(exc), "fitness": -100.0})
            _write_json(gen_dir / "results.json", gen_meta)
            population.append({"path": str(gen_dir / "target_agent.py"), "summary": _summary(gen_meta)})
            break

        agent = gen_dir / "target_agent.py"
        agent.write_text(code)
        ok, compile_log = _py_compile(agent)
        gen_meta["compile_ok"] = ok
        gen_meta["compile_log"] = compile_log
        if not ok:
            gen_meta.update({"status": "compile_error", "fitness": -100.0})
            _write_json(gen_dir / "results.json", gen_meta)
        else:
            leaks = evaluator.leakage_scan(agent)
            gen_meta["leakage_hits"] = leaks
            if leaks:
                gen_meta.update({"status": "leakage_rejected", "fitness": -5.0 * len(leaks)})
                _write_json(gen_dir / "results.json", gen_meta)
            else:
                report = _score(gen_dir)
                report["pre_score_gate"] = gen_meta
                gen_meta = report
        _write_json(gen_dir / "generation_meta.json", gen_meta)
        population.append({"path": str(agent), "summary": _summary(gen_meta)})
        population = sorted(population, key=lambda row: row["summary"].get("fitness", -999), reverse=True)[:args.top_k]
        state = {"run_id": args.run_id, "population": population, "last_generation": gen}
        _write_json(run_root / "state.json", state)
        if _loo_count(gen_meta) >= 1 or _cross_task_max(gen_meta) >= 2:
            state["tripwire"] = True
            _write_json(run_root / "state.json", state)
            return state
        time.sleep(args.sleep)
    return {"run_id": args.run_id, "population": population, "tripwire": False}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=f"sia_lite_{int(time.time())}")
    ap.add_argument("--model", default="gpt-4.1-mini")
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--max-gen", type=int, default=8)
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--max-tokens", type=int, default=16000)
    ap.add_argument("--sleep", type=float, default=0.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    out = run(args)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
