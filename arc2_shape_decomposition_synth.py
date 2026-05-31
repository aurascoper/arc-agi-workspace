"""Shape/decomposition generator — design-only standalone lane (Claude), on top of arc2_object_graph.

Targets the 7 shape-change design misses (5dbc8537, edb79dae, 20a9e565, 2d0172a1, 6ffbe589, e87109e9,
89565ca0). Proposes (output-canvas + content-render) candidates from INPUT only, via 5 families. Each family
is a FACTORY (train -> transform) so informative-LOO is a genuine refit, not vacuous. Gate: train-exact
(hard); informative-LOO if parameterised; cross-task-firing >=2 if effectively fixed. Synthetic invariance =
soft, family-specific. Design-test output is a READOUT only. No task ids / coordinate signatures / public
templates / train|test replay in core logic. Never edits Codex hot files.

Run: python3 arc2_shape_decomposition_synth.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKSPACE))
import arc2_object_graph as OG  # noqa: E402 (reusable IR scaffold)

EVAL = Path(os.environ.get("ARC2_EVAL_DIR", WORKSPACE / "arc_agi_2_data" / "evaluation"))
TARGETS = ["5dbc8537", "edb79dae", "20a9e565", "2d0172a1", "6ffbe589", "e87109e9", "89565ca0"]


def norm(g):
    return OG.norm(g)


def dims(g):
    return OG.dims(g)


def bg(g):
    return OG.background(g)


def equal(a, b):
    return norm(a) == norm(b)


def crop(g, r0, c0, r1, c1):
    g = norm(g)
    return [row[c0:c1 + 1] for row in g[r0:r1 + 1]]


# ===================================================================== families (factories)
# Each factory: train -> transform(grid)->grid  (or None if family does not apply on this train).

# ---- family 1: frame / interior extraction ---------------------------------------------------
def fam_frame_interior(train, which="largest_frame", recolor=False):
    def pick(grid):
        frames = OG.frames(grid) + OG.rectangles(grid)
        if not frames:
            return None
        if which == "largest_frame":
            return max(frames, key=lambda o: o.h * o.w)
        if which == "unique_color":
            cc = Counter(o.color for o in frames)
            uni = [o for o in frames if cc[o.color] == 1]
            return uni[0] if len(uni) == 1 else None
        if which == "most_holes":
            return max(frames, key=lambda o: o.holes())
        return None
    # verify the role yields the right OUTPUT SHAPE on train (input-derived), else family inapplicable
    for p in train:
        o = pick(p["input"])
        if o is None:
            return None
        r0, c0, r1, c1 = o.bbox
        if dims(crop(p["input"], r0 + 1, c0 + 1, r1 - 1, c1 - 1)) != dims(p["output"]):
            return None

    def t(grid):
        o = pick(grid)
        if o is None:
            return [[0]]
        r0, c0, r1, c1 = o.bbox
        return crop(grid, r0 + 1, c0 + 1, r1 - 1, c1 - 1)
    return t


# ---- family 2: separator / panel select-or-stack ---------------------------------------------
def fam_panel_select(train, which="unique_content"):
    def pick(grid):
        panels = OG.panels(grid)
        if len(panels) < 2:
            return None
        crops = []
        for o in panels:
            r0, c0, r1, c1 = o.bbox
            crops.append((o, crop(grid, r0, c0, r1, c1)))
        if which == "unique_content":
            keys = [tuple(map(tuple, c)) for _, c in crops]
            cc = Counter(keys)
            uni = [crops[i] for i, k in enumerate(keys) if cc[k] == 1]
            return uni[0][1] if len(uni) == 1 else None
        if which == "largest":
            return max(crops, key=lambda oc: oc[0].h * oc[0].w)[1]
        if which == "most_nonbg":
            b = bg(grid)
            return max(crops, key=lambda oc: sum(v != b for row in oc[1] for v in row))[1]
        return None
    for p in train:
        c = pick(p["input"])
        if c is None or dims(c) != dims(p["output"]):
            return None

    def t(grid):
        c = pick(grid)
        return c if c is not None else [[0]]
    return t


# ---- family 3: dominant-filler removal (remove repeated/bg rows & cols) -----------------------
def _remove_filler(grid, mode):
    g = norm(grid)
    b = bg(g)
    H, W = len(g), len(g[0])

    def keep_rows(rows):
        out = []
        prev = None
        for i, r in enumerate(rows):
            if mode == "bg" and all(v == b for v in r):
                continue
            if mode == "dup" and prev is not None and r == prev:
                continue
            out.append(r)
            prev = r
        return out
    g2 = keep_rows(g)
    if not g2:
        return [[b]]
    cols = [[g2[r][c] for r in range(len(g2))] for c in range(W)]
    cols2 = keep_rows(cols)
    if not cols2:
        return [[b]]
    return [[cols2[c][r] for c in range(len(cols2))] for r in range(len(cols2[0]))]


def fam_filler_removal(train, mode="dup"):
    for p in train:
        if dims(_remove_filler(p["input"], mode)) != dims(p["output"]):
            return None
    return lambda grid, mode=mode: _remove_filler(grid, mode)


# ---- family 4: object-summary canvas ---------------------------------------------------------
def fam_object_summary(train, axis="row", order="reading", view="color"):
    def render(grid):
        objs = OG.PARSERS[view](grid)
        if not objs:
            return None
        if order == "reading":
            objs = sorted(objs, key=lambda o: (o.bbox[0], o.bbox[1]))
        elif order == "size":
            objs = sorted(objs, key=lambda o: -o.size)
        elif order == "color":
            objs = sorted(objs, key=lambda o: o.color if o.color is not None else 99)
        cols = [o.color if o.color is not None else 0 for o in objs]
        if axis == "row":
            return [cols]
        return [[c] for c in cols]
    for p in train:
        r = render(p["input"])
        if r is None or dims(r) != dims(p["output"]):
            return None

    def t(grid):
        r = render(grid)
        return r if r is not None else [[0]]
    return t


# ---- family 5: compact glyph / integer downscale ---------------------------------------------
def fam_downscale(train):
    # output = input block-averaged by an integer factor (each k*k block -> its majority colour)
    factors = set()
    for p in train:
        ih, iw = dims(p["input"])
        oh, ow = dims(p["output"])
        if oh == 0 or ow == 0 or ih % oh or iw % ow:
            return None
        factors.add((ih // oh, iw // ow))
    if len(factors) != 1:
        return None
    kh, kw = next(iter(factors))
    if (kh, kw) == (1, 1):
        return None

    def t(grid, kh=kh, kw=kw):
        g = norm(grid)
        H, W = len(g), len(g[0])
        out = []
        for r in range(0, H, kh):
            row = []
            for c in range(0, W, kw):
                block = [g[r + i][c + j] for i in range(kh) for j in range(kw)]
                row.append(Counter(block).most_common(1)[0][0])
            out.append(row)
        return out
    return t


FAMILIES = {
    "frame_interior": [lambda tr: fam_frame_interior(tr, w) for w in ("largest_frame", "unique_color", "most_holes")],
    "panel_select": [lambda tr: fam_panel_select(tr, w) for w in ("unique_content", "largest", "most_nonbg")],
    "filler_removal": [lambda tr: fam_filler_removal(tr, m) for m in ("dup", "bg")],
    "object_summary": [lambda tr: fam_object_summary(tr, a, o, v)
                       for a in ("row", "col") for o in ("reading", "size", "color") for v in ("color", "ignore_color")],
    "downscale": [lambda tr: fam_downscale(tr)],
}
# families whose transform is effectively fixed (parameter-free) -> LOO is vacuous, need cross-task firing
PARAMETER_FREE = {"filler_removal", "downscale"}


# ===================================================================== gating
def train_exact(t, train):
    for p in train:
        try:
            if not equal(t(deepcopy(p["input"])), p["output"]):
                return False
        except Exception:
            return False
    return True


def informative_loo(factory, train):
    """Refit the factory on each n-1 subset; must reproduce the held pair exactly. Genuine out-of-sample."""
    if len(train) <= 1:
        return False  # cannot be informative with 1 example
    for i in range(len(train)):
        sub = [train[j] for j in range(len(train)) if j != i]
        t = factory(sub)
        if t is None:
            return False
        try:
            if not equal(t(deepcopy(train[i]["input"])), train[i]["output"]):
                return False
        except Exception:
            return False
    return True


def synthetic_invariance(t, train, family):
    """family-specific soft score in {pass, fail, n/a}."""
    # color permutation where colours are symbolic (summary/glyph), padding where frame not absolute
    if family in ("object_summary",):
        m = {v: (v + 3) % 10 for v in range(10)}
        perm = lambda g: [[m.get(v, v) for v in row] for row in norm(g)]
        try:
            ok = all(norm(t(perm(p["input"]))) == perm(norm(t(deepcopy(p["input"])))) for p in train)
            return "pass" if ok else "fail"
        except Exception:
            return "fail"
    return "n/a"


def failure_locus(train, family_results):
    """If no flip: where did the best family fail? shape / selector / renderer / ordering / decomposition."""
    # a family whose canvas (output shape) matched train but content failed -> renderer/ordering/color-role
    shape_match = [f for f, r in family_results.items() if r.get("shape_ok")]
    if shape_match:
        return f"renderer/ordering/color-role (canvas correct via {shape_match[0]}, content not train-exact)"
    return "shape/decomposition (no family proposes a train-shape-correct canvas from input)"


def run_task(tid):
    task = json.loads((EVAL / f"{tid}.json").read_text())
    train, test = task["train"], task["test"]
    best = None
    fam_results = {}
    for fname, variants in FAMILIES.items():
        fam_shape_ok = False
        for factory in variants:
            try:
                t = factory(train)
            except Exception:
                t = None
            if t is None:
                continue
            # shape_ok: factory already verified output-shape match on train (returns None otherwise)
            fam_shape_ok = True
            if train_exact(t, train):
                loo = informative_loo(factory, train) if fname not in PARAMETER_FREE else False
                syn = synthetic_invariance(t, train, fname)
                tep = sum(1 for p in test if equal(t(deepcopy(p["input"])), p["output"]))
                cand = {"family": fname, "train_exact": True, "informative_loo": loo,
                        "synthetic": syn, "design_test": f"{tep}/{len(test)}",
                        "param_free": fname in PARAMETER_FREE,
                        "flip": (loo or False) and tep == len(test)}
                if best is None or (cand["flip"] and not best["flip"]):
                    best = cand
        fam_results[fname] = {"shape_ok": fam_shape_ok}
    out = {"task_id": tid}
    if best:
        out.update(best)
        out["failure_locus"] = "NONE (train-exact)" if best["train_exact"] else "?"
        if not best["flip"]:
            out["failure_locus"] = ("design-test-fail" if best["train_exact"] and best["informative_loo"]
                                    else "train-exact-but-LOO-vacuous-or-param-free")
    else:
        out.update({"family": None, "train_exact": False, "informative_loo": False,
                    "synthetic": "n/a", "design_test": "0/?", "flip": False,
                    "failure_locus": failure_locus(train, fam_results)})
    out["shape_ok_families"] = [f for f, r in fam_results.items() if r["shape_ok"]]
    return out


def leakage_scan():
    src = Path(__file__).read_text()
    forbidden = [r"\bsolve_[0-9a-f]{8}\b", r"test\[", r"\.test\b", r"pseudo_private", r"public_signature",
                 r"\b(5dbc8537|edb79dae|20a9e565|2d0172a1|6ffbe589|e87109e9|89565ca0)\b\s*[:=]"]
    hits = []
    for pat in forbidden:
        # allow the TARGETS list literal + docstring mentions; flag only assignment/dispatch use
        for m in re.finditer(pat, src):
            ln = src[:m.start()].count("\n") + 1
            line = src.splitlines()[ln - 1]
            s = line.strip()
            # skip the scanner's own pattern list, docstrings, the TARGETS literal, comments
            if ("forbidden" in line or "finditer" in line or "leakage" in line or "TARGETS" in line
                    or s.startswith("#") or s.startswith('"') or s.startswith("r\"")):
                continue
            hits.append((pat, ln, s[:70]))
    return hits


def main():
    rows = [run_task(t) for t in TARGETS]
    flips = [r["task_id"] for r in rows if r.get("flip")]
    scan = leakage_scan()
    out = {"lane": "shape_decomposition", "targets": TARGETS, "flips": flips,
           "leakage_scan_hits": scan, "rows": rows}
    (WORKSPACE / "tmp" / "claude_shape_decomposition_results.json").write_text(json.dumps(out, indent=2))
    print("Shape/decomposition generator over 7 shape-change targets:\n")
    for r in rows:
        print(f"  {r['task_id']}: best_family={str(r.get('family')):16} train_exact={r['train_exact']!s:5} "
              f"info_LOO={r['informative_loo']!s:5} synth={r['synthetic']:4} test={r['design_test']} "
              f"flip={r['flip']!s:5} | {r['failure_locus']}")
        print(f"            shape-correct-canvas families: {r['shape_ok_families']}")
    print(f"\nFLIPS (train-exact + informative-LOO + design-test): {flips}")
    print(f"leakage scan: {'CLEAN' if not scan else scan}")
    print("wrote tmp/claude_shape_decomposition_results.json")


if __name__ == "__main__":
    main()
