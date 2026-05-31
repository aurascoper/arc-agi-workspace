"""ShapeFirstExecGuidedCEGIS — design-only research prototype (Claude lane).

Tests the "mixed coverage wall" hypothesis on DESIGN misses only. Standalone:
imports arc2_candidate_solver / run_pseudo_private_eval READ-ONLY, never edits them.

Hidden-safe by construction:
  - no task ids, no public-output templates, no train replay, no test-output use in synthesis
  - operators are learned only from train pairs; the design test pair is a READOUT, never a selection signal
  - gate = train_exact + leave-one-out (LOO); LOO is the real generalization evidence

Pieces:
  1. predict_output_shapes  — output shape from train I/O shape relations only
  2. learn_local_rule       — exact neighborhood->color rule (the bounded residual repair);
                              train-exact by construction when consistent, so LOO carries the signal
  3. cegis_repair           — try a bounded variant ladder, stop after K non-improving variants
  4. evaluate_family        — flip-to-exact by miss class, with a full regression guard

Run:  python3 arc2_shapefirst_cegis.py --out tmp/claude_cegis_results.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from copy import deepcopy
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKSPACE))

import run_pseudo_private_eval as RP  # noqa: E402
import arc2_candidate_solver as S  # noqa: E402

EVAL = WORKSPACE / "arc_agi_2_data" / "evaluation"

# Design exemplars per target family (frozen-calibration tasks EXCLUDED — count-only).
FAMILY_DESIGN_EXEMPLARS = {
    "ttt_sparse_patch_repair": ["dd6b8c4b", "88bcf3b4", "2b83f449", "8f3a5a89"],
    "sparse_line_endpoint_bridge": ["4a21e3da", "35ab12c3"],
    "crop_largest_object_with_border_cleanup": [
        "edb79dae", "142ca369", "36a08778", "16b78196",
        "446ef5d2", "db695cfb", "64efde09", "271d71e2",
    ],
    "output_shape_count_or_table_serialization": ["5dbc8537"],
}


# ----------------------------------------------------------------------------- grids
def norm(g):
    return S.normalize_grid(g)


def shape(g):
    g = norm(g)
    return (len(g), len(g[0]) if g else 0)


def diff_cells(a, b):
    a, b = norm(a), norm(b)
    if shape(a) != shape(b):
        return None
    return sum(a[r][c] != b[r][c] for r in range(len(a)) for c in range(len(a[0])))


def background_color(g):
    g = norm(g)
    return Counter(v for row in g for v in row).most_common(1)[0][0]


# ----------------------------------------------------------------- 1. shape predictor
def predict_output_shapes(train):
    """Predict the output shape from train I/O shape relations only. Returns a ranked
    list of (predicted_shape_fn_name, callable(input)->(H,W)). Design-only, no test use."""
    ins = [shape(p["input"]) for p in train]
    outs = [shape(p["output"]) for p in train]
    preds = []
    # same shape
    if all(i == o for i, o in zip(ins, outs)):
        preds.append(("same", lambda g: shape(g)))
    # constant output shape
    if len(set(outs)) == 1:
        c = outs[0]
        preds.append(("constant", lambda g, c=c: c))
    # integer tiling out = k*in
    ks = {(o[0] // i[0], o[1] // i[1]) for i, o in zip(ins, outs)
          if i[0] and i[1] and o[0] % i[0] == 0 and o[1] % i[1] == 0}
    if len(ks) == 1:
        kh, kw = next(iter(ks))
        if (kh, kw) != (1, 1):
            preds.append(("tile", lambda g, kh=kh, kw=kw: (shape(g)[0] * kh, shape(g)[1] * kw)))
    # crop to bbox of non-background (used by crop family); verify it reproduces train out shapes
    def bbox_shape(g):
        g = norm(g)
        bg = background_color(g)
        rs = [r for r in range(len(g)) for c in range(len(g[0])) if g[r][c] != bg]
        cs = [c for r in range(len(g)) for c in range(len(g[0])) if g[r][c] != bg]
        if not rs:
            return shape(g)
        return (max(rs) - min(rs) + 1, max(cs) - min(cs) + 1)
    if all(bbox_shape(p["input"]) == o for p, o in zip(train, outs)) and any(i != o for i, o in zip(ins, outs)):
        preds.append(("crop_bbox", bbox_shape))
    return preds


def shape_prediction_exact(train, test_input, test_output):
    """Does any shape predictor match the held-out test output shape? (readout metric)"""
    target = shape(test_output)
    for name, fn in predict_output_shapes(train):
        try:
            if fn(test_input) == target:
                return True, name
        except Exception:
            continue
    return False, None


# ------------------------------------------------- 2. local-rule residual repair (CEGIS core)
def _components(g, bg):
    """4-connected non-background components. Returns label grid + per-label info."""
    H, W = len(g), len(g[0])
    lab = [[-1] * W for _ in range(H)]
    info = {}
    nxt = 0
    for r in range(H):
        for c in range(W):
            if g[r][c] == bg or lab[r][c] != -1:
                continue
            stack = [(r, c)]
            lab[r][c] = nxt
            cells = []
            while stack:
                rr, cc = stack.pop()
                cells.append((rr, cc))
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, ncc = rr + dr, cc + dc
                    if 0 <= nr < H and 0 <= ncc < W and lab[nr][ncc] == -1 and g[nr][ncc] == g[r][c]:
                        lab[nr][ncc] = nxt
                        stack.append((nr, ncc))
            rs = [p[0] for p in cells]
            cs = [p[1] for p in cells]
            info[nxt] = {"size": len(cells), "color": g[r][c],
                         "bbox": (min(rs), min(cs), max(rs), max(cs))}
            nxt += 1
    ranks = {lab_id: i for i, (lab_id, _) in enumerate(
        sorted(info.items(), key=lambda kv: -kv[1]["size"]))}
    return lab, info, ranks


# ----- per-cell KEY BUILDERS (each: grid -> (cell -> hashable key)); translation-equivariant
def pixel_key_builder(radius, ring_counts=False):
    def build(g):
        H, W = len(g), len(g[0])
        def key(r, c):
            win = []
            for dr in range(-radius, radius + 1):
                for dc in range(-radius, radius + 1):
                    rr, cc = r + dr, c + dc
                    win.append(g[rr][cc] if 0 <= rr < H and 0 <= cc < W else -1)
            if ring_counts:
                cnt = Counter(v for v in win if v >= 0)
                win.append(tuple(sorted(cnt.items())))
            return tuple(win)
        return key
    return build


def relational_key_builder(use_rank=True, use_bbox_border=True, use_unique=True, with_n4=True):
    """Object/region features, no coordinates: own color, fg flag, component size-rank &
    color, on-component-bbox-border, count of same-color 4-neighbours, color-is-globally-unique."""
    def build(g):
        H, W = len(g), len(g[0])
        bg = Counter(v for row in g for v in row).most_common(1)[0][0]
        lab, info, ranks = _components(g, bg)
        colorcount = Counter(v for row in g for v in row)

        def key(r, c):
            v = g[r][c]
            feats = [v, int(v != bg)]
            lid = lab[r][c]
            if use_rank:
                feats.append(min(ranks.get(lid, -1), 6) if lid != -1 else -1)
            if lid != -1:
                feats.append(info[lid]["color"])
                if use_bbox_border:
                    r0, c0, r1, c1 = info[lid]["bbox"]
                    feats.append(int(r in (r0, r1) or c in (c0, c1)))
            else:
                feats.extend([-1] + ([0] if use_bbox_border else []))
            if with_n4:
                n4 = sum(1 for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))
                         if 0 <= r + dr < H and 0 <= c + dc < W and g[r + dr][c + dc] == v)
                feats.append(n4)
            if use_unique:
                feats.append(int(colorcount[v] == 1))
            return tuple(feats)
        return key
    return build


def learn_rule(train, key_builder):
    """Exact key->output-color lookup. Train-exact by construction when consistent; None if
    a key maps to >1 output color (the representation cannot express the transform)."""
    if not all(shape(p["input"]) == shape(p["output"]) for p in train):
        return None
    table = {}
    for p in train:
        gi, go = norm(p["input"]), norm(p["output"])
        keyf = key_builder(gi)
        for r in range(len(gi)):
            for c in range(len(gi[0])):
                k = keyf(r, c)
                val = go[r][c]
                if k in table and table[k] != val:
                    return None
                table[k] = val

    def transform(grid, table=table, key_builder=key_builder):
        g = norm(grid)
        H, W = len(g), len(g[0])
        out = [[g[r][c] for c in range(W)] for r in range(H)]
        keyf = key_builder(g)
        for r in range(H):
            for c in range(W):
                k = keyf(r, c)
                if k in table:
                    out[r][c] = table[k]
        return out

    return transform


# Two pre-registered mechanisms, each with its own 5-variant ladder and stop budget.
MECHANISMS = {
    "pixel_local": [
        ("R1", pixel_key_builder(1)),
        ("R1+ringcounts", pixel_key_builder(1, ring_counts=True)),
        ("R2", pixel_key_builder(2)),
        ("R2+ringcounts", pixel_key_builder(2, ring_counts=True)),
        ("R3", pixel_key_builder(3)),
    ],
    "relational": [
        ("rel_color_fg", relational_key_builder(use_rank=False, use_bbox_border=False, use_unique=False, with_n4=False)),
        ("rel_n4", relational_key_builder(use_rank=False, use_bbox_border=False, use_unique=False, with_n4=True)),
        ("rel_rank", relational_key_builder(use_rank=True, use_bbox_border=False, use_unique=True, with_n4=True)),
        ("rel_bbox", relational_key_builder(use_rank=True, use_bbox_border=True, use_unique=True, with_n4=True)),
        ("rel_full", relational_key_builder(use_rank=True, use_bbox_border=True, use_unique=True, with_n4=True)),
    ],
}


def cegis_repair(train, ladder, stop_after_noimprove=5):
    """Run one mechanism's variant ladder. Return (transform, variant, trace). Promote only
    train_exact + LOO. 'improving' = strictly lower total train residual. Stop after K non-improving."""
    best_resid = None
    noimprove = 0
    trace = []
    for vname, kb in ladder:
        t = learn_rule(train, kb)
        if t is None:
            trace.append({"variant": vname, "status": "inconsistent"})
            noimprove += 1
            if noimprove >= stop_after_noimprove:
                break
            continue
        train_exact, _ = S.train_transform_score(t, train)
        resid = sum(diff_cells(t(deepcopy(p["input"])), p["output"]) or 0 for p in train)
        loo = S.leave_one_out_validates(train, (lambda kb=kb: (lambda sub: learn_rule(sub, kb)))()) if train_exact else False
        trace.append({"variant": vname, "train_exact": train_exact, "train_residual": resid, "loo": loo})
        if train_exact and loo:
            return t, vname, trace
        if best_resid is None or resid < best_resid:
            best_resid, noimprove = resid, 0
        else:
            noimprove += 1
        if noimprove >= stop_after_noimprove:
            break
    return None, None, trace


# ------------------------------------------------------------------ 4. family evaluation
def classify_miss(train, baseline_best_resid):
    """shape-correct-small / shape-correct-medium / wrong-shape / finite-far / no-candidate."""
    same_shape = all(shape(p["input"]) == shape(p["output"]) for p in train)
    out_cells = sum(len(norm(p["output"])) * len(norm(p["output"])[0]) for p in train)
    if baseline_best_resid is None:
        return "no_finite_candidate"
    rho = baseline_best_resid / max(1, out_cells)
    if not same_shape:
        return "wrong_shape"
    if rho <= 0.10:
        return "shape_correct_small"
    if rho <= 0.30:
        return "shape_correct_medium"
    return "finite_far"


def baseline_candidate_residual(td, ns, task_id):
    """Best total same-shape train residual among baseline candidates (no exact exists)."""
    cands = S.generate_candidates(td, ns=ns, task_id=task_id)
    best = None
    for c in cands:
        tot = 0
        ok = True
        for p in td["train"]:
            try:
                d = diff_cells(c.transform(deepcopy(p["input"])), p["output"])
            except Exception:
                ok = False
                break
            if d is None:
                ok = False
                break
            tot += d
        if ok and (best is None or tot < best):
            best = tot
    return best, len(cands)


def evaluate_task(task_id, ns):
    task = json.loads((EVAL / f"{task_id}.json").read_text())
    train, test = task["train"], task["test"]
    td = {"train": train, "test": [{"input": test[0]["input"]}]}
    base_resid, ncand = baseline_candidate_residual(td, ns, f"probe_{task_id}")
    miss_class = classify_miss(train, base_resid)

    # shape prediction readout
    shape_ok = all(shape_prediction_exact(train, p["input"], p["output"])[0] for p in test)

    # CEGIS repair, one result per pre-registered mechanism (same-shape only).
    same_shape = all(shape(p["input"]) == shape(p["output"]) for p in train)
    mech_results = {}
    any_flip = False
    flip_mech = None
    for mech, ladder in MECHANISMS.items():
        if not same_shape:
            mech_results[mech] = {"promoted": False, "variant": None, "flip_to_exact": False,
                                  "trace": [{"skipped": "shape_change"}]}
            continue
        transform, variant, trace = cegis_repair(train, ladder)
        flip = False
        tep = 0
        if transform is not None:
            for p in test:  # readout ONLY; never a selection signal
                try:
                    if norm(transform(deepcopy(p["input"]))) == norm(p["output"]):
                        tep += 1
                except Exception:
                    pass
            flip = tep == len(test)
        mech_results[mech] = {"promoted": transform is not None, "variant": variant,
                              "flip_to_exact": flip,
                              "test_exact_pairs": f"{tep}/{len(test)}" if transform is not None else None,
                              "trace": trace}
        if flip:
            any_flip = True
            flip_mech = flip_mech or mech

    return {
        "task_id": task_id,
        "n_train": len(train),
        "n_test": len(test),
        "same_shape": same_shape,
        "baseline_best_train_residual": base_resid,
        "n_candidates": ncand,
        "miss_class": miss_class,
        "shape_predicted_correct": shape_ok,
        "flip_to_exact": any_flip,
        "flip_mechanism": flip_mech,
        "mechanisms": mech_results,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=WORKSPACE / "tmp" / "claude_cegis_results.json")
    ap.add_argument("--families", nargs="*", default=list(FAMILY_DESIGN_EXEMPLARS))
    args = ap.parse_args()

    RP.configure_hidden_environment()
    ns, removed = RP.build_namespace(scrub_task_solvers=True)
    print(f"hidden-faithful ns: {sum(1 for k in ns if k.startswith('solve_'))} generic solvers; "
          f"{len(removed)} task solvers scrubbed\n")

    results = {"by_family": {}, "by_class": Counter(), "flips_by_class": Counter()}
    t0 = time.time()
    for fam in args.families:
        fam_rows = []
        for tid in FAMILY_DESIGN_EXEMPLARS[fam]:
            row = evaluate_task(tid, ns)
            fam_rows.append(row)
            results["by_class"][row["miss_class"]] += 1
            if row["flip_to_exact"]:
                results["flips_by_class"][row["miss_class"]] += 1
            px = row["mechanisms"]["pixel_local"]["variant"] if row["same_shape"] else "-"
            rel = row["mechanisms"]["relational"]["variant"] if row["same_shape"] else "-"
            print(f"  [{fam}] {tid}: class={row['miss_class']:20} shape_ok={row['shape_predicted_correct']!s:5} "
                  f"pixel={px or '-':8} rel={rel or '-':10} flip={row['flip_to_exact']} ({row['flip_mechanism'] or ''})")
        flips = sum(1 for r in fam_rows if r["flip_to_exact"])
        results["by_family"][fam] = {
            "n_design_tasks": len(fam_rows),
            "flips_to_exact": flips,
            "shape_pred_correct": sum(1 for r in fam_rows if r["shape_predicted_correct"]),
            "closes_ge2_design": flips >= 2,
            "tasks": fam_rows,
        }
        print(f"  => {fam}: {flips}/{len(fam_rows)} design flips-to-exact; "
              f"shape_pred {results['by_family'][fam]['shape_pred_correct']}/{len(fam_rows)}\n")

    results["by_class"] = dict(results["by_class"])
    results["flips_by_class"] = dict(results["flips_by_class"])
    results["wall_time_sec"] = round(time.time() - t0, 1)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2))
    print(f"flip-to-exact by class: {results['flips_by_class']} of {results['by_class']}")
    print(f"wrote {args.out}  ({results['wall_time_sec']}s)")


if __name__ == "__main__":
    main()
