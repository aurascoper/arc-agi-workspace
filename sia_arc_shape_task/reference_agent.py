"""Reference agent (SIA seed) for the ARC shape/decomposition task — SELF-CONTAINED, design-only.

Contract: propose(train) -> list[(name, transform)] where transform maps an input grid to an output grid,
learned from TRAIN PAIRS ONLY. SIA mutates THIS file (target_agent.py) across generations; the evaluator
gates every proposal (train-exact + NAME-STABLE informative-LOO + synthetic + leakage), with the held-out
readout log-only. No test outputs are ever visible to the agent.

This seed carries a diverse, reusable family library so SIA has good genetic material to recombine: object
summaries, count canvases, non-bg / object / frame crops, panel selection, filler removal, integer downscale,
and a colour-histogram bar renderer. Each family is NAME-STABLE (propose() re-derives the same named family
on any subset whose train-output SHAPE it reproduces), so informative-LOO is meaningful. SIA should add
routing/serialization/relational families that likewise re-derive their parameters per pair.
"""

from __future__ import annotations

from collections import Counter


# ----------------------------------------------------------------- grid + object helpers (self-contained)
def _norm(g):
    return [[int(v) for v in row] for row in g]


def _dims(g):
    g = _norm(g)
    return (len(g), len(g[0]) if g else 0)


def _bg(g):
    g = _norm(g)
    return Counter(v for row in g for v in row).most_common(1)[0][0]


def _components(g, ignore_color=False):
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
                    if 0 <= nr < H and 0 <= nc < W and not seen[nr][nc] and (ignore_color or g[nr][nc] == col) and g[nr][nc] != bg:
                        seen[nr][nc] = True
                        st.append((nr, nc))
            rs = [p[0] for p in cells]
            cs = [p[1] for p in cells]
            colors = Counter(g[r2][c2] for r2, c2 in cells)
            objs.append({"cells": cells, "color": colors.most_common(1)[0][0], "size": len(cells),
                         "bbox": (min(rs), min(cs), max(rs), max(cs)), "colors": colors})
    return objs


def _crop(g, r0, c0, r1, c1):
    g = _norm(g)
    return [row[c0:c1 + 1] for row in g[r0:r1 + 1]]


def _nonbg_bbox(g):
    g = _norm(g)
    bg = _bg(g)
    cells = [(r, c) for r in range(len(g)) for c in range(len(g[0])) if g[r][c] != bg]
    if not cells:
        return None
    rs = [r for r, _ in cells]
    cs = [c for _, c in cells]
    return (min(rs), min(cs), max(rs), max(cs))


def _panels(g):
    g = _norm(g)
    H, W = _dims(g)
    sr = {r for r in range(H) if len(set(g[r])) == 1}
    sc = {c for c in range(W) if len({g[r][c] for r in range(H)}) == 1}

    def bands(n, seps):
        out, i = [], 0
        while i < n:
            if i in seps:
                i += 1
                continue
            j = i
            while j < n and j not in seps:
                j += 1
            out.append((i, j - 1))
            i = j
        return out
    rb, cb = bands(H, sr), bands(W, sc)
    if len(rb) * len(cb) < 2:
        return []
    return [(r0, c0, r1, c1) for (r0, r1) in rb for (c0, c1) in cb]


# ----------------------------------------------------------------- family library (factories)
# A factory returns (name, transform) iff the transform reproduces every train output SHAPE; else None.
def _shape_ok(t, train):
    try:
        return all(_dims(t(p["input"])) == _dims(p["output"]) for p in train)
    except Exception:
        return False


def _wrap(name, t, train):
    return (name, t) if _shape_ok(t, train) else None


def f_object_summary(train):
    out = []
    for axis in ("row", "col"):
        for order in ("reading", "size", "color"):
            for ic in (False, True):
                def t(g, order=order, axis=axis, ic=ic):
                    objs = _components(g, ignore_color=ic)
                    if order == "reading":
                        objs.sort(key=lambda o: (o["bbox"][0], o["bbox"][1]))
                    elif order == "size":
                        objs.sort(key=lambda o: -o["size"])
                    else:
                        objs.sort(key=lambda o: o["color"])
                    cols = [o["color"] for o in objs] or [0]
                    return [cols] if axis == "row" else [[c] for c in cols]
                w = _wrap(f"object_summary:{axis}:{order}:{'multi' if ic else 'mono'}", t, train)
                if w:
                    out.append(w)
    return out


def f_count_canvas(train):
    def t(g):
        n = len(_components(g))
        b = _bg(g)
        return [[b] * n] if n else [[b]]
    return [w] if (w := _wrap("count_canvas:row_bg", t, train)) else []


def f_color_histogram_bar(train):
    # one row per non-bg colour; bar length = rank by cell-count; pad with the most-frequent (filler) colour
    def t(g):
        gg = _norm(g)
        b = _bg(gg)
        cc = Counter(v for row in gg for v in row if v != b)
        if not cc:
            return [[b]]
        # filler = colour with the most connected components (scattered), else most cells
        comp_count = Counter(o["color"] for o in _components(gg))
        filler = comp_count.most_common(1)[0][0]
        data = [c for c in cc if c != filler]
        data.sort(key=lambda c: cc[c])  # ascending count -> rank
        width = len(data)
        rows = []
        for i, col in enumerate(data, start=1):
            rows.append([col] * i + [filler] * (width - i))
        return rows or [[b]]
    return [w] if (w := _wrap("color_histogram_bar:rank", t, train)) else []


def f_nonbg_bbox_crop(train):
    def t(g):
        bb = _nonbg_bbox(g)
        return _crop(g, *bb) if bb else [[0]]
    return [w] if (w := _wrap("nonbg_bbox_crop", t, train)) else []


def f_object_crop(train):
    out = []
    for role in ("largest", "smallest", "unique_color"):
        def t(g, role=role):
            objs = _components(g)
            if not objs:
                return [[0]]
            if role == "largest":
                o = max(objs, key=lambda o: o["size"])
            elif role == "smallest":
                o = min(objs, key=lambda o: o["size"])
            else:
                cc = Counter(o["color"] for o in objs)
                uni = [o for o in objs if cc[o["color"]] == 1]
                if len(uni) != 1:
                    return [[0]]
                o = uni[0]
            return _crop(g, *o["bbox"])
        w = _wrap(f"object_crop:{role}", t, train)
        if w:
            out.append(w)
    return out


def f_frame_interior(train):
    def t(g):
        objs = [o for o in _components(g) if o["bbox"][2] - o["bbox"][0] >= 2 and o["bbox"][3] - o["bbox"][1] >= 2]
        if not objs:
            return [[0]]
        o = max(objs, key=lambda o: (o["bbox"][2] - o["bbox"][0]) * (o["bbox"][3] - o["bbox"][1]))
        r0, c0, r1, c1 = o["bbox"]
        return _crop(g, r0 + 1, c0 + 1, r1 - 1, c1 - 1)
    return [w] if (w := _wrap("frame_interior:largest", t, train)) else []


def f_panel_select(train):
    out = []
    for role in ("unique_content", "largest", "most_nonbg"):
        def t(g, role=role):
            ps = _panels(g)
            if len(ps) < 2:
                return [[0]]
            crops = [(_crop(g, *p), p) for p in ps]
            if role == "unique_content":
                keys = [tuple(map(tuple, c)) for c, _ in crops]
                cc = Counter(keys)
                uni = [crops[i][0] for i, k in enumerate(keys) if cc[k] == 1]
                return uni[0] if len(uni) == 1 else [[0]]
            if role == "largest":
                return max(crops, key=lambda cp: len(cp[0]) * len(cp[0][0]))[0]
            b = _bg(g)
            return max(crops, key=lambda cp: sum(v != b for row in cp[0] for v in row))[0]
        w = _wrap(f"panel_select:{role}", t, train)
        if w:
            out.append(w)
    return out


def f_filler_removal(train):
    out = []
    for mode in ("dup", "bg"):
        def t(g, mode=mode):
            gg = _norm(g)
            b = _bg(gg)

            def keep(rows):
                res, prev = [], None
                for r in rows:
                    if mode == "bg" and all(v == b for v in r):
                        continue
                    if mode == "dup" and prev is not None and r == prev:
                        continue
                    res.append(r)
                    prev = r
                return res
            g2 = keep(gg) or [[b]]
            cols = [[g2[r][c] for r in range(len(g2))] for c in range(len(g2[0]))]
            c2 = keep(cols) or [[b]]
            return [[c2[c][r] for c in range(len(c2))] for r in range(len(c2[0]))]
        w = _wrap(f"filler_removal:{mode}", t, train)
        if w:
            out.append(w)
    return out


def f_downscale(train):
    facs = set()
    for p in train:
        ih, iw = _dims(p["input"])
        oh, ow = _dims(p["output"])
        if oh == 0 or ow == 0 or ih % oh or iw % ow:
            return []
        facs.add((ih // oh, iw // ow))
    if len(facs) != 1 or next(iter(facs)) == (1, 1):
        return []
    kh, kw = next(iter(facs))

    def t(g, kh=kh, kw=kw):
        gg = _norm(g)
        H, W = len(gg), len(gg[0])
        return [[Counter(gg[r + i][c + j] for i in range(kh) for j in range(kw)).most_common(1)[0][0]
                 for c in range(0, W, kw)] for r in range(0, H, kh)]
    return [w] if (w := _wrap(f"downscale:{kh}x{kw}", t, train)) else []


FAMILIES = [f_object_summary, f_count_canvas, f_color_histogram_bar, f_nonbg_bbox_crop,
            f_object_crop, f_frame_interior, f_panel_select, f_filler_removal, f_downscale]


def propose(train):
    """Return [(name, transform)] learned from TRAIN ONLY. Name-stable across subsets."""
    out = []
    for fam in FAMILIES:
        try:
            out.extend(fam(train) or [])
        except Exception:
            continue
    return out
