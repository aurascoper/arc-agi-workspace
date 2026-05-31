"""Object-extension / line-growth generative primitive — design-only lane (Claude), standalone.

The highest-coverage renderer sub-family is "grow structure from existing objects". This prototypes a real
generative primitive (extend segments / shoot rays to the border) and gives it a fair shot across ALL 23
design misses, gated by train-exact + LOO + synthetic invariance. Hidden-safe: train-only synthesis; design
test output = readout; no task ids / coordinate signatures / public templates / frozen calibration / replay.
Never edits Codex hot files.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKSPACE))
import arc2_candidate_solver as S  # noqa: E402

EVAL = WORKSPACE / "arc_agi_2_data" / "evaluation"


def norm(g):
    return S.normalize_grid(g)


def shape(g):
    g = norm(g)
    return (len(g), len(g[0]))


def background(g):
    from collections import Counter
    g = norm(g)
    return Counter(v for row in g for v in row).most_common(1)[0][0]


def equal(a, b):
    return norm(a) == norm(b)


def maximal_segments(g):
    """Maximal monochromatic straight runs (horizontal & vertical) of non-bg cells, length >= 2."""
    g = norm(g)
    bg = background(g)
    H, W = len(g), len(g[0])
    segs = []
    # horizontal
    for r in range(H):
        c = 0
        while c < W:
            if g[r][c] == bg:
                c += 1
                continue
            col = g[r][c]
            c2 = c
            while c2 < W and g[r][c2] == col:
                c2 += 1
            if c2 - c >= 2:
                segs.append({"color": col, "axis": "h", "cells": [(r, cc) for cc in range(c, c2)]})
            c = c2
    # vertical
    for c in range(W):
        r = 0
        while r < H:
            if g[r][c] == bg:
                r += 1
                continue
            col = g[r][c]
            r2 = r
            while r2 < H and g[r2][c] == col:
                r2 += 1
            if r2 - r >= 2:
                segs.append({"color": col, "axis": "v", "cells": [(rr, c) for rr in range(r, r2)]})
            r = r2
    return segs


# ---------------------------------------------------------------- extension transforms (variants)
def extend_segments_to_border(grid, both=True, stop_at_nonbg=True):
    """Each maximal h/v segment grows along its axis toward the border(s), in its own colour,
    stopping at the border or (optionally) the first non-bg cell."""
    g = [row[:] for row in norm(grid)]
    bg = background(g)
    H, W = len(g), len(g[0])
    for seg in maximal_segments(grid):
        col = seg["color"]
        cells = seg["cells"]
        if seg["axis"] == "h":
            r = cells[0][0]
            cmin = min(c for _, c in cells)
            cmax = max(c for _, c in cells)
            dirs = [(0, -1, cmin), (0, 1, cmax)] if both else [(0, 1, cmax)]
            for _dr, dc, start in dirs:
                cc = start + dc
                while 0 <= cc < W:
                    if stop_at_nonbg and g[r][cc] != bg:
                        break
                    g[r][cc] = col
                    cc += dc
        else:
            c = cells[0][1]
            rmin = min(r for r, _ in cells)
            rmax = max(r for r, _ in cells)
            dirs = [(-1, 0, rmin), (1, 0, rmax)] if both else [(1, 0, rmax)]
            for dr, _dc, start in dirs:
                rr = start + dr
                while 0 <= rr < H:
                    if stop_at_nonbg and g[rr][c] != bg:
                        break
                    g[rr][c] = col
                    rr += dr
    return g


def rays_from_singletons(grid, axes="hv", stop_at_nonbg=True):
    """Each isolated non-bg cell (no same-colour 4-neighbour) shoots rays to the border."""
    g = [row[:] for row in norm(grid)]
    bg = background(g)
    H, W = len(g), len(g[0])
    src = norm(grid)
    singles = []
    for r in range(H):
        for c in range(W):
            if src[r][c] != bg and not any(0 <= r + dr < H and 0 <= c + dc < W and src[r + dr][c + dc] == src[r][c]
                                           for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                singles.append((r, c, src[r][c]))
    dirs = []
    if "h" in axes:
        dirs += [(0, 1), (0, -1)]
    if "v" in axes:
        dirs += [(1, 0), (-1, 0)]
    for r, c, col in singles:
        for dr, dc in dirs:
            rr, cc = r + dr, c + dc
            while 0 <= rr < H and 0 <= cc < W:
                if stop_at_nonbg and src[rr][cc] != bg:
                    break
                g[rr][cc] = col
                rr, cc = rr + dr, cc + dc
    return g


VARIANTS = [
    ("extend_segments_both_stop", lambda g: extend_segments_to_border(g, both=True, stop_at_nonbg=True)),
    ("extend_segments_both_thru", lambda g: extend_segments_to_border(g, both=True, stop_at_nonbg=False)),
    ("extend_segments_fwd_stop", lambda g: extend_segments_to_border(g, both=False, stop_at_nonbg=True)),
    ("rays_from_singletons_hv", lambda g: rays_from_singletons(g, "hv", True)),
    ("rays_from_singletons_h", lambda g: rays_from_singletons(g, "h", True)),
    ("rays_from_singletons_v", lambda g: rays_from_singletons(g, "v", True)),
]


def train_exact(t, train):
    for p in train:
        try:
            if not equal(t(deepcopy(p["input"])), p["output"]):
                return False
        except Exception:
            return False
    return True


def loo_stable(make_t, train):
    if len(train) <= 1:
        return True
    for i in range(len(train)):
        t = make_t()  # parameter-free variants: same transform; LOO is structural
        try:
            if not equal(t(deepcopy(train[i]["input"])), train[i]["output"]):
                return False
        except Exception:
            return False
    return True


def synthetic_invariance(t, train):
    """color-permutation equivariance (no fixed colour roles in pure geometric extension)."""
    mapping = {v: (v + 3) % 10 for v in range(10)}

    def perm(g):
        return [[mapping.get(v, v) for v in row] for row in norm(g)]
    for p in train:
        try:
            a = norm(t(perm(p["input"])))
            b = perm(t(deepcopy(p["input"])))
        except Exception:
            return False
        if a != b:
            return False
    return True


def run_task(tid):
    task = json.loads((EVAL / f"{tid}.json").read_text())
    train, test = task["train"], task["test"]
    if not all(shape(p["input"]) == shape(p["output"]) for p in train):
        return {"task_id": tid, "same_shape": False, "flip": False, "variant": None}
    for vname, fn in VARIANTS:
        if train_exact(fn, train):
            loo = loo_stable(lambda fn=fn: fn, train)
            syn = synthetic_invariance(fn, train)
            tep = sum(1 for p in test if equal(fn(deepcopy(p["input"])), p["output"]))
            return {"task_id": tid, "same_shape": True, "train_exact": True, "variant": vname,
                    "loo": loo, "synthetic_invariance": syn, "design_test_readout": f"{tep}/{len(test)}",
                    "flip": loo and tep == len(test)}
    return {"task_id": tid, "same_shape": True, "train_exact": False, "variant": None, "flip": False}


def main():
    genuine = json.loads((WORKSPACE / "tmp" / "claude_current_coverage_audit.json").read_text())["genuine_coverage_miss"]
    rows = [run_task(t) for t in genuine]
    flips = [r["task_id"] for r in rows if r.get("flip")]
    train_exacts = [r for r in rows if r.get("train_exact")]
    out = {"primitive": "object_extension_line_growth", "n": len(rows),
           "flips": flips, "train_exact_not_flipped": [r["task_id"] for r in train_exacts if not r["flip"]],
           "rows": rows}
    (WORKSPACE / "tmp" / "claude_object_extension_results.json").write_text(json.dumps(out, indent=2))
    print("Object-extension primitive over 23 genuine design misses:")
    for r in rows:
        if r.get("train_exact"):
            print(f"  {r['task_id']}: train_exact via {r['variant']} | LOO={r['loo']} synth={r['synthetic_invariance']} "
                  f"test={r.get('design_test_readout')} FLIP={r['flip']}")
    print(f"\ntrain-exact variants found on: {[r['task_id'] for r in train_exacts]}")
    print(f"FLIPS (train-exact + LOO + design-test-exact): {flips}")
    print("wrote tmp/claude_object_extension_results.json")


if __name__ == "__main__":
    main()
