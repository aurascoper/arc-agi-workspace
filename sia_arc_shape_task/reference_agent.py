"""Reference agent (SIA seed) for the ARC shape/decomposition task — SELF-CONTAINED, design-only.

Contract: propose(train) -> list[(name, transform)] where transform maps an input grid to an output grid,
learned from TRAIN PAIRS ONLY. SIA mutates THIS file (target_agent.py) across generations to add families;
the evaluator gates every proposal (train-exact + informative-LOO + synthetic + leakage). It never sees test
outputs. This seed carries a few shape-change families; SIA should add routing/serialization/object-summary
generators that re-derive their parameters per pair (so informative-LOO is non-vacuous).
"""

from __future__ import annotations

from collections import Counter


def _norm(g):
    return [[int(v) for v in row] for row in g]


def _dims(g):
    g = _norm(g)
    return (len(g), len(g[0]) if g else 0)


def _bg(g):
    g = _norm(g)
    return Counter(v for row in g for v in row).most_common(1)[0][0]


def _components(g):
    g = _norm(g)
    bg = _bg(g)
    H, W = _dims(g)
    seen = [[False] * W for _ in range(H)]
    objs = []
    for r in range(H):
        for c in range(W):
            if g[r][c] == bg or seen[r][c]:
                continue
            col = g[r][c]
            st = [(r, c)]
            seen[r][c] = True
            cells = []
            while st:
                rr, cc = st.pop()
                cells.append((rr, cc))
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = rr + dr, cc + dc
                    if 0 <= nr < H and 0 <= nc < W and not seen[nr][nc] and g[nr][nc] == col:
                        seen[nr][nc] = True
                        st.append((nr, nc))
            rs = [p[0] for p in cells]
            cs = [p[1] for p in cells]
            objs.append({"cells": cells, "color": col, "size": len(cells),
                         "bbox": (min(rs), min(cs), max(rs), max(cs))})
    return objs


def _crop(g, r0, c0, r1, c1):
    g = _norm(g)
    return [row[c0:c1 + 1] for row in g[r0:r1 + 1]]


# ------- families (each = (name, transform); included only if it reproduces train output SHAPE) -------
def _frame_interior(train):
    def pick(grid):
        objs = [o for o in _components(grid) if o["bbox"][2] - o["bbox"][0] >= 2 and o["bbox"][3] - o["bbox"][1] >= 2]
        return max(objs, key=lambda o: (o["bbox"][2] - o["bbox"][0]) * (o["bbox"][3] - o["bbox"][1])) if objs else None
    for p in train:
        o = pick(p["input"])
        if o is None:
            return None
        r0, c0, r1, c1 = o["bbox"]
        if _dims(_crop(p["input"], r0 + 1, c0 + 1, r1 - 1, c1 - 1)) != _dims(p["output"]):
            return None

    def t(grid):
        o = pick(grid)
        if o is None:
            return [[0]]
        r0, c0, r1, c1 = o["bbox"]
        return _crop(grid, r0 + 1, c0 + 1, r1 - 1, c1 - 1)
    return ("frame_interior_largest", t)


def _object_summary_row(train):
    def render(grid):
        objs = sorted(_components(grid), key=lambda o: (o["bbox"][0], o["bbox"][1]))
        return [[o["color"] for o in objs]] if objs else None
    for p in train:
        r = render(p["input"])
        if r is None or _dims(r) != _dims(p["output"]):
            return None
    return ("object_summary_row_reading", lambda grid: render(grid) or [[0]])


def propose(train):
    """Return [(name, transform)] learned from TRAIN ONLY."""
    out = []
    for fam in (_frame_interior, _object_summary_row):
        try:
            c = fam(train)
        except Exception:
            c = None
        if c is not None:
            out.append(c)
    return out
