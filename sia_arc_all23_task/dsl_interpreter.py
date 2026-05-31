"""Tiny quarantined relational DSL interpreter for SIA-lite experiments.

This file is design-only infrastructure. It does not import or edit the live
solver. Programs are JSON-like dictionaries with typed operations and learned
holes. Fitters read train pairs only; private/test outputs are never available.
"""

from __future__ import annotations

from collections import Counter, deque
from copy import deepcopy
from typing import Any, Callable


Grid = list[list[int]]
Program = dict[str, Any]


def norm(g: Any) -> Grid:
    if hasattr(g, "tolist"):
        g = g.tolist()
    return [[int(v) for v in row] for row in g]


def dims(g: Any) -> tuple[int, int]:
    g = norm(g)
    return (len(g), len(g[0]) if g else 0)


def bg(g: Any) -> int:
    g = norm(g)
    return Counter(v for row in g for v in row).most_common(1)[0][0]


def same_shape_train(train: list[dict[str, Any]]) -> bool:
    return all(dims(p["input"]) == dims(p["output"]) for p in train)


def shape_ok(t: Callable[[Any], Grid], train: list[dict[str, Any]]) -> bool:
    try:
        return all(dims(t(deepcopy(p["input"]))) == dims(p["output"]) for p in train)
    except Exception:
        return False


def learn_color_transition_map(train: list[dict[str, Any]]) -> dict[int, int] | None:
    if not same_shape_train(train):
        return None
    mapping: dict[int, int] = {}
    for p in train:
        gi, go = norm(p["input"]), norm(p["output"])
        for r in range(len(gi)):
            for c in range(len(gi[0])):
                a, b = gi[r][c], go[r][c]
                if a == b:
                    continue
                if a in mapping and mapping[a] != b:
                    return None
                mapping[a] = b
    return mapping or None


def learn_dominant_transition_map(train: list[dict[str, Any]]) -> dict[int, int] | None:
    if not same_shape_train(train):
        return None
    votes: dict[int, Counter] = {}
    for p in train:
        gi, go = norm(p["input"]), norm(p["output"])
        for r in range(len(gi)):
            for c in range(len(gi[0])):
                a, b = gi[r][c], go[r][c]
                if a != b:
                    votes.setdefault(a, Counter())[b] += 1
    if not votes:
        return None
    return {a: cnt.most_common(1)[0][0] for a, cnt in votes.items()}


def learn_changed_output_color(train: list[dict[str, Any]]) -> int | None:
    colors = Counter()
    for p in train:
        if dims(p["input"]) != dims(p["output"]):
            return None
        gi, go = norm(p["input"]), norm(p["output"])
        for r in range(len(gi)):
            for c in range(len(gi[0])):
                if gi[r][c] != go[r][c]:
                    colors[go[r][c]] += 1
    return colors.most_common(1)[0][0] if colors else None


FITTERS = {
    "color_transition_map": learn_color_transition_map,
    "dominant_transition_map": learn_dominant_transition_map,
    "changed_output_color": learn_changed_output_color,
}


def resolve(value: Any, train: list[dict[str, Any]]) -> Any:
    if isinstance(value, dict) and set(value) == {"learn"}:
        fitter = FITTERS.get(value["learn"])
        if fitter is None:
            raise ValueError(f"unknown learn key: {value['learn']}")
        out = fitter(train)
        if out is None:
            raise ValueError(f"could not fit learn key: {value['learn']}")
        return out
    if isinstance(value, dict):
        return {k: resolve(v, train) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, train) for v in value]
    return value


def enclosed_regions(grid: Any) -> list[set[tuple[int, int]]]:
    g = norm(grid)
    background = bg(g)
    h, w = dims(g)
    seen = [[False] * w for _ in range(h)]
    out: list[set[tuple[int, int]]] = []
    for sr in range(h):
        for sc in range(w):
            if seen[sr][sc] or g[sr][sc] != background:
                continue
            q = deque([(sr, sc)])
            seen[sr][sc] = True
            cells: set[tuple[int, int]] = set()
            touches_border = False
            while q:
                r, c = q.popleft()
                cells.add((r, c))
                if r in (0, h - 1) or c in (0, w - 1):
                    touches_border = True
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < h and 0 <= nc < w and not seen[nr][nc] and g[nr][nc] == background:
                        seen[nr][nc] = True
                        q.append((nr, nc))
            if not touches_border:
                out.append(cells)
    return out


def singleton_markers(grid: Any, color: int | None = None) -> list[tuple[int, int, int]]:
    g = norm(grid)
    background = bg(g)
    h, w = dims(g)
    pts = []
    for r in range(h):
        for c in range(w):
            col = g[r][c]
            if col == background or (color is not None and col != color):
                continue
            n4 = sum(
                0 <= r + dr < h and 0 <= c + dc < w and g[r + dr][c + dc] == col
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))
            )
            if n4 <= 1:
                pts.append((r, c, col))
    return pts


def op_recolor_map(grid: Any, args: dict[str, Any]) -> Grid:
    g = norm(grid)
    cmap = {int(k): int(v) for k, v in (args.get("map") or {}).items()}
    return [[cmap.get(v, v) for v in row] for row in g]


def op_fill_enclosed(grid: Any, args: dict[str, Any]) -> Grid:
    g = norm(grid)
    color = int(args["color"])
    for region in enclosed_regions(g):
        for r, c in region:
            g[r][c] = color
    return g


def op_route_singletons(grid: Any, args: dict[str, Any]) -> Grid:
    g = norm(grid)
    fill = args.get("color", "same")
    by_color: dict[int, list[tuple[int, int]]] = {}
    for r, c, col in singleton_markers(g):
        by_color.setdefault(col, []).append((r, c))
    for col, pts in by_color.items():
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                r1, c1 = pts[i]
                r2, c2 = pts[j]
                route = []
                if r1 == r2:
                    route = [(r1, c) for c in range(min(c1, c2) + 1, max(c1, c2))]
                elif c1 == c2:
                    route = [(r, c1) for r in range(min(r1, r2) + 1, max(r1, r2))]
                if route:
                    route_color = col if fill == "same" else int(fill)
                    for r, c in route:
                        g[r][c] = route_color
    return g


OPS = {
    "recolor_map": op_recolor_map,
    "fill_enclosed": op_fill_enclosed,
    "route_singletons": op_route_singletons,
}


def signature(program: Program) -> str:
    parts = [program.get("name", "program")]
    for step in program.get("pipeline", []):
        op = step.get("op", "?")
        learn_keys = []
        stack = [step.get("args", {})]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                if set(cur) == {"learn"}:
                    learn_keys.append(cur["learn"])
                else:
                    stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)
        suffix = ",".join(sorted(learn_keys))
        parts.append(f"{op}({suffix})")
    return "|".join(parts)


def compile_program(program: Program, train: list[dict[str, Any]]) -> tuple[str, Callable[[Any], Grid]] | None:
    try:
        fitted = []
        for step in program.get("pipeline", []):
            op = step["op"]
            if op not in OPS:
                return None
            fitted.append((op, resolve(step.get("args", {}), train)))
    except Exception:
        return None

    def transform(grid: Any, fitted=fitted) -> Grid:
        cur = norm(grid)
        for op, args in fitted:
            cur = OPS[op](cur, args)
        return cur

    if not shape_ok(transform, train):
        return None
    return signature(program), transform


DEFAULT_PROGRAMS: list[Program] = [
    {
        "name": "learned_recolor_map",
        "pipeline": [{"op": "recolor_map", "args": {"map": {"learn": "color_transition_map"}}}],
    },
    {
        "name": "dominant_recolor_map",
        "pipeline": [{"op": "recolor_map", "args": {"map": {"learn": "dominant_transition_map"}}}],
    },
    {
        "name": "fill_enclosed_changed_color",
        "pipeline": [{"op": "fill_enclosed", "args": {"color": {"learn": "changed_output_color"}}}],
    },
    {
        "name": "route_singletons_same",
        "pipeline": [{"op": "route_singletons", "args": {"color": "same"}}],
    },
]


def propose_from_programs(train: list[dict[str, Any]], programs: list[Program] | None = None):
    out = []
    for program in programs or DEFAULT_PROGRAMS:
        compiled = compile_program(program, train)
        if compiled is not None:
            out.append(compiled)
    return out


def propose(train):
    return propose_from_programs(train)


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    if len(sys.argv) <= 1:
        print("usage: python3 dsl_interpreter.py path/to/public_task.json")
        raise SystemExit(0)
    task_path = Path(sys.argv[1])
    task = json.loads(task_path.read_text())
    print([name for name, _ in propose(task["train"])])
