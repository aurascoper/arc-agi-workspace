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
    body_obj: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    token_key = "max_completion_tokens" if model.startswith(("gpt-5", "o")) else "max_tokens"
    body_obj[token_key] = max_tokens
    body = json.dumps(body_obj).encode()
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


def _target_row(report: dict[str, Any], target_task: str | None) -> dict[str, Any] | None:
    if not target_task:
        return None
    for row in report.get("tasks", []) or []:
        if isinstance(row, dict) and row.get("task_id") == target_task:
            return row
    return None


def _summary(report: dict[str, Any], target_task: str | None = None) -> dict[str, Any]:
    row = _target_row(report, target_task)
    best_shape = row.get("best_shape_train_diff") if isinstance(row, dict) else None
    out = {
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
    if row is not None:
        target_diff = best_shape.get("diff") if isinstance(best_shape, dict) else None
        out.update({
            "target_task": target_task,
            "target_train_exact": row.get("n_train_exact", 0),
            "target_informative_loo": bool(row.get("informative_loo")),
            "target_shape_exact": row.get("n_shape_exact", 0),
            "target_best_shape_diff": target_diff,
            "target_train_exact_names": row.get("train_exact_names", []),
        })
    out["selection_score"] = _selection_score(out)
    return out


def _selection_score(summary: dict[str, Any]) -> float:
    fitness = summary.get("fitness")
    score = float(fitness if fitness is not None else -100.0)
    if summary.get("target_task"):
        if summary.get("target_train_exact", 0):
            score += 3.0
        if summary.get("target_informative_loo"):
            score += 5.0
        diff = summary.get("target_best_shape_diff")
        if isinstance(diff, int):
            score += max(0.0, 1.0 - min(diff, 250) / 250.0)
        if summary.get("target_shape_exact", 0):
            score += 0.05
    return round(score, 4)


def _prompt_safe_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Drop log-only/private or identity-bearing fields before asking a mutator."""
    banned = {"private_true_total", "target_task"}
    return {k: v for k, v in summary.items() if k not in banned}


def _load_target_context(target_task: str | None) -> str:
    if not target_task:
        return ""
    path = TASK_DIR / "data" / "public" / f"{target_task}.json"
    if not path.exists():
        raise FileNotFoundError(f"unknown --target-task {target_task!r}: {path} does not exist")
    data = json.loads(path.read_text())
    train_only = {"train": data.get("train", [])}
    summary = _target_train_summary(train_only["train"])
    blob = json.dumps(train_only, separators=(",", ":"))
    if len(blob) > 50000:
        blob = json.dumps(train_only, indent=2)[:50000]
    return f"""Selected task train pairs (task id omitted; do not write any task id or output-template literal in code):
```json
{blob}
```

Train-only diff summary:
```json
{json.dumps(summary, separators=(",", ":"))}
```

Task-conditioned objective for this generation:
- Replace or parameterize one weak family so it becomes train-exact on the selected task above.
- Learn all parameters from `train`; do not paste these grids into source code.
- Prefer a candidate name that encodes learned abstract parameters, not coordinates or task identity.
"""


def _target_train_summary(train: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, pair in enumerate(train):
        gi = pair.get("input", [])
        go = pair.get("output", [])
        h = len(gi)
        w = len(gi[0]) if gi else 0
        oh = len(go)
        ow = len(go[0]) if go else 0
        trans: dict[str, int] = {}
        changed: list[tuple[int, int]] = []
        if h == oh and w == ow:
            for r in range(h):
                for c in range(w):
                    a, b = gi[r][c], go[r][c]
                    if a != b:
                        trans[f"{a}->{b}"] = trans.get(f"{a}->{b}", 0) + 1
                        changed.append((r, c))
        bbox = None
        if changed:
            rs = [r for r, _ in changed]
            cs = [c for _, c in changed]
            bbox = [min(rs), min(cs), max(rs), max(cs)]
        rows.append({
            "pair": idx,
            "shape": [h, w],
            "output_shape": [oh, ow],
            "input_palette": sorted({v for row in gi for v in row}),
            "output_palette": sorted({v for row in go for v in row}),
            "changed": len(changed) if h == oh and w == ow else None,
            "changed_bbox": bbox,
            "transitions": dict(sorted(trans.items(), key=lambda kv: (-kv[1], kv[0]))[:12]),
        })
    return rows


def _prompt_for(
    seed_source: str,
    best_rows: list[dict[str, Any]],
    target_context: str = "",
    focus: str = "",
) -> list[dict[str, str]]:
    score_text = json.dumps(best_rows, indent=2)[:12000]
    focus_text = f"\nAdditional focus from harness:\n{focus.strip()}\n" if focus.strip() else ""
    target_text = f"\n{target_context}\n" if target_context else ""
    user = f"""Mutate the current best ARC2 SIA target agent.

Current best score summaries:
```json
{score_text}
```
{target_text}{focus_text}

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
    target_context = _load_target_context(args.target_task)
    population: list[dict[str, Any]] = []
    seed_source = REFERENCE.read_text()

    seed_dir = run_root / "seed"
    seed_dir.mkdir(exist_ok=True)
    (seed_dir / "target_agent.py").write_text(seed_source)
    seed_report = _score(seed_dir)
    population.append({"path": str(seed_dir / "target_agent.py"), "summary": _summary(seed_report, args.target_task)})

    if args.dry_run:
        out = {"run_id": args.run_id, "dry_run": True, "population": population}
        _write_json(run_root / "state.json", out)
        return out

    for gen in range(1, args.max_gen + 1):
        gen_dir = run_root / f"gen_{gen}"
        gen_dir.mkdir(exist_ok=True)
        best = max(population, key=lambda row: row["summary"].get("selection_score", -999))
        seed_source = Path(best["path"]).read_text()
        gen_meta: dict[str, Any] = {"generation": gen, "seed": best}
        try:
            content = _call_openai(
                args.model,
                args.temperature,
                _prompt_for(
                    seed_source,
                    [_prompt_safe_summary(p["summary"]) for p in population],
                    target_context,
                    args.focus,
                ),
                args.max_tokens,
            )
            code = _extract_python(content)
            gen_meta["raw_response"] = content
        except Exception as exc:
            gen_meta.update({"status": "generation_error", "error": str(exc), "fitness": -100.0})
            _write_json(gen_dir / "results.json", gen_meta)
            population.append({"path": str(gen_dir / "target_agent.py"), "summary": _summary(gen_meta, args.target_task)})
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
        population.append({"path": str(agent), "summary": _summary(gen_meta, args.target_task)})
        population = sorted(
            population,
            key=lambda row: row["summary"].get("selection_score", -999),
            reverse=True,
        )[:args.top_k]
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
    ap.add_argument("--target-task", help="Inject this public task's train pairs into the mutator prompt; id is omitted from the prompt.")
    ap.add_argument("--focus", default="", help="Additional train-only mutation guidance appended to the user prompt.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    out = run(args)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
