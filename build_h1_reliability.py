"""H1 — is the admission gate a calibrated predictor of hidden-test success?

For every promoted operator occurrence (train-exact, with a hidden test) we read
public_shadow_hits/total — i.e. did the gate-passing operator actually solve the
hidden pair. We group by EVIDENCE SIGNATURE and ask whether the realized hidden-hit
rate matches across the frozen split:

  predicted  = hidden-hit rate of a signature on the DESIGN split
  realized   = hidden-hit rate of the same signature on the CALIBRATION (frozen) split

A calibrated gate lands on the diagonal. Signature = (admission_type, loo±, synthetic
status). Outputs a table, a reliability-by-evidence bar chart, and a design-vs-frozen
scatter, plus a weighted calibration error.

Usage:
    python3 build_h1_reliability.py --design tmp/pp_design_strict_fixed.json \
                                    --calibration tmp/pp_cal_strict_fixed.json \
                                    --out-prefix reports/h1
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def wilson(hits: int, total: int, z: float = 1.96) -> tuple[float, float, float]:
    """(point, lo, hi) Wilson score interval for a binomial proportion."""
    if total == 0:
        return float("nan"), float("nan"), float("nan")
    p = hits / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    half = (z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))) / denom
    return p, max(0.0, center - half), min(1.0, center + half)


def signature(op: dict) -> str:
    at = op.get("admission_type", "?")
    if at == "fixed_transform":
        return f"fixed / {op.get('synthetic_invariance_status', '?')}"
    loo = "loo+" if op.get("loo_informative") else "loo-"
    syn = "syn+" if op.get("synthetic_self_consistency") else "syn-"
    return f"learned / {loo} {syn}"


def collect(path: Path) -> dict[str, list[tuple[int, int]]]:
    """signature -> list of (hits, total) over train-exact operator occurrences."""
    data = json.loads(path.read_text())
    buckets: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for r in data.get("tasks", []):
        for op in r.get("candidate_report", {}).get("operator_ledger", []):
            if not isinstance(op, dict) or not op.get("train_exact"):
                continue
            total = op.get("public_shadow_total") or 0
            if total <= 0:
                continue
            hits = op.get("public_shadow_hits") or 0
            buckets[signature(op)].append((int(hits), int(total)))
    return buckets


def agg(pairs: list[tuple[int, int]]) -> tuple[int, int, int]:
    hits = sum(h for h, _ in pairs)
    total = sum(t for _, t in pairs)
    return hits, total, len(pairs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", type=Path, required=True)
    ap.add_argument("--calibration", type=Path, required=True)
    ap.add_argument("--out-prefix", type=Path, default=Path("reports/h1"))
    args = ap.parse_args()
    args.out_prefix.parent.mkdir(parents=True, exist_ok=True)

    dz = collect(args.design)
    cz = collect(args.calibration)
    sigs = sorted(set(dz) | set(cz))

    print(f"\nH1 RELIABILITY — operator hidden-hit rate by evidence signature")
    print(f"{'signature':28} | {'design hits/tot (rate)':24} | {'calib hits/tot (rate)':24} | pooled [Wilson95]")
    rows = []
    for s in sigs:
        dh, dt, dn = agg(dz.get(s, []))
        ch, ct, cn = agg(cz.get(s, []))
        ph, pt = dh + ch, dt + ct
        p, lo, hi = wilson(ph, pt)
        drate = f"{dh}/{dt} ({dh/dt:.2f})" if dt else f"{dh}/0 (n/a)"
        crate = f"{ch}/{ct} ({ch/ct:.2f})" if ct else f"{ch}/0 (n/a)"
        print(f"{s:28} | {drate:24} | {crate:24} | {p:.2f} [{lo:.2f},{hi:.2f}] n_op={dn+cn}")
        rows.append((s, dh, dt, ch, ct, ph, pt, p, lo, hi, dn + cn))

    # weighted calibration error over signatures present in BOTH splits
    num = den = 0.0
    for s, dh, dt, ch, ct, *_ in rows:
        if dt and ct:
            num += ct * abs((dh / dt) - (ch / ct))
            den += ct
    ece = num / den if den else float("nan")
    print(f"\nWeighted calibration error (design->frozen, |pred-realized|): "
          f"{ece:.3f}" + ("" if den else "  (no signature present in both splits)"))

    # --- Plot 1: pooled realized hit-rate by signature with Wilson CI ---
    fig, ax = plt.subplots(figsize=(9, 4.5))
    labels = [r[0] for r in rows]
    pts = [r[7] for r in rows]
    los = [r[7] - r[8] for r in rows]
    his = [r[9] - r[7] for r in rows]
    ns = [r[10] for r in rows]
    x = range(len(rows))
    ax.bar(x, pts, color="#4C78A8")
    ax.errorbar(x, pts, yerr=[los, his], fmt="none", ecolor="black", capsize=4)
    for i, (p, n) in enumerate(zip(pts, ns)):
        ax.text(i, min(1.0, p + 0.04), f"n={n}", ha="center", fontsize=8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("realized hidden-hit rate (pooled)")
    ax.set_title("H1: operator hidden-hit rate by evidence signature (Wilson 95% CI)")
    fig.tight_layout()
    p1 = args.out_prefix.with_name(args.out_prefix.name + "_by_evidence.png")
    fig.savefig(p1, dpi=130)

    # --- Plot 2: design (predicted) vs calibration (realized) scatter ---
    fig2, ax2 = plt.subplots(figsize=(5.5, 5.5))
    ax2.plot([0, 1], [0, 1], "--", color="gray", lw=1, label="perfectly calibrated")
    for s, dh, dt, ch, ct, *_ in rows:
        if not (dt and ct):
            continue
        pred = dh / dt
        real = ch / ct
        _, lo, hi = wilson(ch, ct)
        ax2.errorbar([pred], [real], yerr=[[real - lo], [hi - real]], fmt="o",
                     ms=5 + math.sqrt(ct), capsize=3)
        ax2.annotate(s, (pred, real), fontsize=7, xytext=(4, 4), textcoords="offset points")
    ax2.set_xlim(-0.05, 1.05)
    ax2.set_ylim(-0.05, 1.05)
    ax2.set_xlabel("predicted = design-split hit rate")
    ax2.set_ylabel("realized = frozen calibration hit rate")
    ax2.set_title("H1 reliability: design vs frozen")
    ax2.legend(fontsize=8)
    fig2.tight_layout()
    p2 = args.out_prefix.with_name(args.out_prefix.name + "_design_vs_frozen.png")
    fig2.savefig(p2, dpi=130)
    print(f"\nWrote {p1}\nWrote {p2}")


if __name__ == "__main__":
    main()
