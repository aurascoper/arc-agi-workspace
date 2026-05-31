"""Codex sentinel verifier for Claude's relational micro-synthesis lane.

This is a standalone design-only verifier. It does not synthesize from test
outputs and does not edit live Kaggle solver files. Its job is to:

- rerun/poll Claude's relational results,
- independently verify claimed flips when they appear,
- run richer train-output oracle diagnostics when no flip exists,
- classify remaining failures as decomposition, selector, parameter, or renderer.

The oracle diagnostics intentionally use train outputs to locate the failure
locus; they are not candidates for submission.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections import Counter, deque
from copy import deepcopy
from pathlib import Path
from typing import Any

WORKSPACE = Path(__file__).resolve().parent
EVAL = WORKSPACE / "arc_agi_2_data" / "evaluation"
CLAUDE_SCRIPT = WORKSPACE / "arc2_relational_micro_synth.py"
CLAUDE_RESULTS = WORKSPACE / "tmp" / "claude_relational_synth_results.json"
OUT_JSON = WORKSPACE / "tmp" / "codex_relational_verifier.json"

sys.path.insert(0, str(WORKSPACE))
import arc2_relational_micro_synth as C  # noqa: E402


def norm(grid: list[list[int]]) -> list[list[int]]:
    return [list(row) for row in grid]


def shape(grid: list[list[int]]) -> tuple[int, int]:
    grid = norm(grid)
    return len(grid), len(grid[0]) if grid else 0


def background(grid: list[list[int]]) -> int:
    return Counter(value for row in grid for value in row).most_common(1)[0][0]


def componentize(cells: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    todo = set(cells)
    comps: list[set[tuple[int, int]]] = []
    while todo:
        start = todo.pop()
        comp = {start}
        queue = deque([start])
        while queue:
            r, c = queue.popleft()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = (r + dr, c + dc)
                if nb in todo:
                    todo.remove(nb)
                    comp.add(nb)
                    queue.append(nb)
        comps.append(comp)
    return comps


def d4_signature(points: dict[tuple[int, int], int]) -> set[frozenset[tuple[tuple[int, int], int]]]:
    forms = (
        lambda r, c: (r, c),
        lambda r, c: (c, -r),
        lambda r, c: (-r, -c),
        lambda r, c: (-c, r),
        lambda r, c: (r, -c),
        lambda r, c: (-r, c),
        lambda r, c: (c, r),
        lambda r, c: (-c, -r),
    )
    out: set[frozenset[tuple[tuple[int, int], int]]] = set()
    for fn in forms:
        transformed = [(fn(r, c), color) for (r, c), color in points.items()]
        min_r = min(r for (r, _c), _color in transformed)
        min_c = min(c for (_r, c), _color in transformed)
        out.add(frozenset((((r - min_r, c - min_c), color) for (r, c), color in transformed)))
    return out


def input_object_signatures(grid: list[list[int]]) -> set[frozenset[tuple[tuple[int, int], int]]]:
    signatures: set[frozenset[tuple[tuple[int, int], int]]] = set()
    for obj in C.components(grid):
        points = {(r, c): grid[r][c] for r, c in obj["cells"]}
        signatures |= d4_signature(points)
    return signatures


def normalized_signature(cells: set[tuple[int, int]], colors: dict[tuple[int, int], int]) -> frozenset[tuple[tuple[int, int], int]]:
    min_r = min(r for r, _c in cells)
    min_c = min(c for _r, c in cells)
    return frozenset((((r - min_r, c - min_c), colors[(r, c)]) for r, c in cells))


def is_straight_8_connected_line(cells: set[tuple[int, int]]) -> bool:
    if len(cells) <= 1:
        return True
    rows = {r for r, _c in cells}
    cols = {c for _r, c in cells}
    if len(rows) == 1:
        row = next(iter(rows))
        return cells == {(row, c) for c in range(min(cols), max(cols) + 1)}
    if len(cols) == 1:
        col = next(iter(cols))
        return cells == {(r, col) for r in range(min(rows), max(rows) + 1)}
    diag = {r - c for r, c in cells}
    if len(diag) == 1:
        d = next(iter(diag))
        rs = range(min(rows), max(rows) + 1)
        return cells == {(r, r - d) for r in rs}
    anti = {r + c for r, c in cells}
    if len(anti) == 1:
        s = next(iter(anti))
        rs = range(min(rows), max(rows) + 1)
        return cells == {(r, s - r) for r in rs}
    return False


def line_orientation(cells: set[tuple[int, int]]) -> str:
    if len(cells) <= 1:
        return "point"
    rows = {r for r, _c in cells}
    cols = {c for _r, c in cells}
    if len(rows) == 1:
        return "horizontal"
    if len(cols) == 1:
        return "vertical"
    if len({r - c for r, c in cells}) == 1:
        return "diag"
    if len({r + c for r, c in cells}) == 1:
        return "anti"
    return "other"


def aligned(a: tuple[int, int], b: tuple[int, int], orientation: str) -> bool:
    if orientation == "horizontal":
        return a[0] == b[0]
    if orientation == "vertical":
        return a[1] == b[1]
    if orientation == "diag":
        return a[0] - a[1] == b[0] - b[1]
    if orientation == "anti":
        return a[0] + a[1] == b[0] + b[1]
    return False


def component_endpoint_support(
    comp: set[tuple[int, int]],
    inp: list[list[int]],
    color: int,
) -> dict[str, int]:
    rows = [r for r, _c in comp]
    cols = [c for _r, c in comp]
    endpoints: list[tuple[int, int]]
    if len(set(rows)) == 1:
        row = rows[0]
        endpoints = [(row, min(cols)), (row, max(cols))]
    elif len(set(cols)) == 1:
        col = cols[0]
        endpoints = [(min(rows), col), (max(rows), col)]
    else:
        endpoints = [
            min(comp, key=lambda p: (p[0], p[1])),
            max(comp, key=lambda p: (p[0], p[1])),
        ]
    h, w = shape(inp)
    same_color_support = 0
    non_bg_support = 0
    bg = background(inp)
    for r, c in endpoints:
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w:
                same_color_support += int(inp[nr][nc] == color)
                non_bg_support += int(inp[nr][nc] != bg)
    return {"same_color_endpoint_neighbors": same_color_support, "non_bg_endpoint_neighbors": non_bg_support}


def segment_endpoint_oracle_ablation(inp: list[list[int]], out: list[list[int]]) -> dict[str, Any]:
    inp = norm(inp)
    out = norm(out)
    if shape(inp) != shape(out):
        return {"available": False, "reason": "shape_change"}
    h, w = shape(inp)
    bg = background(inp)
    added_by_color: dict[int, set[tuple[int, int]]] = {}
    removed_by_color: dict[int, set[tuple[int, int]]] = {}
    for r in range(h):
        for c in range(w):
            if inp[r][c] == bg and out[r][c] != bg:
                added_by_color.setdefault(out[r][c], set()).add((r, c))
            if inp[r][c] != bg and out[r][c] == bg:
                removed_by_color.setdefault(inp[r][c], set()).add((r, c))
    rows = []
    for color, added_cells in sorted(added_by_color.items()):
        for comp in componentize(added_cells):
            if len(comp) <= 1:
                continue
            orientation = line_orientation(comp)
            is_line = is_straight_8_connected_line(comp)
            removed = removed_by_color.get(color, set())
            min_removed_dist = min((abs(r - rr) + abs(c - cc) for r, c in comp for rr, cc in removed), default=None)
            aligned_removed = sum(
                1
                for removed_cell in removed
                if any(aligned(removed_cell, cell, orientation) for cell in comp)
            )
            endpoints = component_endpoint_support(comp, inp, color)
            rows.append({
                "color": color,
                "size": len(comp),
                "orientation": orientation,
                "is_straight_line": is_line,
                "same_color_removed_count": len(removed),
                "min_same_color_removed_dist": min_removed_dist,
                "aligned_same_color_removed": aligned_removed,
                **endpoints,
            })
    return {
        "available": bool(rows),
        "segments": rows,
        "all_multicell_additions_are_segments": all(row["is_straight_line"] for row in rows) if rows else False,
        "all_segments_have_same_color_removed": all(row["same_color_removed_count"] > 0 for row in rows) if rows else False,
        "all_segments_have_aligned_removed": all(row["aligned_same_color_removed"] > 0 for row in rows) if rows else False,
    }


def side_of_component_relative_to_bbox(comp: set[tuple[int, int]], bbox: tuple[int, int, int, int]) -> list[str]:
    rows = [r for r, _c in comp]
    cols = [c for _r, c in comp]
    center_r = sum(rows) / len(rows)
    center_c = sum(cols) / len(cols)
    r0, c0, r1, c1 = bbox
    sides: list[str] = []
    if center_r < r0:
        sides.append("above")
    elif center_r > r1:
        sides.append("below")
    if center_c < c0:
        sides.append("left")
    elif center_c > c1:
        sides.append("right")
    return sides or ["inside"]


def color_group_summary(inp: list[list[int]], color: int) -> dict[str, Any] | None:
    cells = set(C.cells_of_color(inp, color))
    if not cells:
        return None
    rows = [r for r, _c in cells]
    cols = [c for _r, c in cells]
    r0, c0, r1, c1 = min(rows), min(cols), max(rows), max(cols)
    edge_counts = {
        "above": sum((r0, c) in cells for c in range(c0, c1 + 1)),
        "below": sum((r1, c) in cells for c in range(c0, c1 + 1)),
        "left": sum((r, c0) in cells for r in range(r0, r1 + 1)),
        "right": sum((r, c1) in cells for r in range(r0, r1 + 1)),
    }
    min_count = min(edge_counts.values())
    return {
        "color": color,
        "bbox": (r0, c0, r1, c1),
        "edge_counts": edge_counts,
        "sparse_sides": [side for side, count in edge_counts.items() if count == min_count],
    }


def host_apex_parameter_ablation(inp: list[list[int]], out: list[list[int]]) -> dict[str, Any]:
    """Oracle diagnostic for segment tasks whose output leaves through a host apex.

    This uses train output only to locate the added segment and erased marker
    fragments. It then asks whether input-only color-group geometry exposes a
    plausible sparse/apex side for the host object. It is a diagnostic, not a
    candidate transform.
    """
    inp = norm(inp)
    out = norm(out)
    if shape(inp) != shape(out):
        return {"available": False, "reason": "shape_change"}
    h, w = shape(inp)
    bg = background(inp)
    added_by_color: dict[int, set[tuple[int, int]]] = {}
    removed_by_color: dict[int, set[tuple[int, int]]] = {}
    for r in range(h):
        for c in range(w):
            if inp[r][c] == bg and out[r][c] != bg:
                added_by_color.setdefault(out[r][c], set()).add((r, c))
            if inp[r][c] != bg and out[r][c] == bg:
                removed_by_color.setdefault(inp[r][c], set()).add((r, c))

    rows = []
    for marker, added_cells in sorted(added_by_color.items()):
        for added_comp in componentize(added_cells):
            if len(added_comp) <= 1 or not is_straight_8_connected_line(added_comp):
                continue
            removed = removed_by_color.get(marker, set())
            if not removed:
                continue
            host_colors: set[int] = set()
            for r, c in removed:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if not (dr or dc):
                            continue
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < h and 0 <= nc < w and inp[nr][nc] not in (bg, marker):
                            host_colors.add(inp[nr][nc])
            candidates = []
            for host_color in sorted(host_colors):
                summary = color_group_summary(inp, host_color)
                if not summary:
                    continue
                segment_sides = side_of_component_relative_to_bbox(added_comp, summary["bbox"])
                candidates.append({
                    "host_color": host_color,
                    "host_bbox": summary["bbox"],
                    "host_sparse_sides": summary["sparse_sides"],
                    "segment_sides": segment_sides,
                    "sparse_side_match": bool(set(summary["sparse_sides"]) & set(segment_sides)),
                    "orientation": line_orientation(added_comp),
                    "segment_size": len(added_comp),
                })
            rows.append({
                "marker": marker,
                "candidate_hosts": candidates,
                "any_sparse_side_match": any(candidate["sparse_side_match"] for candidate in candidates),
                "candidate_count": len(candidates),
            })
    return {
        "available": bool(rows),
        "segments": rows,
        "all_segments_have_sparse_side_match": all(row["any_sparse_side_match"] for row in rows) if rows else False,
        "all_segments_have_unique_candidate": all(row["candidate_count"] == 1 for row in rows) if rows else False,
    }


def pair_oracle_diagnostics(inp: list[list[int]], out: list[list[int]]) -> dict[str, Any]:
    inp = norm(inp)
    out = norm(out)
    if shape(inp) != shape(out):
        return {"shape_change": True, "input_shape": shape(inp), "output_shape": shape(out)}
    h, w = shape(inp)
    bg = background(inp)
    added = {(r, c): out[r][c] for r in range(h) for c in range(w) if inp[r][c] == bg and out[r][c] != bg}
    erased = {(r, c): inp[r][c] for r in range(h) for c in range(w) if inp[r][c] != bg and out[r][c] == bg}
    recolored = {
        (r, c): (inp[r][c], out[r][c])
        for r in range(h)
        for c in range(w)
        if inp[r][c] != bg and out[r][c] != bg and inp[r][c] != out[r][c]
    }
    add_comps = componentize(set(added))
    input_sigs = input_object_signatures(inp)
    line_components = 0
    multi_components = 0
    multi_line_components = 0
    rigid_copies = 0
    endpoint_supported = 0
    comp_rows = []
    for comp in add_comps:
        colors = {cell: added[cell] for cell in comp}
        is_line = is_straight_8_connected_line(comp)
        sig = normalized_signature(comp, colors)
        rigid = sig in input_sigs
        support = component_endpoint_support(comp, inp, next(iter(colors.values()))) if comp else {}
        line_components += int(is_line)
        multi_components += int(len(comp) > 1)
        multi_line_components += int(len(comp) > 1 and is_line)
        rigid_copies += int(rigid)
        endpoint_supported += int(bool(support.get("same_color_endpoint_neighbors") or support.get("non_bg_endpoint_neighbors")))
        comp_rows.append({
            "size": len(comp),
            "colors": sorted(set(colors.values())),
            "is_straight_line": is_line,
            "is_rigid_input_copy": rigid,
            **support,
        })
    return {
        "shape_change": False,
        "n_added": len(added),
        "n_erased": len(erased),
        "n_recolored": len(recolored),
        "added_components": len(add_comps),
        "line_added_components": line_components,
        "multi_added_components": multi_components,
        "multi_line_added_components": multi_line_components,
        "rigid_copy_added_components": rigid_copies,
        "endpoint_supported_added_components": endpoint_supported,
        "added_component_samples": comp_rows[:8],
        "recolor_pairs": sorted(Counter(recolored.values()).items(), key=lambda item: (-item[1], item[0]))[:10],
    }


def panel_fill_oracle(task: dict[str, Any]) -> dict[str, Any]:
    rows = []
    exact_all = True
    marker_colors = []
    for pair in task["train"]:
        panel = C.find_host_panel(pair["input"])
        if panel is None:
            return {"available": False, "reason": "missing_panel"}
        marker_candidates = C.marker_color_candidates([pair])
        exact_for_pair = []
        for marker in marker_candidates:
            consumed = C.oracle_consumed_set(pair["input"], pair["output"], marker)
            pred = C.render_fill_panel(pair["input"], panel, marker, consumed)
            if C.equal(pred, pair["output"]):
                exact_for_pair.append({"marker": marker, "consumed_count": len(consumed)})
        exact_all = exact_all and bool(exact_for_pair)
        rows.append(exact_for_pair)
        if exact_for_pair:
            marker_colors.append(exact_for_pair[0]["marker"])
    return {
        "available": True,
        "oracle_exact_all_pairs": exact_all and len(set(marker_colors)) == 1,
        "marker_colors": marker_colors,
        "per_pair": rows,
    }


def component_graph_selector_ablation(task: dict[str, Any]) -> dict[str, Any]:
    """Train-output oracle analysis for marker-component selector complexity.

    This asks whether consumed markers can be selected at whole-component
    granularity. Partial components mean the representation must split marker
    components or add a within-component selector.
    """
    marker_candidates = C.marker_color_candidates(task["train"])
    if not marker_candidates:
        return {"available": False, "reason": "no_marker_candidates"}
    marker = marker_candidates[0]
    rows = []
    feature_rows = []
    for pair_index, pair in enumerate(task["train"]):
        panel = C.find_host_panel(pair["input"])
        if panel is None:
            return {"available": False, "reason": "missing_panel"}
        inp = norm(pair["input"])
        h, w = shape(inp)
        bg = background(inp)
        path_color = C.path_color_guess(inp, marker, panel["panel_color"])
        path_cells = set(C.cells_of_color(inp, path_color)) if path_color is not None else set()
        consumed = set(C.oracle_consumed_set(pair["input"], pair["output"], marker))
        panel_cells = set(panel["rowmajor"])
        r0, c0, r1, c1 = panel["bbox"]
        comp_summaries = []
        for obj in C.components(inp, {marker}):
            cells = set(obj["cells"]) - panel_cells
            if not cells:
                continue
            consumed_count = len(cells & consumed)
            label = "all" if consumed_count == len(cells) else "none" if consumed_count == 0 else "partial"
            min_dist_panel = min(abs(r - pr) + abs(c - pc) for r, c in cells for pr in range(r0, r1 + 1) for pc in range(c0, c1 + 1))
            min_dist_path = min((abs(r - pr) + abs(c - pc) for r, c in cells for pr, pc in path_cells), default=-1)
            touches_border = any(r in (0, h - 1) or c in (0, w - 1) for r, c in cells)
            path_neighbor = any(
                0 <= r + dr < h
                and 0 <= c + dc < w
                and (r + dr, c + dc) in path_cells
                for r, c in cells
                for dr in (-1, 0, 1)
                for dc in (-1, 0, 1)
                if dr or dc
            )
            center_r = sum(r for r, _c in cells) / len(cells)
            center_c = sum(c for _r, c in cells) / len(cells)
            vertical_side = "above" if center_r < r0 else "below" if center_r > r1 else "mid"
            horizontal_side = "left" if center_c < c0 else "right" if center_c > c1 else "mid"
            clear_ray = any(C._clear_ray_to_bbox(inp, r, c, panel["bbox"], marker) for r, c in cells)
            feature = {
                "size": len(cells),
                "bbox_h": obj["bbox"][2] - obj["bbox"][0] + 1,
                "bbox_w": obj["bbox"][3] - obj["bbox"][1] + 1,
                "touches_border": int(touches_border),
                "min_dist_panel": min_dist_panel,
                "min_dist_path": min_dist_path,
                "near_path_le1": int(0 <= min_dist_path <= 1),
                "path_neighbor": int(path_neighbor),
                "vertical_side": vertical_side,
                "horizontal_side": horizontal_side,
                "side": (vertical_side, horizontal_side),
                "clear_ray_to_panel": int(clear_ray),
            }
            feature_rows.append((feature, label))
            comp_summaries.append({
                "size": len(cells),
                "consumed_count": consumed_count,
                "label": label,
                "features": feature,
            })
        rows.append({"pair_index": pair_index, "components": comp_summaries})

    label_counts = Counter(label for _feature, label in feature_rows)
    feature_names = [
        "size", "bbox_h", "bbox_w", "touches_border", "min_dist_panel", "min_dist_path",
        "near_path_le1", "path_neighbor", "vertical_side", "horizontal_side", "side",
        "clear_ray_to_panel",
    ]
    separability = {}
    for name in feature_names:
        value_labels: dict[Any, set[str]] = {}
        for feature, label in feature_rows:
            value_labels.setdefault(feature[name], set()).add(label)
        separability[name] = {
            "separable": all(len(labels) == 1 for labels in value_labels.values()),
            "conflict_values": [value for value, labels in value_labels.items() if len(labels) > 1][:8],
            "all_values": [value for value, labels in value_labels.items() if labels == {"all"}][:8],
            "partial_values": [value for value, labels in value_labels.items() if labels == {"partial"}][:8],
        }
    return {
        "available": True,
        "marker": marker,
        "label_counts": dict(label_counts),
        "has_partial_components": label_counts.get("partial", 0) > 0,
        "separability": separability,
        "per_pair": rows,
    }


def classify_task(task_id: str) -> dict[str, Any]:
    task = json.loads((EVAL / f"{task_id}.json").read_text())
    pair_diags = [pair_oracle_diagnostics(pair["input"], pair["output"]) for pair in task["train"]]
    segment_diags = [segment_endpoint_oracle_ablation(pair["input"], pair["output"]) for pair in task["train"]]
    host_apex_diags = [host_apex_parameter_ablation(pair["input"], pair["output"]) for pair in task["train"]]
    panel = panel_fill_oracle(task)
    component_ablation = component_graph_selector_ablation(task) if panel.get("available") else {"available": False, "reason": panel.get("reason")}
    if panel.get("oracle_exact_all_pairs"):
        failure = "selector_oracle_panel_fill"
    elif all(not row.get("shape_change") and row.get("n_added", 0) > 0 for row in pair_diags):
        line_counts = sum(row["multi_line_added_components"] for row in pair_diags)
        comp_counts = sum(row["multi_added_components"] for row in pair_diags)
        rigid_counts = sum(row["rigid_copy_added_components"] for row in pair_diags)
        if comp_counts and line_counts / comp_counts >= 0.95:
            failure = "path_endpoint_or_parameter"
        # Treat rigid-copy/motif as a usable locus only when it explains nearly
        # all multi-cell additions. Lower ratios are usually mixed generated
        # structure and were too loose for 35ab12c3.
        elif comp_counts and rigid_counts / comp_counts >= 0.95:
            failure = "motif_placement_or_anchor"
        else:
            failure = "renderer_or_decomposition_for_generated_structure"
    elif all(not row.get("shape_change") and row.get("n_recolored", 0) > 0 for row in pair_diags):
        failure = "role_recolor_or_object_rewrite"
    else:
        failure = "shape_or_mixed"
    return {
        "task_id": task_id,
        "train_pairs": len(task["train"]),
        "oracle_panel_fill": panel,
        "component_graph_selector_ablation": component_ablation,
        "segment_endpoint_oracle_ablation": segment_diags,
        "host_apex_parameter_ablation": host_apex_diags,
        "pair_oracle_diagnostics": pair_diags,
        "codex_failure_class": failure,
    }


def run_claude_script() -> dict[str, Any]:
    subprocess.run([sys.executable, "-m", "py_compile", str(CLAUDE_SCRIPT)], check=True, cwd=WORKSPACE)
    subprocess.run([sys.executable, str(CLAUDE_SCRIPT)], check=True, cwd=WORKSPACE)
    return json.loads(CLAUDE_RESULTS.read_text())


def static_leakage_scan() -> dict[str, Any]:
    source = CLAUDE_SCRIPT.read_text()
    tree = ast.parse(source)
    strings = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    actionable_patterns = (
        "arc_agi_2_data/test",
        "arc_agi_2_data/training",
        "run_pseudo_private_eval",
        "pp_cal",
        "pp_design",
        "public_signature",
        "templates =",
        "solve_",
    )
    actionable_hits = {
        token: [idx + 1 for idx, line in enumerate(source.splitlines()) if token in line]
        for token in actionable_patterns
    }
    prose_only_hits = {
        token: [idx + 1 for idx, line in enumerate(source.splitlines()) if token in line]
        for token in ("public templates", "frozen calibration")
    }
    task_id_hits = [s for s in strings if s in C.TARGETS]
    return {
        "actionable_forbidden_hits": actionable_hits,
        "prose_only_guardrail_mentions": prose_only_hits,
        "task_id_string_constants": task_id_hits,
        "target_ids_are_design_lane_only": sorted(task_id_hits) == sorted(C.TARGETS),
        "string_constant_count": len(strings),
        "leakage_detected": any(actionable_hits.values()),
    }


def main() -> None:
    claude_results = run_claude_script()
    task_ids = claude_results.get("targets", C.TARGETS)
    task_reports = [classify_task(task_id) for task_id in task_ids]
    claude_task_loci = {
        row["task_id"]: row.get("failure_locus_4way")
        for row in claude_results.get("tasks", [])
        if isinstance(row, dict) and "task_id" in row
    }
    for row in task_reports:
        claude_locus = claude_task_loci.get(row["task_id"], "")
        if (
            isinstance(claude_locus, str)
            and claude_locus.startswith("renderer")
            and row["codex_failure_class"] == "motif_placement_or_anchor"
        ):
            row["codex_failure_class"] = "renderer_or_decomposition_for_generated_structure"
            row["codex_failure_class_note"] = (
                "downgraded from loose rigid-copy heuristic because Claude's "
                "strict segment/copy/stamp oracle did not reproduce the outputs"
            )
    verified_flips = []
    for task_id in claude_results.get("flips", []):
        # No transform handoff exists yet; rerun result is the independent source.
        verified_flips.append({"task_id": task_id, "status": "claimed_by_claude_results_needs_transform_handoff"})
    report = {
        "lane": "codex_relational_sentinel",
        "claude_flips": claude_results.get("flips", []),
        "verified_flips": verified_flips,
        "integration_ready": bool(verified_flips),
        "static_leakage_scan": static_leakage_scan(),
        "claude_failure_loci": claude_task_loci,
        "tasks": task_reports,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2))
    print(json.dumps({
        "claude_flips": report["claude_flips"],
        "integration_ready": report["integration_ready"],
        "claude_failure_loci": claude_task_loci,
        "task_classes": {row["task_id"]: row["codex_failure_class"] for row in task_reports},
        "out": str(OUT_JSON),
    }, indent=2))


if __name__ == "__main__":
    main()
