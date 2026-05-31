"""Typed sketch enumerator — design-only infrastructure (Claude lane), on top of arc2_object_graph.

The report's "sketch proposer" stage, as a deterministic enumerator (no learned model yet). It reads the
object-graph relations + shape profile of a task and emits a bounded, ranked list of TYPED SKETCH SKELETONS:
program templates with typed holes whose candidate bindings come from the object graph (roles, relations,
actions). It does NOT render task-specific rules and does NOT solve — it produces the search space a
downstream renderer/verifier would fill and gate. Pure, deterministic, design-only; no task ids / templates /
test-output use. Never edits Codex hot files.

A Sketch = (template, typed steps, typed holes with candidate bindings, heuristic prior). The point is to
turn the object-graph IR into a small typed search space instead of unconstrained enumeration.

Run: python3 arc2_typed_sketch_enumerator.py        # enumerates sketches for the 23 design misses
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKSPACE))
import arc2_object_graph as OG  # noqa: E402

EVAL = WORKSPACE / "arc_agi_2_data" / "evaluation"

# typed hole vocabularies (candidate fillers, NOT task-specific values)
ROLES = ["largest", "smallest", "unique_color", "most_holes", "unique_shape", "by_marker", "nth_in_reading"]
RELATIONS = ["host_marker", "contains", "contact", "row_aligned", "col_aligned", "same_color", "same_shape"]
ACTIONS = ["erase", "ray", "bracket", "fill_interior", "recolor", "crop", "stamp", "pack", "serialize"]
VIEWS = list(OG.PARSERS)


@dataclass
class Hole:
    name: str
    type: str
    candidates: list

    def __repr__(self):
        return f"{self.name}:{self.type}={self.candidates[:4]}{'…' if len(self.candidates) > 4 else ''}"


@dataclass
class Sketch:
    template: str
    steps: list           # typed op names (skeleton, no concrete rule)
    holes: list           # list[Hole]
    prior: float          # heuristic plausibility from the object graph
    view: str = "color"

    def as_dict(self):
        return {"template": self.template, "view": self.view, "prior": round(self.prior, 3),
                "steps": self.steps, "holes": {h.name: {"type": h.type, "n_candidates": len(h.candidates)} for h in self.holes}}


# ----------------------------------------------------------------- task features (input grids only)
def task_features(train):
    """Aggregate object-graph signals across train INPUTS (no outputs in synthesis features)."""
    rel_counts = Counter()
    view_objcount = Counter()
    has = Counter()
    for p in train:
        gi = p["input"]
        for v in VIEWS:
            objs = OG.PARSERS[v](gi)
            view_objcount[v] += len(objs)
            if v == "frames" and objs:
                has["frames"] += 1
            if v == "panels" and len(objs) >= 2:
                has["panels"] += 1
            if v == "holes" and objs:
                has["holes"] += 1
            if v == "lines" and objs:
                has["lines"] += 1
        og = OG.build_object_graph(gi, "color")
        for t, *_ in og.relations:
            rel_counts[t] += 1
    n = len(train)
    return {
        "n_train": n,
        "shape": OG.shape_profile(train),
        "rel_counts": rel_counts,
        "avg_objs": {v: view_objcount[v] / n for v in VIEWS},
        "has_frames": has["frames"] == n,
        "has_panels": has["panels"] == n,
        "has_holes": has["holes"] > 0,
        "has_lines": has["lines"] == n,
        "has_host_marker": rel_counts["host_marker"] > 0,
        "has_contact": rel_counts["contact"] > 0,
        "many_objs": view_objcount["color"] / n >= 4,
    }


# ----------------------------------------------------------------- templates (precondition -> sketches)
def t_marker_host_action(f):
    if not f["has_host_marker"]:
        return []
    return [Sketch("marker_host_action",
                   ["select(marker:ObjSet)", "bind(host:Obj via host_marker)", "derive(anchor:Point|Route from host)",
                    "action(a:Action on anchor)", "compose(overlay)"],
                   [Hole("marker_role", "Role", ROLES), Hole("host_relation", "Relation", ["host_marker", "contains"]),
                    Hole("anchor", "Point|Route", ["host_tip", "host_centroid", "contact_point", "bbox_edge"]),
                    Hole("a", "Action", ["erase", "ray", "bracket", "fill_interior", "recolor"])],
                   prior=0.6 + 0.1 * min(3, f["rel_counts"]["host_marker"]))]


def t_route_connect(f):
    if f["shape"]["shape_relation"] != "same" or not (f["has_contact"] or f["has_lines"]):
        return []
    return [Sketch("route_connect",
                   ["select(endpoints:ObjSet)", "pair(by:Relation)", "route(style:Action)", "draw(overlay)"],
                   [Hole("endpoint_role", "Role", ["by_marker", "unique_color", "nth_in_reading"]),
                    Hole("pairing", "Relation", ["same_color", "row_aligned", "col_aligned", "contact"]),
                    Hole("style", "Action", ["ray", "bracket", "orth_path"])],
                   prior=0.4 + 0.1 * f["has_lines"])]


def t_select_transform_place(f):
    if not f["many_objs"] or f["shape"]["shape_relation"] not in ("same", "grow"):
        return []
    return [Sketch("select_transform_place",
                   ["select(obj:Obj by Role)", "normalize", "transform(D4|scale)", "place(anchor:Point)", "stamp(overlay)"],
                   [Hole("sel", "Role", ROLES), Hole("xform", "Transform", ["id", "rot", "mirror", "scale", "outline"]),
                    Hole("place_anchor", "Point", ["marker", "hole_center", "frame_corner", "grid_origin"])],
                   prior=0.45)]


def t_panel_compose(f):
    if not f["has_panels"]:
        return []
    return [Sketch("panel_compose",
                   ["partition(panels)", "select|solve(panel:Region per-panel op)", "compose(layout)"],
                   [Hole("panel_role", "Role", ["unique_content", "largest", "by_marker", "all"]),
                    Hole("per_panel", "Action", ["crop", "recolor", "overlay", "serialize"]),
                    Hole("layout", "Layout", ["stack", "grid", "single", "interleave"])],
                   prior=0.5)]


def t_object_summary(f):
    if f["shape"]["shape_relation"] not in ("shrink", "constant") or not f["many_objs"]:
        return []
    return [Sketch("object_summary",
                   ["select(objs:ObjSet by Role)", "order(key)", "map(obj->cell|glyph)", "render(new_canvas)"],
                   [Hole("sel", "Role", ROLES), Hole("order", "Key", ["reading", "size", "color", "count"]),
                    Hole("cell_color", "ColorRule", ["object_color", "role_color", "count"]),
                    Hole("canvas_dims", "CanvasSpec", ["n_objs x 1", "1 x n_objs", "by_count", "by_role_count"])],
                   prior=0.5 + 0.05 * f["avg_objs"]["color"] / max(1, f["n_train"]))]


def t_frame_crop(f):
    if not f["has_frames"] or f["shape"]["shape_relation"] not in ("shrink", "same"):
        return []
    return [Sketch("frame_crop",
                   ["select(frame:Obj by Role)", "crop(interior:Region)", "optional(recolor/fill)"],
                   [Hole("frame_role", "Role", ["largest", "unique_color", "most_holes"]),
                    Hole("post", "Action", ["identity", "recolor", "fill_interior", "outline"])],
                   prior=0.45)]


def t_recolor_by_relation(f):
    if f["shape"]["shape_relation"] != "same":
        return []
    if not (f["rel_counts"]["same_shape"] or f["rel_counts"]["same_color"] or f["has_holes"]):
        return []
    return [Sketch("recolor_by_relation",
                   ["group(objs by Relation)", "assign(color per group via Rule)", "repaint(overlay)"],
                   [Hole("group_by", "Relation", ["same_shape", "same_color", "same_hole_count", "contact"]),
                    Hole("color_rule", "ColorRule", ["by_size_rank", "by_count", "by_role", "swap"])],
                   prior=0.35)]


TEMPLATES = [t_marker_host_action, t_route_connect, t_select_transform_place,
             t_panel_compose, t_object_summary, t_frame_crop, t_recolor_by_relation]


def enumerate_sketches(train, top=None):
    f = task_features(train)
    sketches = []
    for tmpl in TEMPLATES:
        sketches.extend(tmpl(f))
    sketches.sort(key=lambda s: -s.prior)
    return (sketches[:top] if top else sketches), f


# ----------------------------------------------------------------- validation
def main():
    audit = WORKSPACE / "tmp" / "claude_current_coverage_audit.json"
    tasks = json.loads(audit.read_text())["genuine_coverage_miss"] if audit.exists() \
        else [p.stem for p in sorted(EVAL.glob("*.json"))][:23]
    print(f"Enumerating typed sketch skeletons for {len(tasks)} design misses (object-graph driven, no rendering)\n")
    coverage = Counter()
    results = []
    for tid in tasks:
        task = json.loads((EVAL / f"{tid}.json").read_text())
        sketches, f = enumerate_sketches(task["train"])
        names = [s.template for s in sketches]
        for nm in names:
            coverage[nm] += 1
        results.append({"task_id": tid, "shape": f["shape"]["shape_relation"],
                        "n_sketches": len(sketches), "sketches": [s.as_dict() for s in sketches]})
        top = sketches[0] if sketches else None
        print(f"  {tid}: shape={f['shape']['shape_relation']:8} sketches={len(names):2} "
              f"top={top.template if top else '-'}({top.prior:.2f}) " if top else f"  {tid}: no sketches")
        print(f"           {[f'{s.template}:{s.prior:.2f}' for s in sketches]}")
    out = {"lane": "typed_sketch_enumerator", "n_tasks": len(tasks),
           "template_coverage": dict(coverage), "results": results}
    (WORKSPACE / "tmp" / "claude_sketch_enumeration.json").write_text(json.dumps(out, indent=2))
    avg = sum(r["n_sketches"] for r in results) / len(results)
    print(f"\ntemplate coverage (tasks where each fires): {dict(coverage.most_common())}")
    print(f"avg sketches/task: {avg:.1f} (bounded typed search space, not unconstrained enumeration)")
    print(f"tasks with >=1 sketch: {sum(1 for r in results if r['n_sketches'] > 0)}/{len(results)}")
    print("wrote tmp/claude_sketch_enumeration.json")


if __name__ == "__main__":
    main()
