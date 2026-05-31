"""Sketch renderer / end-to-end search engine — design-only lane (Claude), on the object-graph IR.

Connects the pipeline: object_graph (parse) -> typed sketch enumerator (priors) -> EXECUTOR LIBRARY (fills
holes, renders) -> uniform gate. Exposes propose(train) -> [(name, transform)] (same contract as the SIA
agent, so this doubles as a strong seed) and a harness that runs the 23 design misses with name-stable
informative-LOO + design-test readout (log only) + failure locus. Reuses existing executors where clean.
Design-only; train-only synthesis; no task ids / templates / test-output use; never edits Codex hot files.

Run: python3 arc2_sketch_renderer.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKSPACE))
import arc2_object_graph as OG  # noqa: E402
import arc2_shape_decomposition_synth as SD  # noqa: E402 (reuse shape/decomp factories)
import arc2_apex_ray_router as AR  # noqa: E402 (reuse apex-ray executor)
import arc2_typed_sketch_enumerator as SK  # noqa: E402 (priors)

EVAL = Path(os.environ.get("ARC2_EVAL_DIR", WORKSPACE / "arc_agi_2_data" / "evaluation"))


def norm(g):
    return OG.norm(g)


def dims(g):
    return OG.dims(g)


def equal(a, b):
    return norm(a) == norm(b)


# ===================================================================== executor library
# Each executor: train -> list[(name, transform)]   (candidates whose transform is at least train-shape-valid)
def ex_shape_decomp(train):
    out = []
    for fname, variants in SD.FAMILIES.items():
        for i, factory in enumerate(variants):
            try:
                t = factory(train)
            except Exception:
                t = None
            if t is not None:
                out.append((f"shape_decomp:{fname}:{i}", t))
    return out


def ex_marker_host(train):
    """apex-ray (marker_host_action: erase fragment + ray from host tip) under a small parameter ladder."""
    out = []
    for mh in (2, 3):
        for tip in ("away_from_frag", "any_single"):
            for lr in ("min_frag_border", "to_border"):
                t = AR.make_router(mh, tip, lr)
                out.append((f"apex_ray:{mh}:{tip}:{lr}", t))
    return out


def ex_route_connect(train):
    """Connect pairs of same-colour singleton markers sharing a row/col with a straight line."""
    def t(grid):
        g = [row[:] for row in norm(grid)]
        H, W = len(g), len(g[0])
        bg = OG.background(grid)
        singles = {}
        for r in range(H):
            for c in range(W):
                if g[r][c] != bg and not any(0 <= r + dr < H and 0 <= c + dc < W and g[r + dr][c + dc] == g[r][c]
                                             for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    singles.setdefault(g[r][c], []).append((r, c))
        for col, pts in singles.items():
            for i in range(len(pts)):
                for j in range(i + 1, len(pts)):
                    (r1, c1), (r2, c2) = pts[i], pts[j]
                    if r1 == r2:
                        for c in range(min(c1, c2) + 1, max(c1, c2)):
                            if g[r1][c] == bg:
                                g[r1][c] = col
                    elif c1 == c2:
                        for r in range(min(r1, r2) + 1, max(r1, r2)):
                            if g[r][c1] == bg:
                                g[r][c1] = col
        return g
    return [("route_connect:same_color_rowcol", t)]


def ex_select_transform(train):
    """Output = a whole-grid D4/transpose transform (when it reproduces train output shape)."""
    forms = {
        "rot90": lambda g: [list(r) for r in zip(*g[::-1])],
        "rot180": lambda g: [row[::-1] for row in g[::-1]],
        "rot270": lambda g: [list(r) for r in zip(*g)][::-1],
        "mirror_h": lambda g: [row[::-1] for row in g],
        "mirror_v": lambda g: g[::-1],
        "transpose": lambda g: [list(r) for r in zip(*g)],
    }
    out = []
    for name, fn in forms.items():
        def t(grid, fn=fn):
            return fn(norm(grid))
        if all(dims(t(p["input"])) == dims(p["output"]) for p in train):
            out.append((f"d4:{name}", t))
    return out


def ex_recolor_by_group(train):
    """Recolour each object by a learned (size-rank -> colour) map; same shape only."""
    def factory(tr):
        cmap = {}
        for p in tr:
            if dims(p["input"]) != dims(p["output"]):
                return None
            gi, go = norm(p["input"]), norm(p["output"])
            objs = OG.cc_by_color(gi)
            sizes = sorted({o.size for o in objs}, reverse=True)
            rank = {s: i for i, s in enumerate(sizes)}
            recon = [row[:] for row in gi]
            for o in objs:
                outvals = {go[r][c] for r, c in o.cells}
                if len(outvals) != 1:
                    return None
                nc = next(iter(outvals))
                key = min(rank[o.size], 5)
                if key in cmap and cmap[key] != nc:
                    return None
                cmap[key] = nc
                for r, c in o.cells:
                    recon[r][c] = nc
            if recon != go:
                return None

        def t(grid, cmap=dict(cmap)):
            g = norm(grid)
            out = [row[:] for row in g]
            objs = OG.cc_by_color(grid)
            sizes = sorted({o.size for o in objs}, reverse=True)
            rank = {s: i for i, s in enumerate(sizes)}
            for o in objs:
                key = min(rank[o.size], 5)
                if key in cmap:
                    for r, c in o.cells:
                        out[r][c] = cmap[key]
            return out
        return t
    t = factory(train)
    return [("recolor_by_size_rank", t)] if t is not None else []


EXECUTORS = [ex_shape_decomp, ex_marker_host, ex_route_connect, ex_select_transform, ex_recolor_by_group]


def propose(train):
    """Aggregate executor candidates -> [(name, transform)]. Same contract as the SIA agent (usable as seed)."""
    out = []
    for ex in EXECUTORS:
        try:
            out.extend(ex(train) or [])
        except Exception:
            continue
    return out


# ===================================================================== gate harness
def train_exact(t, train):
    try:
        return all(equal(t(deepcopy(p["input"])), p["output"]) for p in train)
    except Exception:
        return False


def _stable_repr(v):
    if isinstance(v, (str, int, float, bool, type(None))):
        return repr(v)
    if isinstance(v, (tuple, list)):
        return "[" + ",".join(_stable_repr(x) for x in v[:20]) + (",..." if len(v) > 20 else "") + "]"
    if isinstance(v, dict):
        items = sorted(v.items(), key=lambda kv: repr(kv[0]))[:20]
        return "{" + ",".join(f"{_stable_repr(k)}:{_stable_repr(val)}" for k, val in items) + "}"
    return f"<{type(v).__name__}>"


def transform_fingerprint(t):
    code = getattr(t, "__code__", None)
    closure = []
    for cell in getattr(t, "__closure__", None) or []:
        try:
            closure.append(_stable_repr(cell.cell_contents))
        except ValueError:
            closure.append("<empty>")
    if code is None:
        return {"callable": type(t).__name__, "repr": repr(t)}
    return {
        "code": code.co_code.hex(),
        "consts": _stable_repr(code.co_consts),
        "names": list(code.co_names),
        "defaults": _stable_repr(getattr(t, "__defaults__", None)),
        "closure": closure,
    }


def loo_evidence(name, train, full_transform=None):
    """Same-name LOO plus a non-vacuity check for fold-varying/refit transforms."""
    out = {"passes": False, "informative": False, "admission_type": "loo_fail"}
    if len(train) <= 1:
        return out
    full_fp = transform_fingerprint(full_transform) if full_transform is not None else None
    fold_fps = []
    for i in range(len(train)):
        sub = [train[j] for j in range(len(train)) if j != i]
        held = train[i]
        cands = {nm: t for nm, t in propose(sub)}
        t = cands.get(name)
        if t is None:
            return False
        try:
            if not equal(t(deepcopy(held["input"])), held["output"]):
                return out
            fold_fps.append(transform_fingerprint(t))
        except Exception:
            return out
    fp_strings = {json.dumps(fp, sort_keys=True) for fp in fold_fps}
    if full_fp is not None:
        fp_strings.add(json.dumps(full_fp, sort_keys=True))
    varies = len(fp_strings) > 1
    out.update({"passes": True, "informative": varies,
                "admission_type": "informative_loo" if varies else "train_exact_fixed_loo_vacuous"})
    return out


def informative_loo(name, train):
    return loo_evidence(name, train)["informative"]


def synthetic_color_perm(t, train):
    m = {v: (v + 3) % 10 for v in range(10)}
    perm = lambda g: [[m.get(v, v) for v in row] for row in norm(g)]
    try:
        return all(norm(t(perm(p["input"]))) == perm(norm(t(deepcopy(p["input"])))) for p in train)
    except Exception:
        return False


def run_task(tid):
    task = json.loads((EVAL / f"{tid}.json").read_text())
    train, test = task["train"], task["test"]
    cands = propose(train)
    te = [(nm, t) for nm, t in cands if train_exact(t, train)]
    out = {"task_id": tid, "n_candidates": len(cands), "n_train_exact": len(te),
           "train_exact_names": [nm for nm, _ in te][:6]}
    flip = False
    if te:
        nm, t = te[0]
        loo_ev = loo_evidence(nm, train, full_transform=t)
        loo = loo_ev["informative"]
        syn = synthetic_color_perm(t, train)
        tep = sum(1 for p in test if equal(t(deepcopy(p["input"])), p["output"]))  # readout only
        flip = loo and tep == len(test)
        out.update({"best": nm, "same_name_loo": loo_ev["passes"], "informative_loo": loo,
                    "loo_admission_type": loo_ev["admission_type"], "synthetic": syn,
                    "design_test": f"{tep}/{len(test)}", "flip": flip})
        out["failure_locus"] = "NONE (flip)" if flip else (
            "train-exact + informative-LOO but design-test-fail" if loo else loo_ev["admission_type"])
    else:
        out.update({"best": None, "flip": False,
                    "failure_locus": "no train-exact candidate from the executor library"})
    return out


def main():
    audit = WORKSPACE / "tmp" / "claude_current_coverage_audit.json"
    tasks = json.loads(audit.read_text())["genuine_coverage_miss"] if audit.exists() \
        else [p.stem for p in sorted(EVAL.glob("*.json"))][:23]
    rows = [run_task(t) for t in tasks]
    flips = [r["task_id"] for r in rows if r.get("flip")]
    te_tasks = [r for r in rows if r["n_train_exact"]]
    # cross-task firing of candidate names
    name_tasks = Counter()
    for r in rows:
        for nm in r["train_exact_names"]:
            name_tasks[nm] += 1
    out = {"lane": "sketch_renderer", "flips": flips,
           "train_exact_tasks": [r["task_id"] for r in te_tasks],
           "cross_task_firing": {nm: n for nm, n in name_tasks.items() if n >= 2}, "rows": rows}
    (WORKSPACE / "tmp" / "claude_sketch_renderer_results.json").write_text(json.dumps(out, indent=2))
    print("End-to-end sketch renderer over 23 design misses:\n")
    for r in rows:
        tag = (f"train_exact={r['n_train_exact']} best={r.get('best')} loo={r.get('informative_loo')} "
               f"loo_type={r.get('loo_admission_type')} "
               f"test={r.get('design_test')} flip={r.get('flip')}" if r["n_train_exact"] else "no train-exact")
        print(f"  {r['task_id']}: cands={r['n_candidates']:2} {tag}")
    print(f"\ntasks with a train-exact candidate: {[r['task_id'] for r in te_tasks]}")
    print(f"cross-task firing >=2: {out['cross_task_firing']}")
    print(f"FLIPS (train-exact + informative-LOO + design-test): {flips}")
    print("wrote tmp/claude_sketch_renderer_results.json")


if __name__ == "__main__":
    main()
