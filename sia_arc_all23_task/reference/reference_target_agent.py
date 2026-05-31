"""Strong SIA seed agent — SELF-CONTAINED full executor library (Claude lane).

Drop-in `target_agent.py` for SIA: `propose(train) -> list[(name, transform)]`, learned from TRAIN ONLY.
Bundles the whole design-only executor library (object parsing + shape/decomposition families + apex-ray
marker-host + route_connect + D4 select-transform + recolor-by-role) with ZERO workspace imports, so SIA can
mutate it in isolation and start from strong, diverse genetic material. No task-id dispatch, no hardcoded
templates, no held-out-split reads, no output replay. Learning from the train pairs is the only signal used.

This is the self-contained twin of arc2_sketch_renderer.propose(); use it to seed an all-23 SIA task.
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


# ----------------------------------------------------------------- grid + object helpers
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
                for dr, dc in N4:
                    nr, nc = rr + dr, cc + dc
                    if 0 <= nr < H and 0 <= nc < W and not seen[nr][nc] and g[nr][nc] != bg and (ignore_color or g[nr][nc] == col):
                        seen[nr][nc] = True
                        st.append((nr, nc))
            rs = [p[0] for p in cells]
            cs = [p[1] for p in cells]
            objs.append({"cells": cells, "color": Counter(g[r2][c2] for r2, c2 in cells).most_common(1)[0][0],
                         "size": len(cells), "bbox": (min(rs), min(cs), max(rs), max(cs))})
    return objs


def _crop(g, r0, c0, r1, c1):
    g = _norm(g)
    return [row[c0:c1 + 1] for row in g[r0:r1 + 1]]


def _nonbg_bbox(g):
    g = _norm(g)
    bg = _bg(g)
    cs = [(r, c) for r in range(len(g)) for c in range(len(g[0])) if g[r][c] != bg]
    if not cs:
        return None
    rs = [p[0] for p in cs]
    cc = [p[1] for p in cs]
    return (min(rs), min(cc), max(rs), max(cc))


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
    return [(r0, c0, r1, c1) for (r0, r1) in rb for (c0, c1) in cb] if len(rb) * len(cb) >= 2 else []


def _shape_ok(t, train):
    try:
        return all(_dims(t(p["input"])) == _dims(p["output"]) for p in train)
    except Exception:
        return False


def _wrap(name, t, train):
    return [(name, t)] if _shape_ok(t, train) else []


# ----------------------------------------------------------------- shape/decomposition families
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
                out += _wrap(f"object_summary:{axis}:{order}:{'multi' if ic else 'mono'}", t, train)
    return out


def f_nonbg_bbox_crop(train):
    def t(g):
        bb = _nonbg_bbox(g)
        return _crop(g, *bb) if bb else [[0]]
    return _wrap("nonbg_bbox_crop", t, train)


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
        out += _wrap(f"object_crop:{role}", t, train)
    return out


def f_frame_interior(train):
    def t(g):
        objs = [o for o in _components(g) if o["bbox"][2] - o["bbox"][0] >= 2 and o["bbox"][3] - o["bbox"][1] >= 2]
        if not objs:
            return [[0]]
        o = max(objs, key=lambda o: (o["bbox"][2] - o["bbox"][0]) * (o["bbox"][3] - o["bbox"][1]))
        r0, c0, r1, c1 = o["bbox"]
        return _crop(g, r0 + 1, c0 + 1, r1 - 1, c1 - 1)
    return _wrap("frame_interior:largest", t, train)


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
        out += _wrap(f"panel_select:{role}", t, train)
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
    return _wrap(f"downscale:{kh}x{kw}", t, train)


# ----------------------------------------------------------------- same-shape executors
def f_apex_ray(train):
    """marker-host: erase bbox-contained marker fragment; draw marker-colour ray from host single-cell tip."""
    DIRS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}

    def tips(cells):
        rs = [r for r, _ in cells]
        cs = [c for _, c in cells]
        ex = {"up": [x for x in cells if x[0] == min(rs)], "down": [x for x in cells if x[0] == max(rs)],
              "left": [x for x in cells if x[1] == min(cs)], "right": [x for x in cells if x[1] == max(cs)]}
        return {d: e[0] for d, e in ex.items() if len(e) == 1}

    def make(min_host, tip_choice, length_rule):
        def t(grid):
            g = [row[:] for row in _norm(grid)]
            bg = _bg(grid)
            H, W = len(g), len(g[0])
            by = {}
            for r in range(H):
                for c in range(W):
                    if g[r][c] != bg:
                        by.setdefault(g[r][c], set()).add((r, c))
            for hc, hcells in by.items():
                if len(hcells) < min_host:
                    continue
                rs = [r for r, _ in hcells]
                cs = [c for _, c in hcells]
                r0, c0, r1, c1 = min(rs), min(cs), max(rs), max(cs)
                tp = tips(hcells)
                if not tp:
                    continue
                for mc, mcells in by.items():
                    if mc == hc or len(mcells) > len(hcells):
                        continue
                    frag = {(r, c) for (r, c) in mcells if r0 <= r <= r1 and c0 <= c <= c1}
                    if not frag:
                        continue
                    if tip_choice == "any_single":
                        if len(tp) != 1:
                            continue
                        d = next(iter(tp))
                    else:
                        fr = sum(r for r, _ in frag) / len(frag)
                        fcc = sum(c for _, c in frag) / len(frag)
                        hr = sum(r for r, _ in hcells) / len(hcells)
                        hcx = sum(c for _, c in hcells) / len(hcells)
                        d = max(tp, key=lambda d: DIRS[d][0] * (hr - fr) + DIRS[d][1] * (hcx - fcc))
                    tip = tp[d]
                    dr, dc = DIRS[d]
                    bd = {"up": tip[0], "down": H - 1 - tip[0], "left": tip[1], "right": W - 1 - tip[1]}[d]
                    length = min(len(frag), bd) if length_rule == "min_frag_border" else bd
                    for (r, c) in frag:
                        g[r][c] = bg
                    rr, cc = tip[0] + dr, tip[1] + dc
                    n = 0
                    while n < length and 0 <= rr < H and 0 <= cc < W:
                        g[rr][cc] = mc
                        rr, cc, n = rr + dr, cc + dc, n + 1
            return g
        return t
    out = []
    for mh in (2, 3):
        for tc in ("away_from_frag", "any_single"):
            for lr in ("min_frag_border", "to_border"):
                out.append((f"apex_ray:{mh}:{tc}:{lr}", make(mh, tc, lr)))
    return out


def f_route_connect(train):
    def t(grid):
        g = [row[:] for row in _norm(grid)]
        H, W = len(g), len(g[0])
        bg = _bg(grid)
        singles = {}
        for r in range(H):
            for c in range(W):
                if g[r][c] != bg and not any(0 <= r + dr < H and 0 <= c + dc < W and g[r + dr][c + dc] == g[r][c] for dr, dc in N4):
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


def f_component_gap_bridge(train):
    """Renderer seed: bridge aligned same-colour components across background gaps."""
    out = []

    def make(mode):
        def t(grid):
            g = [row[:] for row in _norm(grid)]
            H, W = _dims(g)
            bg = _bg(g)
            objs_by_color = {}
            for o in _components(g):
                objs_by_color.setdefault(o["color"], []).append(o)

            def clear_row(r, c0, c1):
                return all(g[r][c] == bg for c in range(c0, c1 + 1))

            def clear_col(c, r0, r1):
                return all(g[r][c] == bg for r in range(r0, r1 + 1))

            for col, objs in objs_by_color.items():
                for i in range(len(objs)):
                    r0a, c0a, r1a, c1a = objs[i]["bbox"]
                    for j in range(i + 1, len(objs)):
                        r0b, c0b, r1b, c1b = objs[j]["bbox"]
                        row_overlap = max(r0a, r0b) <= min(r1a, r1b)
                        col_overlap = max(c0a, c0b) <= min(c1a, c1b)
                        if mode in ("rowcol", "row") and row_overlap and c1a < c0b - 1:
                            r = (max(r0a, r0b) + min(r1a, r1b)) // 2
                            if clear_row(r, c1a + 1, c0b - 1):
                                for c in range(c1a + 1, c0b):
                                    g[r][c] = col
                        if mode in ("rowcol", "row") and row_overlap and c1b < c0a - 1:
                            r = (max(r0a, r0b) + min(r1a, r1b)) // 2
                            if clear_row(r, c1b + 1, c0a - 1):
                                for c in range(c1b + 1, c0a):
                                    g[r][c] = col
                        if mode in ("rowcol", "col") and col_overlap and r1a < r0b - 1:
                            c = (max(c0a, c0b) + min(c1a, c1b)) // 2
                            if clear_col(c, r1a + 1, r0b - 1):
                                for r in range(r1a + 1, r0b):
                                    g[r][c] = col
                        if mode in ("rowcol", "col") and col_overlap and r1b < r0a - 1:
                            c = (max(c0a, c0b) + min(c1a, c1b)) // 2
                            if clear_col(c, r1b + 1, r0a - 1):
                                for r in range(r1b + 1, r0a):
                                    g[r][c] = col
            return g
        return t

    for mode in ("rowcol", "row", "col"):
        out.append((f"component_gap_bridge:{mode}", make(mode)))
    return out


def f_symmetry_complete(train):
    """Renderer seed: complete missing background cells from simple grid symmetries."""
    out = []

    def make(mode):
        def counterpart(r, c, H, W):
            if mode == "mirror_h":
                return r, W - 1 - c
            if mode == "mirror_v":
                return H - 1 - r, c
            return H - 1 - r, W - 1 - c

        def t(grid):
            src = _norm(grid)
            H, W = _dims(src)
            bg = _bg(src)
            g = [row[:] for row in src]
            for r in range(H):
                for c in range(W):
                    rr, cc = counterpart(r, c, H, W)
                    if g[r][c] == bg and src[rr][cc] != bg:
                        g[r][c] = src[rr][cc]
            return g
        return t

    for mode in ("mirror_h", "mirror_v", "rot180"):
        out.append((f"symmetry_complete:{mode}", make(mode)))
    return out


def f_enclosed_region_fill(train):
    """Renderer seed: fill enclosed background regions from their boundary colour."""
    out = []

    def make(strategy):
        def t(grid):
            g = [row[:] for row in _norm(grid)]
            H, W = _dims(g)
            bg = _bg(g)
            seen = [[False] * W for _ in range(H)]
            for sr in range(H):
                for sc in range(W):
                    if seen[sr][sc] or g[sr][sc] != bg:
                        continue
                    stack = [(sr, sc)]
                    seen[sr][sc] = True
                    region = []
                    boundary = []
                    touches_edge = False
                    while stack:
                        r, c = stack.pop()
                        region.append((r, c))
                        if r in (0, H - 1) or c in (0, W - 1):
                            touches_edge = True
                        for dr, dc in N4:
                            nr, nc = r + dr, c + dc
                            if not (0 <= nr < H and 0 <= nc < W):
                                continue
                            if g[nr][nc] == bg and not seen[nr][nc]:
                                seen[nr][nc] = True
                                stack.append((nr, nc))
                            elif g[nr][nc] != bg:
                                boundary.append(g[nr][nc])
                    if touches_edge or not boundary:
                        continue
                    counts = Counter(boundary)
                    if strategy == "unique" and len(counts) != 1:
                        continue
                    fill = counts.most_common(1)[0][0]
                    for r, c in region:
                        g[r][c] = fill
            return g
        return t

    for strategy in ("unique", "majority"):
        out.append((f"enclosed_region_fill:{strategy}", make(strategy)))
    return out


def f_singleton_rays(train):
    """Renderer seed: draw rays from singleton markers through background cells."""
    out = []
    dirs = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}

    def make(direction):
        def t(grid):
            g = [row[:] for row in _norm(grid)]
            H, W = _dims(g)
            bg = _bg(g)
            comps = _components(g)
            singles = [o for o in comps if o["size"] == 1]
            use_dirs = dirs.items() if direction == "all" else [(direction, dirs[direction])]
            for o in singles:
                (r, c) = o["cells"][0]
                for _, (dr, dc) in use_dirs:
                    rr, cc = r + dr, c + dc
                    while 0 <= rr < H and 0 <= cc < W and g[rr][cc] == bg:
                        g[rr][cc] = o["color"]
                        rr += dr
                        cc += dc
            return g
        return t

    for direction in ("up", "down", "left", "right", "all"):
        out.append((f"singleton_rays:{direction}", make(direction)))
    return out


def f_d4(train):
    forms = {"rot90": lambda g: [list(r) for r in zip(*g[::-1])],
             "rot180": lambda g: [row[::-1] for row in g[::-1]],
             "rot270": lambda g: [list(r) for r in zip(*g)][::-1],
             "mirror_h": lambda g: [row[::-1] for row in g],
             "mirror_v": lambda g: g[::-1],
             "transpose": lambda g: [list(r) for r in zip(*g)]}
    out = []
    for name, fn in forms.items():
        out += _wrap(f"d4:{name}", lambda g, fn=fn: fn(_norm(g)), train)
    return out


def f_recolor_by_size_rank(train):
    cmap = {}
    for p in train:
        if _dims(p["input"]) != _dims(p["output"]):
            return []
        gi, go = _norm(p["input"]), _norm(p["output"])
        objs = _components(gi)
        sizes = sorted({o["size"] for o in objs}, reverse=True)
        rank = {s: i for i, s in enumerate(sizes)}
        recon = [row[:] for row in gi]
        for o in objs:
            outvals = {go[r][c] for r, c in o["cells"]}
            if len(outvals) != 1:
                return []
            nc = next(iter(outvals))
            k = min(rank[o["size"]], 5)
            if k in cmap and cmap[k] != nc:
                return []
            cmap[k] = nc
            for r, c in o["cells"]:
                recon[r][c] = nc
        if recon != go:
            return []

    def t(grid, cmap=dict(cmap)):
        g = _norm(grid)
        out = [row[:] for row in g]
        objs = _components(grid)
        sizes = sorted({o["size"] for o in objs}, reverse=True)
        rank = {s: i for i, s in enumerate(sizes)}
        for o in objs:
            k = min(rank[o["size"]], 5)
            if k in cmap:
                for r, c in o["cells"]:
                    out[r][c] = cmap[k]
        return out
    return [("recolor_by_size_rank", t)]


FAMILIES = [f_object_summary, f_nonbg_bbox_crop, f_object_crop, f_frame_interior, f_panel_select, f_downscale,
            f_apex_ray, f_route_connect, f_component_gap_bridge, f_symmetry_complete, f_enclosed_region_fill,
            f_singleton_rays, f_d4, f_recolor_by_size_rank]


def propose(train):
    out = []
    for fam in FAMILIES:
        try:
            out.extend(fam(train) or [])
        except Exception:
            continue
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset_dir", required=True)
    ap.add_argument("--working_dir", required=True)
    args = ap.parse_args()
    dataset_dir = Path(args.dataset_dir).resolve()
    working_dir = Path(args.working_dir).resolve()
    tasks = sorted(p.stem for p in dataset_dir.glob("*.json"))
    log = {
        "status": "ok",
        "message": "Strong seed reference agent ready; evaluator imports propose(train).",
        "dataset_dir": str(dataset_dir),
        "working_dir": str(working_dir),
        "n_public_tasks": len(tasks),
        "public_tasks": tasks,
    }
    (working_dir / "agent_execution.json").write_text(json.dumps(log, indent=2))
    try:
        shutil.copyfile(Path(__file__).resolve(), working_dir / "candidate_agent.py")
    except OSError:
        pass
    print(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
