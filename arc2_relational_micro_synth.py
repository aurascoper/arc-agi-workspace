"""Relational micro-synthesis — design-only research lane (Claude), standalone.

Tests whether the 23 strict design misses are SELECTOR-limited (a search/relational-feature problem,
still tractable) or RENDER-limited (a representation problem). Prior work falsified 5 generic operator
classes; this lane searches small COMPOSITIONAL, GENERATIVE relational programs and, crucially, runs an
ORACLE-SELECTOR ablation that isolates the failure locus.

Representation: bg / host objects / marker fragments / paths / central panels.
Render ops (generative): erase, render_ray, copy_motif_along_path, relocate, thread_spine,
fill_panel_by_marker_count.
Gate: train-exact + leave-one-train-out (LOO) + synthetic invariance (color-perm / padding).
Discipline: no task ids / coordinate signatures / public templates / frozen calibration / replay;
design test output is a READOUT only, never a synthesis input. Never edits Codex hot files.

Oracle ablation: for a render family, compute its parameters from the TRAIN OUTPUT (cheating, readout
only) and test if the render then reproduces train. If oracle-render is exact but no input-only selector
is LOO-stable -> SELECTOR-limited. If even oracle-render can't reproduce train -> RENDER-limited.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKSPACE))
import arc2_candidate_solver as S  # noqa: E402  (read-only import)

EVAL = WORKSPACE / "arc_agi_2_data" / "evaluation"

TARGETS = ["4a21e3da", "3dc255db", "dd6b8c4b", "35ab12c3", "142ca369", "195c6913"]


# ----------------------------------------------------------------- grid utilities
def norm(g):
    return S.normalize_grid(g)


def shape(g):
    g = norm(g)
    return (len(g), len(g[0]))


def background(g):
    g = norm(g)
    return Counter(v for row in g for v in row).most_common(1)[0][0]


def cells_of_color(g, col):
    g = norm(g)
    return [(r, c) for r in range(len(g)) for c in range(len(g[0])) if g[r][c] == col]


def components(g, colors=None):
    """4-connected single-colour components (non-bg). colors restricts to a colour set."""
    g = norm(g)
    bg = background(g)
    H, W = len(g), len(g[0])
    seen = [[False] * W for _ in range(H)]
    objs = []
    for r in range(H):
        for c in range(W):
            col = g[r][c]
            if col == bg or seen[r][c] or (colors is not None and col not in colors):
                continue
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
                         "centroid": (sum(rs) / len(rs), sum(cs) / len(cs)),
                         "touches_border": any(rr in (0, H - 1) or cc in (0, W - 1) for rr, cc in cells)})
    return objs


def diff_cells(a, b):
    a, b = norm(a), norm(b)
    if shape(a) != shape(b):
        return None
    return [(r, c, a[r][c], b[r][c]) for r in range(len(a)) for c in range(len(a[0])) if a[r][c] != b[r][c]]


def equal(a, b):
    return norm(a) == norm(b)


# --------------------------------------------- FILL_PANEL_BY_MARKER_COUNT family (dd6b8c4b-like)
def find_host_panel(g):
    """A small framed panel: the connected non-bg, non-noise structure with an enclosed centre.
    Heuristic: the largest component whose colour forms a hollow-ish box (size >= perimeter-ish).
    Returns (panel_color, centre_marker_color, ordered_cells_row_major, bbox) or None."""
    g = norm(g)
    bg = background(g)
    objs = components(g)
    # candidate panels: components forming a rectangle frame (bbox area ~ cells for solid, or frame)
    best = None
    for o in objs:
        r0, c0, r1, c1 = o["bbox"]
        h, w = r1 - r0 + 1, c1 - c0 + 1
        if h < 2 or w < 2:
            continue
        area = h * w
        cellset = set(o["cells"])
        # centre marker = any non-bg, non-panel colour strictly inside the bbox
        inside = [(r, c) for r in range(r0 + 1, r1) for c in range(c0 + 1, c1)]
        centre_colors = {g[r][c] for r, c in inside if g[r][c] not in (bg, o["color"])}
        # panel must roughly tile its bbox (solid or frame) and contain a centre marker
        if not centre_colors:
            continue
        coverage = len(cellset) / area
        if coverage < 0.4:
            continue
        rowmajor = [(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]
        if best is None or area < best[3]:
            best = (o["color"], next(iter(centre_colors)), rowmajor, area, (r0, c0, r1, c1))
    if best is None:
        return None
    return {"panel_color": best[0], "centre_color": best[1], "rowmajor": best[2], "bbox": best[4]}


def render_fill_panel(g, panel, marker_color, consumed):
    """Erase exactly the `consumed` marker cells (-> bg); fill the first len(consumed) panel cells
    (row-major) with marker_color. consumed = set of (r,c). The render is fully determined by the
    consumed set (count == |consumed|)."""
    g = [row[:] for row in norm(g)]
    bg = background(g)
    for (r, c) in consumed:
        if 0 <= r < len(g) and 0 <= c < len(g[0]):
            g[r][c] = bg
    for i, (r, c) in enumerate(panel["rowmajor"]):
        if i < len(consumed):
            g[r][c] = marker_color
    return g


def oracle_consumed_set(gi, go, marker_color):
    """Readout-only: the marker cells erased by the train output (input==marker, output==bg)."""
    gi, go = norm(gi), norm(go)
    bg = background(gi)
    return {(r, c) for r in range(len(gi)) for c in range(len(gi[0]))
            if gi[r][c] == marker_color and go[r][c] == bg}


# --------------------------------------------------- selector vocabulary for "consumed markers"
def marker_color_candidates(train):
    """Colours that appear as scattered small fragments AND are involved in the diff (added/removed)."""
    cand = Counter()
    for p in train:
        gi, go = norm(p["input"]), norm(p["output"])
        bg = background(gi)
        d = diff_cells(gi, go) or []
        for r, c, a, b in d:
            for col in (a, b):
                if col != bg:
                    cand[col] += 1
    return [c for c, _ in cand.most_common()]


def consumed_marker_selectors():
    """Each selector: (name, fn(grid, marker_color, panel) -> SET of consumed marker (r,c) cells).
    The crux of dd6b8c4b: which scattered markers are 'consumed'."""
    def non_panel(g, mk, panel):
        ps = set(panel["rowmajor"])
        return {(r, c) for (r, c) in cells_of_color(g, mk) if (r, c) not in ps}

    def all_markers(g, mk, panel):
        return non_panel(g, mk, panel)

    def isolated_cells(g, mk, panel):
        gg = norm(g)
        H, W = len(gg), len(gg[0])
        return {(r, c) for (r, c) in non_panel(g, mk, panel)
                if not any(0 <= r + dr < H and 0 <= c + dc < W and gg[r + dr][c + dc] == mk
                           for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)))}

    def free_floating(g, mk, panel):
        gg = norm(g)
        H, W = len(gg), len(gg[0])
        bg = background(gg)
        out = set()
        for (r, c) in non_panel(g, mk, panel):
            nbrs = [gg[r + dr][c + dc] for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                    if (dr or dc) and 0 <= r + dr < H and 0 <= c + dc < W]
            if all(v in (bg, mk) for v in nbrs):
                out.add((r, c))
        return out

    def touching_other_object(g, mk, panel):
        # markers 8-adjacent to a non-bg, non-marker object (attached, not free noise)
        gg = norm(g)
        H, W = len(gg), len(gg[0])
        bg = background(gg)
        out = set()
        for (r, c) in non_panel(g, mk, panel):
            nbrs = [gg[r + dr][c + dc] for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                    if (dr or dc) and 0 <= r + dr < H and 0 <= c + dc < W]
            if any(v not in (bg, mk) for v in nbrs):
                out.add((r, c))
        return out

    def marker_pairs(g, mk, panel):
        # marker cells belonging to a 2-cell component (adjacent pair), per dd6b8c4b pair0 hint
        ps = set(panel["rowmajor"])
        out = set()
        for o in components(g, {mk}):
            if set(o["cells"]) & ps:
                continue
            if o["size"] == 2:
                out.update(o["cells"])
        return out

    return [
        ("all_non_panel_markers", all_markers),
        ("isolated_marker_cells", isolated_cells),
        ("free_floating_markers", free_floating),
        ("markers_touching_other_object", touching_other_object),
        ("two_cell_marker_pairs", marker_pairs),
    ]


# ---------------------------------- feature-based consumed-marker SELECTOR search (Codex vocabulary)
def path_color_guess(g, mk, panel_color):
    g = norm(g)
    bg = background(g)
    cnt = Counter(v for row in g for v in row if v not in (bg, mk, panel_color))
    return cnt.most_common(1)[0][0] if cnt else None


def _enclosed_by(g, r, c, wall):
    """Flood from (r,c) through non-wall cells (4-conn); enclosed iff flood never reaches the border."""
    g = norm(g)
    H, W = len(g), len(g[0])
    seen = {(r, c)}
    stack = [(r, c)]
    while stack:
        rr, cc = stack.pop()
        if rr in (0, H - 1) or cc in (0, W - 1):
            return False
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = rr + dr, cc + dc
            if 0 <= nr < H and 0 <= nc < W and (nr, nc) not in seen and g[nr][nc] != wall:
                seen.add((nr, nc))
                stack.append((nr, nc))
    return True


def _clear_ray_to_bbox(g, r, c, bbox, mk):
    """True if a straight horizontal/vertical line from (r,c) reaches the panel bbox through bg/mk only."""
    g = norm(g)
    bg = background(g)
    r0, c0, r1, c1 = bbox
    H, W = len(g), len(g[0])
    # horizontal toward panel column range
    for (dr, dc) in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        rr, cc = r + dr, c + dc
        clear = True
        while 0 <= rr < H and 0 <= cc < W:
            if r0 <= rr <= r1 and c0 <= cc <= c1:
                if clear:
                    return True
                break
            if g[rr][cc] not in (bg, mk):
                clear = False
                break
            rr, cc = rr + dr, cc + dc
    return False


def marker_cell_features(g, mk, panel):
    """Per non-panel marker cell -> feature dict (Codex's hypotheses)."""
    g = norm(g)
    H, W = len(g), len(g[0])
    bg = background(g)
    ps = set(panel["rowmajor"])
    r0, c0, r1, c1 = panel["bbox"]
    pcol = path_color_guess(g, mk, panel["panel_color"])
    comp_of = {}
    for o in components(g, {mk}):
        for cell in o["cells"]:
            comp_of[cell] = o
    path_cells = cells_of_color(g, pcol) if pcol is not None else []
    feats = {}
    for (r, c) in cells_of_color(g, mk):
        if (r, c) in ps:
            continue
        o = comp_of.get((r, c), {"size": 1, "cells": [(r, c)]})
        deg = sum(1 for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))
                  if 0 <= r + dr < H and 0 <= c + dc < W and g[r + dr][c + dc] == mk)
        dist_panel = min(abs(r - rr) + abs(c - cc) for rr in range(r0, r1 + 1) for cc in range(c0, c1 + 1))
        dist_path = (min(abs(r - pr) + abs(c - pc) for pr, pc in path_cells) if path_cells else -1)
        attached = any(0 <= r + dr < H and 0 <= c + dc < W and g[r + dr][c + dc] not in (bg, mk)
                       for dr in (-1, 0, 1) for dc in (-1, 0, 1) if (dr or dc))
        feats[(r, c)] = {
            "comp_size": o["size"],
            "degree": deg,
            "is_endpoint": int(deg <= 1),
            "on_border": int(r in (0, H - 1) or c in (0, W - 1)),
            "dist_panel": dist_panel,
            "dist_path": dist_path,
            "near_path_le1": int(0 <= dist_path <= 1),
            "attached_to_object": int(attached),
            "enclosed_by_path": int(_enclosed_by(g, r, c, pcol)) if pcol is not None else 0,
            "clear_ray_to_panel": int(_clear_ray_to_bbox(g, r, c, panel["bbox"], mk)),
            "quadrant": (int(r > (H - 1) / 2), int(c > (W - 1) / 2)),
            "row_half": int(r > (H - 1) / 2),
            "col_half": int(c > (W - 1) / 2),
        }
    return feats


def search_separating_selector(train, mk):
    """Find a single feature predicate that separates oracle-consumed from non-consumed markers across
    ALL train pairs. Returns (feature_name, rule_desc, selector_fn) or (None, diagnostics)."""
    # gather (features, label) per pair
    per_pair = []
    for p in train:
        panel = find_host_panel(p["input"])
        if panel is None:
            return None, {"error": "no_panel"}
        feats = marker_cell_features(p["input"], mk, panel)
        consumed = oracle_consumed_set(p["input"], p["output"], mk)
        per_pair.append({(cell): (fv, cell in consumed) for cell, fv in feats.items()})
    feature_names = ["comp_size", "degree", "is_endpoint", "on_border", "dist_panel", "dist_path",
                     "near_path_le1", "attached_to_object", "enclosed_by_path", "clear_ray_to_panel",
                     "row_half", "col_half", "quadrant"]
    diagnostics = {}
    for fn in feature_names:
        # categorical separation: value -> set of labels seen (across all pairs)
        val_labels = {}
        ok = True
        for pair in per_pair:
            for cell, (fv, lab) in pair.items():
                v = fv[fn]
                val_labels.setdefault(v, set()).add(lab)
        # separable if no value maps to BOTH labels
        conflicts = [v for v, labs in val_labels.items() if len(labs) > 1]
        consumed_vals = {v for v, labs in val_labels.items() if labs == {True}}
        diagnostics[fn] = {
            "separable": len(conflicts) == 0,
            "conflict_values": conflicts[:6],
            "consumed_values": sorted(consumed_vals, key=str)[:8],
        }
        if not conflicts:
            def selector(g, marker=mk, fname=fn, cvals=frozenset(consumed_vals)):
                panel = find_host_panel(g)
                if panel is None:
                    return set()
                feats = marker_cell_features(g, marker, panel)
                return {cell for cell, fv in feats.items() if fv[fname] in cvals}
            return (fn, f"consumed iff {fn} in {sorted(consumed_vals, key=str)}", selector), diagnostics

    # 2-feature conjunction pass (product key categorical separation)
    import itertools
    for f1, f2 in itertools.combinations(feature_names, 2):
        val_labels = {}
        for pair in per_pair:
            for cell, (fv, lab) in pair.items():
                key = (fv[f1], fv[f2])
                val_labels.setdefault(key, set()).add(lab)
        conflicts = [v for v, labs in val_labels.items() if len(labs) > 1]
        if not conflicts:
            consumed_keys = frozenset(v for v, labs in val_labels.items() if labs == {True})
            diagnostics[f"{f1}+{f2}"] = {"separable": True, "consumed_keys": list(consumed_keys)[:6]}

            def selector(g, marker=mk, fa=f1, fb=f2, ckeys=consumed_keys):
                panel = find_host_panel(g)
                if panel is None:
                    return set()
                feats = marker_cell_features(g, marker, panel)
                return {cell for cell, fv in feats.items() if (fv[fa], fv[fb]) in ckeys}
            return (f"{f1}+{f2}", f"consumed iff ({f1},{f2}) separates", selector), diagnostics
    diagnostics["_two_feature_search"] = "no_separating_pair"
    return None, diagnostics


# ----------------------------------------------------------------- gating
def train_exact(transform, train):
    for p in train:
        try:
            if not equal(transform(deepcopy(p["input"])), p["output"]):
                return False
        except Exception:
            return False
    return True


def loo_stable(fit_fn, train):
    """fit_fn(subset) -> transform or None. LOO: refit on n-1, must reproduce held pair exactly."""
    if len(train) <= 1:
        return True
    for i in range(len(train)):
        subset = [train[j] for j in range(len(train)) if j != i]
        t = fit_fn(subset)
        if t is None:
            return False
        try:
            if not equal(t(deepcopy(train[i]["input"])), train[i]["output"]):
                return False
        except Exception:
            return False
    return True


# --------------------------------------------- per-task: fill-panel-by-count synthesis + oracle ablation
def synth_fill_panel_by_count(train):
    """Returns a dict report: render expressible w/ oracle? selector LOO-stable? flip params."""
    report = {"family": "fill_panel_by_marker_count", "decomposition_ok": False,
              "render_oracle_exact": False, "selector": None, "selector_loo_stable": False,
              "train_exact": False}
    # decomposition: every train input must have a host panel + a marker colour
    panels = [find_host_panel(p["input"]) for p in train]
    if any(p is None for p in panels):
        report["decomposition_fail"] = "no_host_panel_in_some_pair"
        return report, None
    report["decomposition_ok"] = True

    mks = marker_color_candidates(train)
    for mk in mks:
        # ORACLE render: consumed set read from train output (input==marker & output==bg)
        oracle_ok = True
        oracle_counts = []
        for p, panel in zip(train, panels):
            consumed = oracle_consumed_set(p["input"], p["output"], mk)
            oracle_counts.append(len(consumed))
            if not equal(render_fill_panel(p["input"], panel, mk, consumed), p["output"]):
                oracle_ok = False
                break
        if not oracle_ok:
            continue
        report["render_oracle_exact"] = True
        report["marker_color"] = mk
        report["oracle_consumed_counts"] = oracle_counts

        # search input-only selectors that pick the EXACT consumed set
        for sname, sfn in consumed_marker_selectors():
            def make_transform(selfn=sfn, marker=mk):
                def t(grid):
                    panel = find_host_panel(grid)
                    if panel is None:
                        return norm(grid)
                    consumed = selfn(grid, marker, panel)
                    return render_fill_panel(grid, panel, marker, consumed)
                return t
            t = make_transform()
            if train_exact(t, train):
                report["train_exact"] = True
                report["selector"] = sname
                report["selector_loo_stable"] = loo_stable(lambda sub, mk=mk, sfn=sfn: make_transform(sfn, mk), train)
                return report, t

        # feature-separation search over the richer (Codex) vocabulary
        found, diagnostics = search_separating_selector(train, mk)
        report["feature_separability"] = diagnostics
        if found is not None:
            fname, rule, selector = found

            def make_feat_transform(sel=selector, marker=mk):
                def t(grid):
                    panel = find_host_panel(grid)
                    if panel is None:
                        return norm(grid)
                    return render_fill_panel(grid, panel, marker, sel(grid))
                return t
            tf = make_feat_transform()
            if train_exact(tf, train):
                report["train_exact"] = True
                report["selector"] = f"feature:{fname}"
                report["selector_rule"] = rule
                report["selector_loo_stable"] = loo_stable(
                    lambda sub: (lambda: search_separating_selector_transform(sub, mk))(), train)
                return report, tf
            report["selector"] = f"feature:{fname}_separable_but_not_train_exact"
            return report, None
        report["selector"] = "no_separating_feature"
        report["selector_vocabulary"] = [n for n, _ in consumed_marker_selectors()]
        return report, None
    report["render_oracle_fail"] = "no_marker_color_made_oracle_render_exact"
    return report, None


def search_separating_selector_transform(train, mk):
    """LOO helper: refit a separating selector on a subset and return its transform (or None)."""
    found, _ = search_separating_selector(train, mk)
    if found is None:
        return None
    _, _, selector = found

    def t(grid):
        panel = find_host_panel(grid)
        if panel is None:
            return norm(grid)
        return render_fill_panel(grid, panel, mk, selector(grid))
    return t


# ----------------- generic additions classifier (rigid-copy vs generated) for all families
def _d4_variants(cells, colors):
    """Yield (transformed_cells_relative, name) under the 8 dihedral symmetries (origin-normalized)."""
    pts = list(zip(cells, colors))
    forms = {
        "id": lambda r, c: (r, c), "rot90": lambda r, c: (c, -r), "rot180": lambda r, c: (-r, -c),
        "rot270": lambda r, c: (-c, r), "flip_h": lambda r, c: (r, -c), "flip_v": lambda r, c: (-r, c),
        "transpose": lambda r, c: (c, r), "anti": lambda r, c: (-c, -r),
    }
    for name, fn in forms.items():
        tp = [(fn(r, c), col) for (r, c), col in pts]
        rs = [p[0][0] for p in tp]
        cs = [p[0][1] for p in tp]
        mr, mc = min(rs), min(cs)
        normed = frozenset(((r - mr, c - mc), col) for (r, c), col in tp)
        yield normed, name


def _object_signature(o, g):
    g = norm(g)
    r0, c0, _, _ = o["bbox"]
    return frozenset(((r - r0, c - c0), g[r][c]) for r, c in o["cells"])


def classify_generative_structure(train):
    """For each pair: additions (bg->nonbg), erasures (nonbg->bg), recolors. Test if every added
    connected component is a D4 copy of some INPUT object (relocate/stamp) vs generated (draw/fill)."""
    per_pair = []
    for p in train:
        gi, go = norm(p["input"]), norm(p["output"])
        if shape(gi) != shape(go):
            per_pair.append({"shape_change": True})
            continue
        bg = background(gi)
        added = {(r, c): go[r][c] for r in range(len(gi)) for c in range(len(gi[0]))
                 if gi[r][c] == bg and go[r][c] != bg}
        erased = {(r, c) for r in range(len(gi)) for c in range(len(gi[0]))
                  if gi[r][c] != bg and go[r][c] == bg}
        recol = {(r, c): (gi[r][c], go[r][c]) for r in range(len(gi)) for c in range(len(gi[0]))
                 if gi[r][c] != bg and go[r][c] != bg and gi[r][c] != go[r][c]}
        # input object D4 signatures (relative)
        in_sigs = set()
        for o in components(gi):
            for form, _name in _d4_variants(o["cells"], [gi[r][c] for r, c in o["cells"]]):
                in_sigs.add(form)
        # connected components of the ADDED cells
        added_cells = set(added)
        seen = set()
        add_comps = []
        for cell in added_cells:
            if cell in seen:
                continue
            stack = [cell]
            seen.add(cell)
            comp = []
            while stack:
                r, c = stack.pop()
                comp.append((r, c))
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nb = (r + dr, c + dc)
                    if nb in added_cells and nb not in seen:
                        seen.add(nb)
                        stack.append(nb)
            add_comps.append(comp)
        # only MULTI-cell added components are meaningful copies (single cells are trivially invariant)
        multi = [comp for comp in add_comps if len(comp) >= 2]
        comps_are_copies = []
        for comp in multi:
            r0 = min(r for r, _ in comp)
            c0 = min(c for _, c in comp)
            normed = frozenset(((r - r0, c - c0), added[(r, c)]) for (r, c) in comp)
            comps_are_copies.append(normed in in_sigs)
        per_pair.append({
            "shape_change": False, "n_added": len(added), "n_erased": len(erased), "n_recolor": len(recol),
            "n_added_components": len(add_comps), "n_multi_cell_added_components": len(multi),
            "added_components_all_rigid_copies": bool(multi) and all(comps_are_copies),
            "frac_multicell_added_rigid": (sum(comps_are_copies) / len(multi)) if multi else None,
        })
    # aggregate classification
    if all(pp.get("shape_change") for pp in per_pair):
        cls = "shape_change"
    elif all((not pp["shape_change"]) and pp["n_added"] == 0 for pp in per_pair):
        cls = "erase_or_recolor_only"
    elif all((not pp["shape_change"]) and pp.get("added_components_all_rigid_copies") for pp in per_pair):
        cls = "additions_are_rigid_copies (relocate/stamp -> SELECTOR/anchor limited)"
    else:
        cls = "additions_generated (draw/fill -> needs generative primitive; RENDER-limited)"
    return {"classification": cls, "per_pair": per_pair}


# ---------------------------------- richer oracle ablations (Codex request): ray/segment & motif stamp
def _added_components(gi, go):
    gi, go = norm(gi), norm(go)
    bg = background(gi)
    added = {(r, c): go[r][c] for r in range(len(gi)) for c in range(len(gi[0]))
             if gi[r][c] == bg and go[r][c] != bg}
    cells = set(added)
    seen = set()
    comps = []
    for cell in cells:
        if cell in seen:
            continue
        stack = [cell]
        seen.add(cell)
        comp = []
        while stack:
            r, c = stack.pop()
            comp.append((r, c))
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                nb = (r + dr, c + dc)
                if nb in cells and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        comps.append(comp)
    return added, comps


def _is_straight_segment(comp):
    rs = sorted({r for r, _ in comp})
    cs = sorted({c for _, c in comp})
    if len(rs) == 1 or len(cs) == 1:
        return True
    # diagonal: r-c constant or r+c constant, and one cell per anti/main index
    if len({r - c for r, c in comp}) == 1 or len({r + c for r, c in comp}) == 1:
        return True
    return False


def oracle_segment_render_test(train):
    """Are ALL multi-cell added components straight segments (h/v/diag)? If so the render is
    'draw segments'; the unknowns are endpoints (-> SELECTOR/PARAMETER), not a missing RENDERER."""
    frac = []
    for p in train:
        if shape(p["input"]) != shape(p["output"]):
            return {"applicable": False}
        _added, comps = _added_components(p["input"], p["output"])
        multi = [c for c in comps if len(c) >= 2]
        if not multi:
            frac.append(None)
            continue
        frac.append(sum(1 for c in multi if _is_straight_segment(c)) / len(multi))
    vals = [f for f in frac if f is not None]
    return {"applicable": True, "frac_segments_per_pair": frac,
            "all_segments": bool(vals) and all(f == 1.0 for f in vals)}


def oracle_single_motif_stamp_test(train):
    """Is there a single recurring multi-cell added motif stamped at multiple anchors per pair? If so
    the render is 'stamp motif'; unknowns are anchors (-> SELECTOR), not a missing RENDERER."""
    per_pair = []
    for p in train:
        if shape(p["input"]) != shape(p["output"]):
            per_pair.append({"applicable": False})
            continue
        added, comps = _added_components(p["input"], p["output"])
        multi = [c for c in comps if len(c) >= 2]
        sigs = {}
        for comp in multi:
            r0 = min(r for r, _ in comp)
            c0 = min(c for _, c in comp)
            sig = frozenset(((r - r0, c - c0), added[(r, c)]) for (r, c) in comp)
            sigs[sig] = sigs.get(sig, 0) + 1
        dominant = max(sigs.values()) if sigs else 0
        per_pair.append({"applicable": True, "n_multi": len(multi), "n_distinct_motifs": len(sigs),
                         "dominant_motif_count": dominant})
    # single recurring motif iff few distinct shapes but many instances (require applicable pairs)
    applicable = [pp for pp in per_pair if pp.get("applicable")]
    single = bool(applicable) and all(pp["n_multi"] >= 2 and pp["n_distinct_motifs"] <= 2 for pp in applicable)
    return {"single_recurring_motif": single, "per_pair": per_pair}


def four_way_locus(task_result):
    """decomposition | selector | parameter | renderer."""
    fp = task_result["fill_panel_by_count"]
    gen = task_result["generative_structure"]
    seg = task_result["oracle_segment_render"]
    stamp = task_result["oracle_motif_stamp"]
    if task_result["flip_to_exact"]:
        return "NONE_FLIPPED"
    # fill-panel family fully applies and render works -> selector
    if fp.get("render_oracle_exact") and not fp.get("train_exact"):
        return "selector"
    # shape-change first: cannot parse to the right output canvas without an output-shape op
    if gen["classification"] == "shape_change":
        return "decomposition (shape-change; needs output-shape op + content render)"
    # recolor-aware: if recolors are significant, it is a mixed multi-op transform, not pure draw
    recol_total = sum(pp.get("n_recolor", 0) for pp in gen.get("per_pair", []) if not pp.get("shape_change"))
    add_total = sum(pp.get("n_added", 0) for pp in gen.get("per_pair", []) if not pp.get("shape_change"))
    recolor_heavy = recol_total > 0 and recol_total >= 0.5 * max(1, add_total)
    # additions are straight segments AND recolors are minor -> renderer exists (draw-segment); endpoints unknown
    if seg.get("applicable") and seg.get("all_segments") and not recolor_heavy:
        return "parameter (segment-draw renderer expressible; endpoints/anchor unknown)"
    if recolor_heavy:
        return "renderer (mixed-op: additions + significant recolors; multi-structure extend/recolor)"
    # additions are a single recurring stamped motif -> renderer exists; anchors unknown
    if stamp.get("single_recurring_motif"):
        return "selector (stamp renderer expressible; anchors unknown)"
    # additions are generated, not segments/copies/stamps -> renderer missing
    if "generated" in gen["classification"]:
        return "renderer (additions are generated structure; no segment/copy/stamp render reproduces them)"
    return "renderer"


# ----------------------------------------------------------------- main
def run_task(tid):
    task = json.loads((EVAL / f"{tid}.json").read_text())
    train, test = task["train"], task["test"]
    out = {"task_id": tid, "n_train": len(train)}
    rep, transform = synth_fill_panel_by_count(train)
    out["fill_panel_by_count"] = rep
    out["generative_structure"] = classify_generative_structure(train)
    out["oracle_segment_render"] = oracle_segment_render_test(train)
    out["oracle_motif_stamp"] = oracle_single_motif_stamp_test(train)
    flip = False
    if transform is not None and rep.get("train_exact"):
        tep = 0
        for p in test:  # readout only
            try:
                if equal(transform(deepcopy(p["input"])), p["output"]):
                    tep += 1
            except Exception:
                pass
        flip = tep == len(test)
        out["design_test_readout"] = f"{tep}/{len(test)}"
    out["flip_to_exact"] = flip
    out["failure_locus_4way"] = four_way_locus(out)  # decomposition | selector | parameter | renderer
    return out


def main():
    results = {"lane": "claude_relational_micro_synth", "targets": TARGETS, "tasks": []}
    for tid in TARGETS:
        r = run_task(tid)
        results["tasks"].append(r)
        rep = r["fill_panel_by_count"]
        print(f"{tid}: oracle_render={rep['render_oracle_exact']!s:5} flip={r['flip_to_exact']!s:5} "
              f"LOCUS = {r['failure_locus_4way']}")
    flips = [r["task_id"] for r in results["tasks"] if r["flip_to_exact"]]
    results["flips"] = flips
    (WORKSPACE / "tmp" / "claude_relational_synth_results.json").write_text(json.dumps(results, indent=2))
    print(f"\nflips: {flips}")
    print("wrote tmp/claude_relational_synth_results.json")


if __name__ == "__main__":
    main()
