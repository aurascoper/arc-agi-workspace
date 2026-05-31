"""Object-graph IR + parser bank — standalone reusable scaffold (Claude lane).

Hours 0-12 of the research report's prototype: lift grids into multiple object views and a typed relation
graph, so downstream stages (shape/decomposition prediction, sketch search, routing/redraw) reason over
named entities and relations rather than raw pixels. Pure Python/NumPy-free (lists only); deterministic;
no task ids / templates / test-output use; never edits Codex hot files. Reusable by Claude and Codex.

Public API:
    parse_views(grid) -> {view_name: [Obj]}                  # the parser bank
    build_object_graph(grid, view="color") -> ObjectGraph    # objects + typed relations
    shape_profile(train) -> dict                             # input/output shape relations (decomp stage)

Run: python3 arc2_object_graph.py            # validates by parsing the 23 design misses
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
EVAL = Path(os.environ.get("ARC2_EVAL_DIR", WORKSPACE / "arc_agi_2_data" / "evaluation"))

Cell = tuple[int, int]
Grid = list[list[int]]
N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
N8 = N4 + ((1, 1), (1, -1), (-1, 1), (-1, -1))


# ----------------------------------------------------------------- grid utilities
def norm(g) -> Grid:
    if hasattr(g, "tolist"):
        g = g.tolist()
    return [[int(v) for v in row] for row in g]


def dims(g) -> tuple[int, int]:
    g = norm(g)
    return (len(g), len(g[0]) if g else 0)


def background(g) -> int:
    g = norm(g)
    return Counter(v for row in g for v in row).most_common(1)[0][0]


# ----------------------------------------------------------------- object type
@dataclass
class Obj:
    id: int
    cells: frozenset
    colors: Counter            # colour histogram over the object's cells
    bbox: tuple                # (r0, c0, r1, c1)
    view: str                  # which parser produced it
    kind: str = "object"       # object | rectangle | frame | line | panel | hole | bg_island

    @property
    def size(self) -> int:
        return len(self.cells)

    @property
    def color(self):           # dominant colour (None if multi-colour)
        mc = self.colors.most_common()
        return mc[0][0] if len(mc) == 1 else (mc[0][0] if mc[0][1] > sum(n for _, n in mc[1:]) else None)

    @property
    def h(self) -> int:
        return self.bbox[2] - self.bbox[0] + 1

    @property
    def w(self) -> int:
        return self.bbox[3] - self.bbox[1] + 1

    @property
    def centroid(self) -> tuple:
        rs = [r for r, _ in self.cells]
        cs = [c for _, c in self.cells]
        return (sum(rs) / len(rs), sum(cs) / len(cs))

    def touches_border(self, H, W) -> bool:
        return any(r in (0, H - 1) or c in (0, W - 1) for r, c in self.cells)

    @property
    def is_rect_solid(self) -> bool:
        return self.size == self.h * self.w

    @property
    def is_frame(self) -> bool:
        r0, c0, r1, c1 = self.bbox
        if self.h < 2 or self.w < 2:
            return False
        perim = {(r, c) for r in (r0, r1) for c in range(c0, c1 + 1)} | \
                {(r, c) for c in (c0, c1) for r in range(r0, r1 + 1)}
        return self.cells == frozenset(perim)

    @property
    def is_line(self) -> bool:
        return self.h == 1 or self.w == 1

    def holes(self) -> int:
        """Background-coloured 4-conn regions fully enclosed inside the object's bbox."""
        r0, c0, r1, c1 = self.bbox
        inside = {(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)} - self.cells
        seen = set()
        holes = 0
        for cell in inside:
            if cell in seen:
                continue
            stack = [cell]
            seen.add(cell)
            comp = []
            touches_edge = False
            while stack:
                r, c = stack.pop()
                comp.append((r, c))
                if r in (r0, r1) or c in (c0, c1):
                    touches_edge = True
                for dr, dc in N4:
                    nb = (r + dr, c + dc)
                    if nb in inside and nb not in seen:
                        seen.add(nb)
                        stack.append(nb)
            if not touches_edge:
                holes += 1
        return holes

    def normalized(self) -> frozenset:
        r0, c0, _, _ = self.bbox
        return frozenset((r - r0, c - c0) for r, c in self.cells)


def _components(grid, cell_ok, same, conn=N4):
    """Generic flood-fill: cell_ok(r,c) gates membership; same(a,b) joins neighbours."""
    g = norm(grid)
    H, W = dims(g)
    seen = [[False] * W for _ in range(H)]
    comps = []
    for r in range(H):
        for c in range(W):
            if seen[r][c] or not cell_ok(r, c):
                continue
            stack = [(r, c)]
            seen[r][c] = True
            cells = []
            while stack:
                rr, cc = stack.pop()
                cells.append((rr, cc))
                for dr, dc in conn:
                    nr, nc = rr + dr, cc + dc
                    if 0 <= nr < H and 0 <= nc < W and not seen[nr][nc] and cell_ok(nr, nc) and same((rr, cc), (nr, nc)):
                        seen[nr][nc] = True
                        stack.append((nr, nc))
            comps.append(cells)
    return comps


def _mk(cells, grid, view, kind="object", counter=None):
    g = norm(grid)
    rs = [r for r, _ in cells]
    cs = [c for _, c in cells]
    colors = Counter(g[r][c] for r, c in cells)
    if counter is None:
        counter = [0]
    o = Obj(counter[0], frozenset(cells), colors, (min(rs), min(cs), max(rs), max(cs)), view, kind)
    counter[0] += 1
    return o


# ----------------------------------------------------------------- the parser bank
def cc_by_color(grid, conn=N4):
    """4-connected single-colour non-background components."""
    g = norm(grid)
    bg = background(g)
    counter = [0]
    return [_mk(cells, g, "color", counter=counter) for cells in
            _components(g, lambda r, c: g[r][c] != bg, lambda a, b: g[a[0]][a[1]] == g[b[0]][b[1]], conn)]


def cc_ignore_color(grid, conn=N4):
    """Multi-colour objects: 4-connected non-background regions regardless of colour."""
    g = norm(grid)
    bg = background(g)
    counter = [0]
    return [_mk(cells, g, "ignore_color", counter=counter) for cells in
            _components(g, lambda r, c: g[r][c] != bg, lambda a, b: True, conn)]


def rectangles(grid):
    return [o for o in cc_by_color(grid) if o.is_rect_solid and o.h >= 2 and o.w >= 2]


def frames(grid):
    out = []
    for o in cc_by_color(grid):
        if o.is_frame:
            o.kind = "frame"
            out.append(o)
    return out


def line_segments(grid):
    """Maximal monochromatic straight runs (h, v, both diagonals), length >= 2."""
    g = norm(grid)
    bg = background(g)
    H, W = dims(g)
    out = []
    counter = [0]
    def run(cells_iter):
        run_cells = []
        prev = None
        for (r, c) in cells_iter:
            col = g[r][c]
            if col == bg:
                prev = None
                if len(run_cells) >= 2:
                    out.append(_mk(run_cells, g, "line", "line", counter))
                run_cells = []
                continue
            if prev is not None and col != prev:
                if len(run_cells) >= 2:
                    out.append(_mk(run_cells, g, "line", "line", counter))
                run_cells = []
            run_cells.append((r, c))
            prev = col
        if len(run_cells) >= 2:
            out.append(_mk(run_cells, g, "line", "line", counter))
    for r in range(H):
        run([(r, c) for c in range(W)])
    for c in range(W):
        run([(r, c) for r in range(H)])
    for d in range(-(W - 1), H):
        run([(r, r - d) for r in range(H) if 0 <= r - d < W])
    for s in range(H + W - 1):
        run([(r, s - r) for r in range(H) if 0 <= s - r < W])
    return out


def holes(grid):
    """Enclosed background regions (not touching the grid border)."""
    g = norm(grid)
    bg = background(g)
    H, W = dims(g)
    comps = _components(g, lambda r, c: g[r][c] == bg, lambda a, b: True)
    out = []
    counter = [0]
    for cells in comps:
        if not any(r in (0, H - 1) or c in (0, W - 1) for r, c in cells):
            out.append(_mk(cells, g, "hole", "hole", counter))
    return out


def background_islands(grid):
    """Connected background regions (any, including border-touching)."""
    g = norm(grid)
    bg = background(g)
    counter = [0]
    return [_mk(cells, g, "bg_island", "bg_island", counter) for cells in
            _components(g, lambda r, c: g[r][c] == bg, lambda a, b: True)]


def panels(grid):
    """Regions separated by full-length monochromatic separator rows/columns."""
    g = norm(grid)
    H, W = dims(g)
    sep_rows = [r for r in range(H) if len(set(g[r])) == 1]
    sep_cols = [c for c in range(W) if len({g[r][c] for r in range(H)}) == 1]
    if not sep_rows and not sep_cols:
        return []
    sep_rs = set(sep_rows)
    sep_cs = set(sep_cols)
    # contiguous non-separator row/col bands
    def bands(n, seps):
        out = []
        i = 0
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
    rbands = bands(H, sep_rs)
    cbands = bands(W, sep_cs)
    out = []
    counter = [0]
    for (r0, r1) in rbands:
        for (c0, c1) in cbands:
            cells = [(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]
            out.append(_mk(cells, g, "panel", "panel", counter))
    return out if len(out) >= 2 else []


PARSERS = {
    "color": cc_by_color, "ignore_color": cc_ignore_color, "rectangles": rectangles,
    "frames": frames, "lines": line_segments, "holes": holes,
    "bg_islands": background_islands, "panels": panels,
}


def parse_views(grid) -> dict:
    return {name: fn(grid) for name, fn in PARSERS.items()}


# ----------------------------------------------------------------- relations
def _bbox_contains(a, b) -> bool:
    ar0, ac0, ar1, ac1 = a.bbox
    br0, bc0, br1, bc1 = b.bbox
    return ar0 <= br0 and ac0 <= bc0 and ar1 >= br1 and ac1 >= bc1 and a.size != b.size


def _adjacent(a, b, conn=N8) -> tuple:
    """Return contact direction set if a,b touch, else empty."""
    dirs = set()
    bset = b.cells
    for (r, c) in a.cells:
        for dr, dc in conn:
            if (r + dr, c + dc) in bset:
                if dr < 0:
                    dirs.add("up")
                elif dr > 0:
                    dirs.add("down")
                if dc < 0:
                    dirs.add("left")
                elif dc > 0:
                    dirs.add("right")
    return frozenset(dirs)


def _d4_forms(cells):
    forms = []
    for fn in (lambda r, c: (r, c), lambda r, c: (r, -c), lambda r, c: (-r, c), lambda r, c: (-r, -c),
               lambda r, c: (c, r), lambda r, c: (-c, r), lambda r, c: (c, -r), lambda r, c: (-c, -r)):
        pts = [fn(r, c) for r, c in cells]
        mr, mc = min(r for r, _ in pts), min(c for _, c in pts)
        forms.append(frozenset((r - mr, c - mc) for r, c in pts))
    return forms


@dataclass
class ObjectGraph:
    grid: Grid
    view: str
    objects: list
    relations: list = field(default_factory=list)  # (type, a_id, b_id, payload)

    def summary(self) -> dict:
        rc = Counter(t for t, *_ in self.relations)
        return {"view": self.view, "n_objects": len(self.objects),
                "kinds": dict(Counter(o.kind for o in self.objects)),
                "n_relations": len(self.relations), "relation_types": dict(rc)}


def build_object_graph(grid, view="color") -> ObjectGraph:
    g = norm(grid)
    H, W = dims(g)
    objs = PARSERS[view](grid)
    rels = []
    d4 = {o.id: _d4_forms(o.cells) for o in objs}
    hc = {o.id: o.holes() for o in objs}        # cache holes once (avoid O(n^2) recompute)
    for a, b in combinations(objs, 2):
        # containment (host-marker): larger bbox contains smaller
        if _bbox_contains(a, b):
            rels.append(("contains", a.id, b.id, None))
            if b.size <= max(2, a.size // 3):
                rels.append(("host_marker", a.id, b.id, None))
        elif _bbox_contains(b, a):
            rels.append(("contains", b.id, a.id, None))
            if a.size <= max(2, b.size // 3):
                rels.append(("host_marker", b.id, a.id, None))
        # contact
        d = _adjacent(a, b)
        if d:
            rels.append(("contact", a.id, b.id, sorted(d)))
        # alignment (share a row or column band)
        ar0, ac0, ar1, ac1 = a.bbox
        br0, bc0, br1, bc1 = b.bbox
        if not (ar1 < br0 or br1 < ar0):
            rels.append(("row_aligned", a.id, b.id, None))
        if not (ac1 < bc0 or bc1 < ac0):
            rels.append(("col_aligned", a.id, b.id, None))
        # similarity
        if a.normalized() == b.normalized():
            rels.append(("same_shape", a.id, b.id, None))
        elif d4[a.id][0] in d4[b.id]:
            rels.append(("same_shape_d4", a.id, b.id, None))
        if a.color is not None and a.color == b.color:
            rels.append(("same_color", a.id, b.id, None))
        if a.size == b.size:
            rels.append(("same_size", a.id, b.id, None))
        if hc[a.id] == hc[b.id]:
            rels.append(("same_hole_count", a.id, b.id, None))
    return ObjectGraph(g, view, objs, rels)


# ----------------------------------------------------------------- shape / decomposition profile
def shape_profile(train) -> dict:
    """Input/output shape relations to seed the decomposition stage (no content)."""
    ins = [dims(p["input"]) for p in train]
    outs = [dims(p["output"]) for p in train]
    rel = "other"
    if all(i == o for i, o in zip(ins, outs)):
        rel = "same"
    elif len(set(outs)) == 1:
        rel = "constant"
    elif all(o[0] % i[0] == 0 and o[1] % i[1] == 0 for i, o in zip(ins, outs)) and \
            len({(o[0] // i[0], o[1] // i[1]) for i, o in zip(ins, outs)}) == 1:
        rel = "tile"
    elif all(o[0] < i[0] or o[1] < i[1] for i, o in zip(ins, outs)):
        rel = "shrink"
    elif all(o[0] > i[0] or o[1] > i[1] for i, o in zip(ins, outs)):
        rel = "grow"
    return {"in_shapes": ins, "out_shapes": outs, "shape_relation": rel}


# ----------------------------------------------------------------- validation
def main():
    audit_path = WORKSPACE / "tmp" / "claude_current_coverage_audit.json"
    tasks = json.loads(audit_path.read_text())["genuine_coverage_miss"] if audit_path.exists() \
        else [p.stem for p in sorted(EVAL.glob("*.json"))][:23]
    print(f"Parsing {len(tasks)} design-miss tasks (no per-task code)\n")
    ok = 0
    for tid in tasks:
        task = json.loads((EVAL / f"{tid}.json").read_text())
        gi = task["train"][0]["input"]
        views = parse_views(gi)
        og = build_object_graph(gi, "color")
        sp = shape_profile(task["train"])
        nobj = {v: len(o) for v, o in views.items()}
        parsed = all(isinstance(o, Obj) for v in views.values() for o in v)
        ok += int(parsed and len(views) == len(PARSERS))
        print(f"  {tid}: shape={sp['shape_relation']:8} color={nobj['color']:3} ignore={nobj['ignore_color']:3} "
              f"frames={nobj['frames']} holes={nobj['holes']} lines={nobj['lines']} panels={nobj['panels']} "
              f"| graph: {og.summary()['n_relations']} rels {dict(Counter(t for t,*_ in og.relations))}")
    print(f"\nparsed cleanly: {ok}/{len(tasks)} (all {len(PARSERS)} views, valid Obj IR, relations built)")
    print(f"parser bank: {list(PARSERS)}")
    print("relation types: contains, host_marker, contact(dir), row/col_aligned, same_shape(_d4), same_color/size/hole_count")


if __name__ == "__main__":
    main()
