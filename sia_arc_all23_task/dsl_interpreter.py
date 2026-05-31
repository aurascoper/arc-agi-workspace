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


def learn_full_color_transition_map(train: list[dict[str, Any]]) -> dict[int, int] | None:
    """Map colours whose every occurrence changes to one new colour.

    This intentionally rejects sparse/background transitions. For cb2d8a2c-style
    bars it learns 1->2 while refusing the much leakier "some 8 become 3" rule.
    """
    if not same_shape_train(train):
        return None
    seen: dict[int, Counter] = {}
    for p in train:
        gi, go = norm(p["input"]), norm(p["output"])
        for r in range(len(gi)):
            for c in range(len(gi[0])):
                seen.setdefault(gi[r][c], Counter())[go[r][c]] += 1
    mapping: dict[int, int] = {}
    for src, outs in seen.items():
        if len(outs) == 1:
            dst = next(iter(outs))
            if dst != src:
                mapping[src] = dst
    return mapping or None


def learn_bg_draw_color(train: list[dict[str, Any]]) -> int | None:
    if not same_shape_train(train):
        return None
    votes = Counter()
    for p in train:
        gi, go = norm(p["input"]), norm(p["output"])
        background = bg(gi)
        for r in range(len(gi)):
            for c in range(len(gi[0])):
                if gi[r][c] == background and go[r][c] != background:
                    votes[go[r][c]] += 1
    return votes.most_common(1)[0][0] if votes else None


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


def canonical_window(grid: Grid, r0: int, c0: int, h: int, w: int, background: int) -> tuple[tuple[int, ...], ...]:
    # Keep colour values: these are train-fitted templates, not shape-only keys.
    return tuple(tuple(grid[r0 + r][c0 + c] for c in range(w)) for r in range(h))


def learn_frame_occurrence_templates(train: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Learn small templates whose surrounding background is framed in output.

    This is an audited matcher/occurrences scaffold. It intentionally searches a
    tiny fixed family of glyph window sizes and returns only typed data:
    draw colour + window sizes + canonical train templates.
    """
    if not same_shape_train(train):
        return None
    draw_color = learn_bg_draw_color(train)
    if draw_color is None:
        return None
    by_size: dict[str, set[tuple[tuple[int, ...], ...]]] = {}
    for p in train:
        gi, go = norm(p["input"]), norm(p["output"])
        h, w = dims(gi)
        background = bg(gi)
        for wh, ww in ((3, 3), (3, 4), (3, 5), (4, 3), (5, 3)):
            if h < wh + 2 or w < ww + 2:
                continue
            key = f"{wh}x{ww}"
            for r0 in range(1, h - wh):
                for c0 in range(1, w - ww):
                    cells = [gi[r0 + r][c0 + c] for r in range(wh) for c in range(ww)]
                    if sum(v != background for v in cells) < 2:
                        continue
                    frame_changed = 0
                    frame_bg = 0
                    for rr in range(r0 - 1, r0 + wh + 1):
                        for cc in range(c0 - 1, c0 + ww + 1):
                            if r0 <= rr < r0 + wh and c0 <= cc < c0 + ww:
                                continue
                            if gi[rr][cc] == background:
                                frame_bg += 1
                                if go[rr][cc] == draw_color:
                                    frame_changed += 1
                    if frame_bg and frame_changed >= max(2, frame_bg // 3):
                        by_size.setdefault(key, set()).add(canonical_window(gi, r0, c0, wh, ww, background))
    serial = {key: [list(map(list, tpl)) for tpl in sorted(vals)] for key, vals in by_size.items() if vals}
    if not serial:
        return None
    return {"color": draw_color, "templates": serial}


FITTERS = {
    "color_transition_map": learn_color_transition_map,
    "dominant_transition_map": learn_dominant_transition_map,
    "full_color_transition_map": learn_full_color_transition_map,
    "bg_draw_color": learn_bg_draw_color,
    "changed_output_color": learn_changed_output_color,
    "frame_occurrence_templates": learn_frame_occurrence_templates,
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


def components(grid: Any, cells: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    g = norm(grid)
    h, w = dims(g)
    remaining = set(cells)
    out = []
    while remaining:
        start = next(iter(remaining))
        q = deque([start])
        remaining.remove(start)
        comp = {start}
        while q:
            r, c = q.popleft()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = (r + dr, c + dc)
                if 0 <= nb[0] < h and 0 <= nb[1] < w and nb in remaining:
                    remaining.remove(nb)
                    comp.add(nb)
                    q.append(nb)
        out.append(comp)
    return out


def line_bar_components(grid: Any, route_color: int) -> list[dict[str, Any]]:
    g = norm(grid)
    background = bg(g)
    cells = {
        (r, c)
        for r, row in enumerate(g)
        for c, value in enumerate(row)
        if value != background and value != route_color
    }
    bars = []
    for comp in components(g, cells):
        if len(comp) < 2:
            continue
        rs = [r for r, _ in comp]
        cs = [c for _, c in comp]
        r0, r1, c0, c1 = min(rs), max(rs), min(cs), max(cs)
        horizontal = r0 == r1 and len(comp) >= 2
        vertical = c0 == c1 and len(comp) >= 2
        if not (horizontal or vertical):
            continue
        bars.append({
            "cells": comp,
            "bbox": (r0, c0, r1, c1),
            "orientation": "h" if horizontal else "v",
            "length": len(comp),
        })
    return bars


def draw_orth_segment(g: Grid, a: tuple[int, int], b: tuple[int, int], color: int) -> None:
    r1, c1 = a
    r2, c2 = b
    if r1 == r2:
        for c in range(min(c1, c2), max(c1, c2) + 1):
            g[r1][c] = color
    elif c1 == c2:
        for r in range(min(r1, r2), max(r1, r2) + 1):
            g[r][c1] = color


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


def op_bar_bracket_route(grid: Any, args: dict[str, Any]) -> Grid:
    """Draw a conservative rectilinear route around straight host bars.

    This is a generic renderer scaffold for tasks with one route-colour marker
    and one or more straight bar hosts. It uses only input geometry at runtime:
    host bars are non-background/non-route straight components, and turn rails
    are chosen from available empty-side space. Empty selections are a no-op.
    """
    g = norm(grid)
    h, w = dims(g)
    color = int(args["color"])
    markers = [(r, c) for r, c, col in singleton_markers(g, color)]
    if not markers:
        return g
    bars = line_bar_components(g, color)
    if not bars:
        return g
    marker = markers[0]
    hbars = [b for b in bars if b["orientation"] == "h"]
    vbars = [b for b in bars if b["orientation"] == "v"]
    if len(hbars) >= len(vbars):
        ordered = sorted(hbars, key=lambda b: (b["bbox"][0], b["bbox"][1]))
        current = marker
        prev_row = marker[0]
        for bar in ordered:
            r0, c0, _r1, c1 = bar["bbox"]
            turn_row = max(0, min(h - 1, (prev_row + r0) // 2))
            left_space = c0
            right_space = w - 1 - c1
            if right_space > left_space:
                rail_col = min(w - 1, c1 + max(1, min(3, right_space)))
            else:
                rail_col = max(0, c0 - max(1, min(5, left_space)))
            draw_orth_segment(g, current, (turn_row, current[1]), color)
            draw_orth_segment(g, (turn_row, current[1]), (turn_row, rail_col), color)
            current = (turn_row, rail_col)
            prev_row = r0
        end_row = h - 1 if current[0] >= marker[0] else 0
        draw_orth_segment(g, current, (end_row, current[1]), color)
    else:
        ordered = sorted(vbars, key=lambda b: (b["bbox"][1], b["bbox"][0]))
        current = marker
        prev_col = marker[1]
        for bar in ordered:
            r0, c0, r1, _c1 = bar["bbox"]
            turn_col = max(0, min(w - 1, (prev_col + c0) // 2))
            above_space = r0
            below_space = h - 1 - r1
            if below_space > above_space:
                rail_row = min(h - 1, r1 + max(1, min(3, below_space)))
            else:
                rail_row = max(0, r0 - max(1, min(3, above_space)))
            draw_orth_segment(g, current, (current[0], turn_col), color)
            draw_orth_segment(g, (current[0], turn_col), (rail_row, turn_col), color)
            current = (rail_row, turn_col)
            prev_col = c0
        end_col = w - 1 if current[1] >= marker[1] else 0
        draw_orth_segment(g, current, (current[0], end_col), color)
    return g


def op_bar_marker_bracket_route(grid: Any, args: dict[str, Any]) -> Grid:
    """Recolor marked straight bars and route around them by marker count.

    For each straight non-background/non-route bar containing source colours
    from `map`, the side offset is derived from the number of source-colour
    cells in that bar plus one. This keeps the integer parameter input-derived
    instead of a constant, matching the v0.3 derived-int contract.
    """
    original = norm(grid)
    g = norm(grid)
    h, w = dims(g)
    color = int(args["color"])
    cmap = {int(k): int(v) for k, v in (args.get("map") or {}).items()}
    if not cmap:
        return g
    source_colors = set(cmap)
    markers = [(r, c) for r, c, col in singleton_markers(original, color)]
    if not markers:
        return [[cmap.get(v, v) for v in row] for row in g]
    marker = markers[0]
    bars = []
    for bar in line_bar_components(original, color):
        n_src = sum(1 for cell in bar["cells"] if original[cell[0]][cell[1]] in source_colors)
        if n_src <= 0:
            continue
        item = dict(bar)
        item["source_count"] = n_src
        item["margin"] = n_src + 1
        bars.append(item)
    if not bars:
        return [[cmap.get(v, v) for v in row] for row in g]

    hbars = [b for b in bars if b["orientation"] == "h"]
    vbars = [b for b in bars if b["orientation"] == "v"]
    if len(hbars) >= len(vbars):
        first_h = min(hbars, key=lambda b: b["bbox"][0])
        marker_above = marker[0] <= first_h["bbox"][0]
        ordered = sorted(hbars, key=lambda b: (b["bbox"][0], b["bbox"][1]), reverse=not marker_above)
        current = marker
        for bar in ordered:
            r0, c0, r1, c1 = bar["bbox"]
            margin = int(bar["margin"])
            turn_row = max(0, r0 - margin) if marker_above else min(h - 1, r1 + margin)
            left_space = c0
            right_space = w - 1 - c1
            if right_space > left_space:
                rail_col = min(w - 1, c1 + margin)
            else:
                rail_col = max(0, c0 - margin)
            draw_orth_segment(g, current, (turn_row, current[1]), color)
            draw_orth_segment(g, (turn_row, current[1]), (turn_row, rail_col), color)
            current = (turn_row, rail_col)
        end_row = h - 1 if marker_above else 0
        draw_orth_segment(g, current, (end_row, current[1]), color)
    else:
        first_v = min(vbars, key=lambda b: b["bbox"][1])
        marker_left = marker[1] <= first_v["bbox"][1]
        ordered = sorted(vbars, key=lambda b: (b["bbox"][1], b["bbox"][0]), reverse=not marker_left)
        current = marker
        start_below = marker[0] <= (h - 1) / 2
        for idx, bar in enumerate(ordered):
            r0, c0, r1, c1 = bar["bbox"]
            margin = int(bar["margin"])
            turn_col = max(0, c0 - margin) if marker_left else min(w - 1, c1 + margin)
            use_below = start_below if idx % 2 == 0 else not start_below
            if use_below:
                rail_row = min(h - 1, r1 + margin)
            else:
                rail_row = max(0, r0 - margin)
            draw_orth_segment(g, current, (current[0], turn_col), color)
            draw_orth_segment(g, (current[0], turn_col), (rail_row, turn_col), color)
            current = (rail_row, turn_col)
        end_col = w - 1 if marker_left else 0
        draw_orth_segment(g, current, (current[0], end_col), color)

    for r in range(h):
        for c in range(w):
            g[r][c] = cmap.get(g[r][c], g[r][c])
    return g


def op_frame_occurrences(grid: Any, args: dict[str, Any]) -> Grid:
    g = norm(grid)
    h, w = dims(g)
    spec = args.get("spec") or {}
    color = int(spec.get("color"))
    templates = spec.get("templates") or {}
    background = bg(g)
    for key, raw_templates in templates.items():
        try:
            wh_s, ww_s = key.split("x")
            wh, ww = int(wh_s), int(ww_s)
        except Exception:
            continue
        wanted = {tuple(tuple(int(v) for v in row) for row in tpl) for tpl in raw_templates}
        if h < wh + 2 or w < ww + 2:
            continue
        for r0 in range(1, h - wh):
            for c0 in range(1, w - ww):
                tpl = canonical_window(g, r0, c0, wh, ww, background)
                if tpl not in wanted:
                    continue
                for rr in range(r0 - 1, r0 + wh + 1):
                    for cc in range(c0 - 1, c0 + ww + 1):
                        if r0 <= rr < r0 + wh and c0 <= cc < c0 + ww:
                            continue
                        if g[rr][cc] == background:
                            g[rr][cc] = color
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
    "bar_bracket_route": op_bar_bracket_route,
    "bar_marker_bracket_route": op_bar_marker_bracket_route,
    "frame_occurrences": op_frame_occurrences,
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
        "name": "full_color_transition_map",
        "pipeline": [{"op": "recolor_map", "args": {"map": {"learn": "full_color_transition_map"}}}],
    },
    {
        "name": "fill_enclosed_changed_color",
        "pipeline": [{"op": "fill_enclosed", "args": {"color": {"learn": "changed_output_color"}}}],
    },
    {
        "name": "route_singletons_same",
        "pipeline": [{"op": "route_singletons", "args": {"color": "same"}}],
    },
    {
        "name": "full_recolor_then_bar_bracket_route",
        "pipeline": [
            {"op": "recolor_map", "args": {"map": {"learn": "full_color_transition_map"}}},
            {"op": "bar_bracket_route", "args": {"color": {"learn": "bg_draw_color"}}},
        ],
    },
    {
        "name": "bar_marker_bracket_route",
        "pipeline": [
            {
                "op": "bar_marker_bracket_route",
                "args": {
                    "map": {"learn": "full_color_transition_map"},
                    "color": {"learn": "bg_draw_color"},
                },
            }
        ],
    },
    {
        "name": "frame_occurrences",
        "pipeline": [{"op": "frame_occurrences", "args": {"spec": {"learn": "frame_occurrence_templates"}}}],
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
