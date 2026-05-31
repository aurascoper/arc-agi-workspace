"""Object-role structured operators — design-only research lane (Claude).

Replaces per-cell repair (falsified under LOO) with OBJECT-level rewrites whose role predicate is a
function of object features (size, color, holes, rank, uniqueness, ...) — never task ids, templates,
coordinates, or test outputs. Two pre-registered mechanisms:

  keep_remove_by_role : output = input with objects whose role-predicate is False erased to background
  recolor_by_role     : output = input with each object repainted by a learned (feature -> colour) map

Gate = train_exact (by construction when a consistent rule exists) + leave-one-out (LOO) at object
granularity. LOO is the real evidence: a held-out pair's objects must be classified correctly by the
rule fit on the other pairs. Frozen calibration is never touched; design test output is a readout only.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from copy import deepcopy
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKSPACE))
import run_pseudo_private_eval as RP  # noqa: E402
import arc2_candidate_solver as S  # noqa: E402

EVAL = WORKSPACE / "arc_agi_2_data" / "evaluation"


def norm(g):
    return S.normalize_grid(g)


def shape(g):
    g = norm(g)
    return (len(g), len(g[0]))


def background(g):
    g = norm(g)
    return Counter(v for row in g for v in row).most_common(1)[0][0]


def components(g, bg):
    """4-connected, single-colour objects (non-background). Returns list of dicts."""
    g = norm(g)
    H, W = shape(g)
    seen = [[False] * W for _ in range(H)]
    objs = []
    for r in range(H):
        for c in range(W):
            if g[r][c] == bg or seen[r][c]:
                continue
            col = g[r][c]
            stack = [(r, c)]
            seen[r][c] = True
            cells = []
            while stack:
                rr, cc = stack.pop()
                cells.append((rr, cc))
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = rr + dr, cc + dc
                    if 0 <= nr < H and 0 <= nc < W and not seen[nr][nc] and g[nr][nc] == col:
                        seen[nr][nc] = True
                        stack.append((nr, nc))
            rs = [p[0] for p in cells]
            cs = [p[1] for p in cells]
            objs.append({"cells": cells, "color": col, "size": len(cells),
                         "bbox": (min(rs), min(cs), max(rs), max(cs)),
                         "h": max(rs) - min(rs) + 1, "w": max(cs) - min(cs) + 1,
                         "touches_border": any(rr in (0, H - 1) or cc in (0, W - 1) for rr, cc in cells)})
    # derived features
    sizes = sorted({o["size"] for o in objs}, reverse=True)
    size_rank = {s: i + 1 for i, s in enumerate(sizes)}
    colorcount = Counter(o["color"] for o in objs)
    sizecount = Counter(o["size"] for o in objs)
    for o in objs:
        o["size_rank"] = min(size_rank[o["size"]], 6)
        o["is_largest"] = int(o["size"] == sizes[0]) if sizes else 0
        o["is_smallest"] = int(o["size"] == sizes[-1]) if sizes else 0
        o["unique_color"] = int(colorcount[o["color"]] == 1)
        o["unique_size"] = int(sizecount[o["size"]] == 1)
    return objs


# object-feature accessors used as role separators (categorical, translation-invariant)
ROLE_FEATURES = {
    "color": lambda o: o["color"],
    "size_rank": lambda o: o["size_rank"],
    "is_largest": lambda o: o["is_largest"],
    "is_smallest": lambda o: o["is_smallest"],
    "unique_color": lambda o: o["unique_color"],
    "unique_size": lambda o: o["unique_size"],
    "touches_border": lambda o: o["touches_border"],
    "size": lambda o: o["size"],
}


def erase(g, obj, bg):
    g = [row[:] for row in norm(g)]
    for r, c in obj["cells"]:
        g[r][c] = bg
    return g


def label_keep_remove(gi, go, bg):
    """Per input object: 'keep' (unchanged in output), 'remove' (all cells -> bg), or None (other)."""
    go = norm(go)
    objs = components(gi, bg)
    labels = []
    for o in objs:
        vals_out = {go[r][c] for r, c in o["cells"]}
        if vals_out == {o["color"]}:
            labels.append((o, "keep"))
        elif vals_out == {bg}:
            labels.append((o, "remove"))
        else:
            return objs, None  # not a pure keep/remove task
    # output must equal input with removed objects erased (no other changes)
    return objs, labels


def fit_keep_remove(train, feature_name):
    """Learn 'keep iff feature in kept_values'. Returns transform or None if inconsistent."""
    feat = ROLE_FEATURES[feature_name]
    value_label = {}
    for p in train:
        bg = background(p["input"])
        # require output = input with some objects erased (same shape, output nonbg subset of input)
        if shape(p["input"]) != shape(p["output"]):
            return None
        objs, labels = label_keep_remove(p["input"], p["output"], bg)
        if labels is None:
            return None
        # verify exact reconstruction by erasing 'remove' objects
        recon = [row[:] for row in norm(p["input"])]
        for o, lab in labels:
            if lab == "remove":
                for r, c in o["cells"]:
                    recon[r][c] = bg
        if recon != norm(p["output"]):
            return None
        for o, lab in labels:
            v = feat(o)
            if v in value_label and value_label[v] != lab:
                return None  # this feature does not separate keep vs remove
            value_label[v] = lab
    kept_values = {v for v, lab in value_label.items() if lab == "keep"}

    def transform(grid, feat=feat, kept=frozenset(kept_values), value_label=dict(value_label)):
        g = norm(grid)
        bg = background(g)
        out = [row[:] for row in g]
        for o in components(g, bg):
            v = feat(o)
            keep = (v in kept) if v in value_label else True  # unseen -> default keep (conservative)
            if not keep:
                for r, c in o["cells"]:
                    out[r][c] = bg
        return out

    return transform


def fit_recolor(train, feature_name):
    """Learn 'object of feature value v -> colour map[v]'. Same shape; objects keep cells, change colour."""
    feat = ROLE_FEATURES[feature_name]
    cmap = {}
    for p in train:
        if shape(p["input"]) != shape(p["output"]):
            return None
        bg = background(p["input"])
        go = norm(p["output"])
        objs = components(p["input"], bg)
        # every non-bg output cell must be covered by an input object (no new cells, no erasures)
        recon = [row[:] for row in norm(p["input"])]
        for o in objs:
            outvals = {go[r][c] for r, c in o["cells"]}
            if len(outvals) != 1:
                return None  # object not uniformly recoloured
            nc = next(iter(outvals))
            v = feat(o)
            if v in cmap and cmap[v] != nc:
                return None
            cmap[v] = nc
            for r, c in o["cells"]:
                recon[r][c] = nc
        if recon != go:
            return None  # background or non-object cells changed -> not pure recolour

    def transform(grid, feat=feat, cmap=dict(cmap)):
        g = norm(grid)
        bg = background(g)
        out = [row[:] for row in g]
        for o in components(g, bg):
            v = feat(o)
            if v in cmap:
                for r, c in o["cells"]:
                    out[r][c] = cmap[v]
        return out

    return transform


MECHANISMS = {
    "keep_remove_by_role": (fit_keep_remove, list(ROLE_FEATURES)),
    "recolor_by_role": (fit_recolor, list(ROLE_FEATURES)),
}


def loo_object_rule(train, fitter, feature_name):
    def factory(subset):
        return fitter(subset, feature_name)
    return S.leave_one_out_validates(train, factory)


def evaluate_task(tid):
    task = json.loads((EVAL / f"{tid}.json").read_text())
    train, test = task["train"], task["test"]
    result = {"task_id": tid, "mechanisms": {}}
    any_flip = False
    flip_via = None
    for mech, (fitter, features) in MECHANISMS.items():
        promoted = None
        for fname in features:  # bounded ladder = the feature set (stop-after-non-improving is trivial here)
            t = fitter(train, fname)
            if t is None:
                continue
            train_exact, _ = S.train_transform_score(t, train)
            if not train_exact:
                continue
            loo = loo_object_rule(train, fitter, fname)
            if loo:
                promoted = (fname, t)
                break
        flip = False
        if promoted is not None:
            _, t = promoted
            tep = 0
            for p in test:  # readout only
                try:
                    if norm(t(deepcopy(p["input"]))) == norm(p["output"]):
                        tep += 1
                except Exception:
                    pass
            flip = tep == len(test)
        result["mechanisms"][mech] = {
            "promoted_feature": promoted[0] if promoted else None,
            "train_exact_loo": promoted is not None,
            "flip_to_exact": flip,
        }
        if flip:
            any_flip = True
            flip_via = flip_via or f"{mech}:{promoted[0]}"
    result["flip_to_exact"] = any_flip
    result["flip_via"] = flip_via
    return result


def main():
    audit = json.loads((WORKSPACE / "tmp" / "claude_current_coverage_audit.json").read_text())
    genuine = audit["genuine_coverage_miss"]
    rows = []
    t0 = time.time()
    for tid in genuine:
        r = evaluate_task(tid)
        rows.append(r)
        kr = r["mechanisms"]["keep_remove_by_role"]
        rc = r["mechanisms"]["recolor_by_role"]
        print(f"  {tid}: keep_remove[{kr['promoted_feature'] or '-'}|exact_loo={kr['train_exact_loo']}] "
              f"recolor[{rc['promoted_feature'] or '-'}|exact_loo={rc['train_exact_loo']}] flip={r['flip_to_exact']} {r['flip_via'] or ''}")
    flips = [r for r in rows if r["flip_to_exact"]]
    promoted_kr = [r["task_id"] for r in rows if r["mechanisms"]["keep_remove_by_role"]["train_exact_loo"]]
    promoted_rc = [r["task_id"] for r in rows if r["mechanisms"]["recolor_by_role"]["train_exact_loo"]]
    out = {
        "n_genuine": len(genuine),
        "flips_to_exact": [r["task_id"] for r in flips],
        "n_flips": len(flips),
        "promoted_train_exact_loo": {"keep_remove_by_role": promoted_kr, "recolor_by_role": promoted_rc},
        "rows": rows,
        "wall_time_sec": round(time.time() - t0, 1),
    }
    (WORKSPACE / "tmp" / "claude_object_role_results.json").write_text(json.dumps(out, indent=2))
    print(f"\nflips-to-exact: {out['n_flips']}/{len(genuine)} -> {out['flips_to_exact']}")
    print(f"train_exact+LOO promoted (keep_remove): {promoted_kr}")
    print(f"train_exact+LOO promoted (recolor):     {promoted_rc}")
    print(f"wrote tmp/claude_object_role_results.json ({out['wall_time_sec']}s)")


if __name__ == "__main__":
    main()
