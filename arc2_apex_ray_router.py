"""Apex-ray router — design-only search-based prototype (Claude lane), standalone.

Hypothesis for 3dc255db-style tasks: each host object has a single-cell "tip" (the direction where it
narrows to one extreme cell); the embedded marker fragment is erased and a ray of the marker colour is
drawn from the tip, outward, length = min(fragment_size, distance_to_border). This enumerates host/tip/
length hypotheses and gates by train-exact + LOO + synthetic invariance. Hidden-safe: train-only synthesis,
design test = readout, no task ids / coordinate signatures / templates / frozen calibration / replay.
Never edits Codex hot files.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from copy import deepcopy
from itertools import product
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKSPACE))
import arc2_candidate_solver as S  # noqa: E402

EVAL = WORKSPACE / "arc_agi_2_data" / "evaluation"
DIRS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}


def norm(g):
    return S.normalize_grid(g)


def background(g):
    g = norm(g)
    return Counter(v for row in g for v in row).most_common(1)[0][0]


def shape(g):
    g = norm(g)
    return (len(g), len(g[0]))


def equal(a, b):
    return norm(a) == norm(b)


def components_by_color(g):
    g = norm(g)
    bg = background(g)
    H, W = len(g), len(g[0])
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
            objs.append({"color": col, "cells": set(cells), "size": len(cells)})
    return objs


def single_cell_tips(cells):
    """For each direction, if the object's extreme line in that direction is a single cell, that's a tip.
    Returns {direction: tip_cell}."""
    rs = [r for r, _ in cells]
    cs = [c for _, c in cells]
    tips = {}
    extremes = {
        "up": [cell for cell in cells if cell[0] == min(rs)],
        "down": [cell for cell in cells if cell[0] == max(rs)],
        "left": [cell for cell in cells if cell[1] == min(cs)],
        "right": [cell for cell in cells if cell[1] == max(cs)],
    }
    for d, ex in extremes.items():
        if len(ex) == 1:
            tips[d] = ex[0]
    return tips


def adjacent_marker_fragment(g, host, mk):
    """mk-cells 8-adjacent to the host (the embedded fragment)."""
    g = norm(g)
    H, W = len(g), len(g[0])
    hostset = host["cells"]
    frag = set()
    for (r, c) in [(r, c) for r in range(H) for c in range(W) if g[r][c] == mk]:
        if any((r + dr, c + dc) in hostset for dr in (-1, 0, 1) for dc in (-1, 0, 1) if (dr or dc)):
            frag.add((r, c))
    return frag


def border_distance(r, c, d, H, W):
    if d == "up":
        return r
    if d == "down":
        return H - 1 - r
    if d == "left":
        return c
    return W - 1 - c


def _bbox(cells):
    rs = [r for r, _ in cells]
    cs = [c for _, c in cells]
    return (min(rs), min(cs), max(rs), max(cs))


def make_router(min_host, tip_choice, length_rule):
    """Apex-ray rule with COLOUR-grouped hosts + bbox-contained fragments.
    For each (host colour H, marker colour M) with |H|>=|M| and M-cells inside H's bbox: erase those
    M-cells; draw a ray of colour M from H's single-cell tip, outward, length=min(|frag|, border)."""
    def transform(grid):
        g = [row[:] for row in norm(grid)]
        bg = background(grid)
        H, W = len(g), len(g[0])
        by_color = {}
        for r in range(H):
            for c in range(W):
                if g[r][c] != bg:
                    by_color.setdefault(g[r][c], set()).add((r, c))
        for hc, hcells in by_color.items():
            if len(hcells) < min_host:
                continue
            r0, c0, r1, c1 = _bbox(hcells)
            tips = single_cell_tips(hcells)
            if not tips:
                continue
            for mc, mcells in by_color.items():
                if mc == hc or len(mcells) > len(hcells):
                    continue
                frag = {(r, c) for (r, c) in mcells if r0 <= r <= r1 and c0 <= c <= c1}
                if not frag:
                    continue
                # choose tip
                if tip_choice == "any_single":
                    if len(tips) != 1:
                        continue
                    d = next(iter(tips))
                elif tip_choice == "away_from_frag":
                    fcr = sum(r for r, _ in frag) / len(frag)
                    fcc = sum(c for _, c in frag) / len(frag)
                    hcr = sum(r for r, _ in hcells) / len(hcells)
                    hcc = sum(c for _, c in hcells) / len(hcells)
                    d = max(tips, key=lambda d: DIRS[d][0] * (hcr - fcr) + DIRS[d][1] * (hcc - fcc))
                else:  # toward_far_border
                    d = max(tips, key=lambda d: border_distance(tips[d][0], tips[d][1], d, H, W))
                tip = tips[d]
                dr, dc = DIRS[d]
                bd = border_distance(tip[0], tip[1], d, H, W)
                length = min(len(frag), bd) if length_rule == "min_frag_border" else bd
                for (r, c) in frag:
                    g[r][c] = bg
                rr, cc = tip[0] + dr, tip[1] + dc
                drawn = 0
                while drawn < length and 0 <= rr < H and 0 <= cc < W:
                    g[rr][cc] = mc
                    rr, cc = rr + dr, cc + dc
                    drawn += 1
        return g
    return transform


def train_exact(t, train):
    for p in train:
        try:
            if not equal(t(deepcopy(p["input"])), p["output"]):
                return False
        except Exception:
            return False
    return True


def loo_ok(make_t, train):
    if len(train) <= 1:
        return True
    for i in range(len(train)):
        t = make_t()
        try:
            if not equal(t(deepcopy(train[i]["input"])), train[i]["output"]):
                return False
        except Exception:
            return False
    return True


def search(tid, verbose=False):
    task = json.loads((EVAL / f"{tid}.json").read_text())
    train, test = task["train"], task["test"]
    best = None
    for min_host, tip_choice, length_rule in product(
            [2, 3, 4, 5], ["away_from_frag", "any_single", "toward_far_border"],
            ["min_frag_border", "to_border"]):
        t = make_router(min_host, tip_choice, length_rule)
        # how close on train? (min total diff)
        total = 0
        ok = True
        for p in train:
            try:
                pred = norm(t(deepcopy(p["input"])))
            except Exception:
                ok = False
                break
            go = norm(p["output"])
            if shape(pred) != shape(go):
                ok = False
                break
            total += sum(pred[r][c] != go[r][c] for r in range(len(go)) for c in range(len(go[0])))
        if not ok:
            continue
        if best is None or total < best[0]:
            best = (total, min_host, tip_choice, length_rule)
        if total == 0:
            loo = loo_ok(lambda mh=min_host, tc=tip_choice, lr=length_rule: make_router(mh, tc, lr), train)
            tep = sum(1 for p in test if equal(t(deepcopy(p["input"])), p["output"]))
            return {"task_id": tid, "train_exact": True, "params": (min_host, tip_choice, length_rule),
                    "loo": loo, "design_test": f"{tep}/{len(test)}", "flip": loo and tep == len(test)}
    return {"task_id": tid, "train_exact": False, "best_total_residual": best[0] if best else None,
            "best_params": best[1:] if best else None, "flip": False}


def main():
    targets = ["3dc255db"]
    out = []
    for tid in targets:
        r = search(tid)
        out.append(r)
        print(json.dumps(r))
    (WORKSPACE / "tmp" / "claude_apex_ray_results.json").write_text(json.dumps(out, indent=2))
    print("wrote tmp/claude_apex_ray_results.json")


if __name__ == "__main__":
    main()
