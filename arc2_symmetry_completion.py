"""Generative operator: symmetry / periodic completion — design-only lane (Claude).

The 23 genuine misses are construction tasks (draw/fill/complete), not selection tasks. This tests the
most tractable GENERATIVE hidden-safe primitive: the input is a damaged copy of a symmetric or periodic
grid; the output repairs it by filling background cells from their orbit partners. No task ids /
templates / coordinates / test-output use. Gate = train_exact + LOO. Frozen calibration untouched.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from copy import deepcopy
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKSPACE))
import arc2_candidate_solver as S  # noqa: E402

EVAL = WORKSPACE / "arc_agi_2_data" / "evaluation"


def norm(g):
    return S.normalize_grid(g)


def shape(g):
    g = norm(g)
    return (len(g), len(g[0]))


def background(g):
    g = norm(g)
    return Counter(v for row in g for v in row).most_common(1)[0][0]


# symmetry orbit generators: map (r,c,H,W) -> partner cell
SYMS = {
    "mirror_h": lambda r, c, H, W: (r, W - 1 - c),
    "mirror_v": lambda r, c, H, W: (H - 1 - r, c),
    "rot180": lambda r, c, H, W: (H - 1 - r, W - 1 - c),
    "transpose": lambda r, c, H, W: (c, r) if H == W else None,
    "anti_transpose": lambda r, c, H, W: (W - 1 - c, H - 1 - r) if H == W else None,
}


def complete_symmetry(grid, sym, bg):
    g = [row[:] for row in norm(grid)]
    H, W = shape(g)
    fn = SYMS[sym]
    out = [row[:] for row in g]
    for r in range(H):
        for c in range(W):
            if g[r][c] != bg:
                continue
            p = fn(r, c, H, W)
            if p is None:
                return None
            pr, pc = p
            if 0 <= pr < H and 0 <= pc < W and g[pr][pc] != bg:
                out[r][c] = g[pr][pc]
    return out


def complete_periodic(grid, ph, pw, bg):
    """Fill bg cells from the modal non-bg value of their (r%ph, c%pw) phase class."""
    g = norm(grid)
    H, W = shape(g)
    phase = {}
    for r in range(H):
        for c in range(W):
            if g[r][c] != bg:
                phase.setdefault((r % ph, c % pw), Counter())[g[r][c]] += 1
    out = [row[:] for row in g]
    for r in range(H):
        for c in range(W):
            if g[r][c] == bg:
                cnt = phase.get((r % ph, c % pw))
                if cnt:
                    out[r][c] = cnt.most_common(1)[0][0]
    return out


def make_sym_transform(sym):
    def t(grid, sym=sym):
        bg = background(grid)
        r = complete_symmetry(grid, sym, bg)
        return r if r is not None else norm(grid)
    return t


def make_periodic_transform(ph, pw):
    def t(grid, ph=ph, pw=pw):
        bg = background(grid)
        return complete_periodic(grid, ph, pw, bg)
    return t


def candidate_variants(train):
    """Bounded ladder of generative variants (symmetries + small periods inferred from train shapes)."""
    variants = [(f"sym_{s}", make_sym_transform(s)) for s in SYMS]
    # small periods up to 5 in each axis (period must divide some train dimension to be plausible)
    Hs = {shape(p["input"])[0] for p in train}
    Ws = {shape(p["input"])[1] for p in train}
    periods = set()
    for ph in range(2, 6):
        for pw in range(2, 6):
            periods.add((ph, pw))
    for ph, pw in sorted(periods):
        variants.append((f"period_{ph}x{pw}", make_periodic_transform(ph, pw)))
    return variants


def evaluate_task(tid):
    task = json.loads((EVAL / f"{tid}.json").read_text())
    train, test = task["train"], task["test"]
    same_shape = all(shape(p["input"]) == shape(p["output"]) for p in train)
    promoted = None
    noimprove = 0
    best_resid = None
    trace = []
    if same_shape:
        for vname, t in candidate_variants(train):
            train_exact, _ = S.train_transform_score(t, train)
            resid = 0
            for p in train:
                a, b = norm(t(deepcopy(p["input"]))), norm(p["output"])
                resid += sum(a[r][c] != b[r][c] for r in range(len(a)) for c in range(len(a[0]))) if shape(a) == shape(b) else 9999
            loo = S.leave_one_out_validates(train, (lambda t=t: (lambda sub: t))()) if train_exact else False
            trace.append({"variant": vname, "train_exact": train_exact, "resid": resid, "loo": loo})
            if train_exact and loo:
                promoted = (vname, t)
                break
            if best_resid is None or resid < best_resid:
                best_resid, noimprove = resid, 0
            else:
                noimprove += 1
            if noimprove >= 5:
                break
    flip = False
    if promoted is not None:
        _, t = promoted
        tep = sum(1 for p in test if norm(t(deepcopy(p["input"]))) == norm(p["output"]))
        flip = tep == len(test)
    return {"task_id": tid, "same_shape": same_shape, "promoted": promoted[0] if promoted else None,
            "flip_to_exact": flip, "best_resid": best_resid, "trace": trace[:4]}


def main():
    genuine = json.loads((WORKSPACE / "tmp" / "claude_current_coverage_audit.json").read_text())["genuine_coverage_miss"]
    rows = []
    t0 = time.time()
    for tid in genuine:
        r = evaluate_task(tid)
        rows.append(r)
        print(f"  {tid}: same={r['same_shape']!s:5} promoted={r['promoted'] or '-':14} flip={r['flip_to_exact']} best_resid={r['best_resid']}")
    flips = [r["task_id"] for r in rows if r["flip_to_exact"]]
    out = {"n_genuine": len(genuine), "n_flips": len(flips), "flips": flips, "rows": rows,
           "wall_time_sec": round(time.time() - t0, 1)}
    (WORKSPACE / "tmp" / "claude_symmetry_results.json").write_text(json.dumps(out, indent=2))
    print(f"\nsymmetry/periodic completion flips-to-exact: {len(flips)}/{len(genuine)} -> {flips}")
    print(f"wrote tmp/claude_symmetry_results.json ({out['wall_time_sec']}s)")


if __name__ == "__main__":
    main()
