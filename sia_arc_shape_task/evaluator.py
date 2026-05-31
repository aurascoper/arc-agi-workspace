"""Quarantined SIA evaluator for ARC shape/decomposition research (Claude lane).

THIS IS THE SANDBOX. SIA's danger is a self-improvement loop that exploits the eval harness; this grader
makes that hard by encoding the design-only admission protocol and keeping the held-out (private) readout
OUT of the fitness signal SIA optimizes.

Agent contract (reference_agent.py / SIA's target_agent.py must define):
    propose(train) -> list[(name:str, transform: grid->grid)]
        # learn candidate transforms from TRAIN PAIRS ONLY. No test outputs are available to the agent.

Fitness (what SIA maximizes) is built ONLY from hidden-safe signals:
    + 1.0   per public task with a TRAIN-EXACT + INFORMATIVE-LOO candidate (genuine re-derivation)
    + 0.5   per public task with a TRAIN-EXACT candidate whose NAME fires train-exact on >=2 public tasks
    + 0.1   per public task with any TRAIN-EXACT candidate (weak partial credit)
    - 5.0   per leakage-scan hit (task ids / coordinate templates / public-signature / replay)
    -100.0  if the agent fails to import/compile
The PRIVATE (design-test) match is computed and LOGGED for humans, but NEVER added to fitness — so SIA cannot
optimize by exploiting the held-out outputs. Promotion to the live solver is a separate manual Codex step,
gated on the logged evidence.

Usage:  python3 evaluator.py --agent reference_agent.py        # prints fitness + per-task evidence + private log
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import signal
import sys
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).resolve().parent
PUBLIC = HERE / "data" / "public"
PRIVATE = HERE / "data" / "private"
PER_CANDIDATE_TIMEOUT = 4  # seconds


# ----------------------------------------------------------------- safety: leakage scan
FORBIDDEN = [
    (r"\bsolve_[0-9a-f]{8}\b", "task-id dispatch"),
    (r"data.{0,80}private|private.{0,80}data", "reads the private split"),
    (r"\bPRIVATE\b|\bprivate\b|\btest_outputs\b", "mentions held-out private outputs"),
    (r"\barc_agi_2_data\b|\bevaluation\b", "bypasses SIA public split"),
    (r"\b(5dbc8537|edb79dae|20a9e565|2d0172a1|6ffbe589|e87109e9|89565ca0)\b", "hardcoded target task id"),
    (r"pseudo_private|public_signature|coordinate_signature", "forbidden signature/replay"),
    (r"OUTPUT_TEMPLATE\s*=|=\s*\[\[\d.*\],\s*\[\d", "hardcoded output template literal"),
]
# NB: reading train pair["output"] is LEGITIMATE (agents learn from train); the public split has no test
# outputs, so an agent cannot read them. Leakage vectors are: task-id dispatch, private reads, templates.


def leakage_scan(agent_path: Path):
    src = agent_path.read_text()
    hits = []
    for pat, why in FORBIDDEN:
        for m in re.finditer(pat, src, re.MULTILINE):
            ln = src[:m.start()].count("\n") + 1
            line = src.splitlines()[ln - 1].strip()
            if line.startswith("#") or line.startswith('"') or "FORBIDDEN" in line:
                continue
            hits.append({"why": why, "line": ln, "text": line[:80]})
    return hits


# ----------------------------------------------------------------- grids
def norm(g):
    return [[int(v) for v in row] for row in g]


def equal(a, b):
    return norm(a) == norm(b)


def dims(g):
    g = norm(g)
    return (len(g), len(g[0]) if g else 0)


def pixel_diff(a, b):
    """Finite diff only for same-shape grids; otherwise None."""
    aa, bb = norm(a), norm(b)
    if dims(aa) != dims(bb):
        return None
    return sum(x != y for ra, rb in zip(aa, bb) for x, y in zip(ra, rb))


class _Timeout(Exception):
    pass


def _alarm(*_):
    raise _Timeout()


def _call(fn, *a):
    signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, PER_CANDIDATE_TIMEOUT)
    try:
        return fn(*a)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


# ----------------------------------------------------------------- gates
def train_exact(t, train):
    try:
        return all(equal(_call(t, deepcopy(p["input"])), p["output"]) for p in train)
    except Exception:
        return False


def candidate_train_diagnostics(cands, train):
    """Non-fitness diagnostics: shape matches and residuals on train only."""
    rows = []
    for name, t in cands:
        shape_ok = True
        total_diff = 0
        diffs = []
        pred_shapes = []
        error = None
        for p in train:
            try:
                pred = _call(t, deepcopy(p["input"]))
                pred_shape = dims(pred)
                out_shape = dims(p["output"])
                pred_shapes.append(pred_shape)
                if pred_shape != out_shape:
                    shape_ok = False
                    diffs.append(None)
                    continue
                d = pixel_diff(pred, p["output"])
                diffs.append(d)
                total_diff += int(d or 0)
            except Exception as exc:
                error = type(exc).__name__
                shape_ok = False
                diffs.append(None)
                break
        rows.append({
            "name": name,
            "shape_exact": shape_ok,
            "train_diff": total_diff if shape_ok else None,
            "per_pair_diff": diffs,
            "pred_shapes": pred_shapes[:5],
            "error": error,
        })
    return rows


def informative_loo(propose, train, required_name=None):
    """Re-call propose() on each n-1 subset and require a stable candidate family/name.

    A full-train candidate should not receive LOO credit merely because a different
    candidate produced by the subset happens to solve the held pair. For promotion
    evidence, the same named family must be re-derived on every fold.
    """
    if len(train) <= 1:
        return False
    for i in range(len(train)):
        sub = [train[j] for j in range(len(train)) if j != i]
        held = train[i]
        try:
            cands = propose(sub)
        except Exception:
            return False
        ok = False
        for name, t in cands or []:
            if required_name is not None and name != required_name:
                continue
            try:
                if equal(_call(t, deepcopy(held["input"])), held["output"]):
                    ok = True
                    break
            except Exception:
                continue
        if not ok:
            return False
    return True


def synthetic_color_perm(t, train):
    m = {v: (v + 3) % 10 for v in range(10)}
    perm = lambda g: [[m.get(v, v) for v in row] for row in norm(g)]
    try:
        return all(norm(_call(t, perm(p["input"]))) == perm(norm(_call(t, deepcopy(p["input"])))) for p in train)
    except Exception:
        return False


# ----------------------------------------------------------------- evaluate
def load_agent(path: Path):
    spec = importlib.util.spec_from_file_location("sia_target_agent", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "propose"):
        raise AttributeError("agent must define propose(train) -> list[(name, transform)]")
    return mod


def evaluate(agent_path: Path) -> dict:
    leaks = leakage_scan(agent_path)
    report = {"agent": agent_path.name, "leakage_hits": leaks, "tasks": [], "fitness": 0.0,
              "private_readout": {}}
    try:
        agent = load_agent(agent_path)
    except Exception as e:
        report["compile_error"] = str(e)
        report["fitness"] = -100.0 - 5.0 * len(leaks)
        return report

    task_ids = sorted(p.stem for p in PUBLIC.glob("*.json"))
    train_exact_names = {}  # name -> set(task_ids) for cross-task firing
    fitness = -5.0 * len(leaks)
    for tid in task_ids:
        pub = json.loads((PUBLIC / f"{tid}.json").read_text())
        train = pub["train"]
        test_inputs = [t["input"] for t in pub["test"]]
        try:
            cands = agent.propose(deepcopy(train)) or []
        except Exception as e:
            report["tasks"].append({"task_id": tid, "error": str(e)[:80], "train_exact": False})
            continue
        cand_diag = candidate_train_diagnostics(cands, train)
        shape_exact_names = [r["name"] for r in cand_diag if r["shape_exact"]]
        best_shape = min(
            (r for r in cand_diag if r["shape_exact"] and r["train_diff"] is not None),
            key=lambda r: r["train_diff"],
            default=None,
        )
        te = [(nm, t) for nm, t in cands if train_exact(t, train)]
        loo = False
        loo_names = []
        best = None
        for nm, t in te:
            train_exact_names.setdefault(nm, set()).add(tid)
            if informative_loo(agent.propose, train, required_name=nm):
                loo = True
                loo_names.append(nm)
            best = best or (nm, t)
        # PRIVATE readout (LOG ONLY, not in fitness)
        priv_match = None
        if best is not None and (PRIVATE / f"{tid}.json").exists():
            priv = json.loads((PRIVATE / f"{tid}.json").read_text())
            try:
                priv_match = all(equal(_call(best[1], deepcopy(ti)), po)
                                 for ti, po in zip(test_inputs, priv["test_outputs"]))
            except Exception:
                priv_match = False
        report["private_readout"][tid] = priv_match
        report["tasks"].append({"task_id": tid, "n_candidates": len(cands), "n_train_exact": len(te),
                                "train_exact_names": [nm for nm, _ in te][:5], "informative_loo": loo,
                                "informative_loo_names": loo_names[:5],
                                "n_shape_exact": len(shape_exact_names),
                                "shape_exact_names": shape_exact_names[:10],
                                "best_shape_train_diff": (
                                    {"name": best_shape["name"], "diff": best_shape["train_diff"],
                                     "per_pair_diff": best_shape["per_pair_diff"]}
                                    if best_shape else None
                                ),
                                "synthetic_color_perm": synthetic_color_perm(best[1], train) if best else None})
        if loo:
            fitness += 1.0
        elif te:
            fitness += 0.1
    # cross-task firing bonus
    for nm, tids in train_exact_names.items():
        if len(tids) >= 2:
            fitness += 0.5 * len(tids)
    report["fitness"] = round(fitness, 3)
    report["cross_task_firing"] = {nm: sorted(t) for nm, t in train_exact_names.items() if len(t) >= 2}
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="reference_agent.py")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rep = evaluate((HERE / args.agent) if not Path(args.agent).is_absolute() else Path(args.agent))
    if args.json:
        print(json.dumps(rep, indent=2))
        return
    print(f"FITNESS: {rep['fitness']}   (leakage hits: {len(rep['leakage_hits'])})")
    if rep.get("compile_error"):
        print("COMPILE ERROR:", rep["compile_error"])
    for t in rep["tasks"]:
        print(f"  {t['task_id']}: train_exact={t.get('n_train_exact', 0)} loo={t.get('informative_loo')} "
              f"shape_exact={t.get('n_shape_exact', 0)} best_shape={t.get('best_shape_train_diff')} "
              f"synth={t.get('synthetic_color_perm')} names={t.get('train_exact_names', [])}")
    print(f"cross-task firing >=2: {rep.get('cross_task_firing', {})}")
    print(f"PRIVATE readout (LOG ONLY, not in fitness): {rep['private_readout']}")
    if rep["leakage_hits"]:
        print("LEAKAGE HITS:", rep["leakage_hits"])


if __name__ == "__main__":
    main()
