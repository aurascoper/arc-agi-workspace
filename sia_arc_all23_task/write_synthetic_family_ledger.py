"""Write a structured ledger for synthetic-family method-track evidence.

This is a coordination artifact. It summarizes which synthetic families are
usable only as method evidence, which are not ledger-safe, and whether anything
creates live-solver work. It deliberately does not import generator code or
promote candidates.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


WORKSPACE = Path(__file__).resolve().parent.parent
OUT = WORKSPACE / "tmp" / "synthetic_family_ledger_latest.json"


def load_json(rel: str) -> dict:
    path = WORKSPACE / rel
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        return {"_error": repr(exc)}


def latest_download(watch: dict, family: str) -> dict | None:
    downloads = watch.get("downloads", {}) or {}
    row = downloads.get(family, {}) if isinstance(downloads, dict) else {}
    return row.get("latest") if isinstance(row, dict) else None


def template_match_entry(watch: dict, review: dict) -> dict:
    latest = latest_download(watch, "template_match_role_recolor")
    align = watch.get("template_match_review_alignment", {}) or {}
    findings = review.get("findings", []) or []
    if not latest:
        status = "pending_generator"
    elif not align.get("latest_is_reviewed"):
        status = "needs_review"
    elif review.get("verdict") == "passes_review":
        status = "ledger_candidate_method_only"
    else:
        status = "not_ledger_safe"
    blockers = [
        {
            "name": row.get("name"),
            "axis": row.get("axis"),
            "admitted_tasks": row.get("admitted_tasks"),
            "fix": row.get("fix"),
        }
        for row in findings
    ]
    deferred = [
        {
            "name": row.get("name"),
            "axis": row.get("axis"),
            "admitted_tasks": row.get("admitted_tasks"),
            "declared_scope": row.get("declared_scope"),
            "future_fix": row.get("fix"),
        }
        for row in (review.get("deferred_survivors", []) or [])
    ]
    if blockers:
        next_action = "Fix blocking synthetic-review findings: " + ", ".join(
            f"{row['name']} ({row.get('fix')})" for row in blockers
        )
    elif status == "needs_review":
        next_action = "Run review_template_match_role_recolor.py before using template-match evidence."
    elif status == "ledger_candidate_method_only":
        next_action = (
            "Eligible for method/generalization-ledger discussion only; still not live Kaggle evidence. "
            "Document deferred surfaces before any scoped ledger entry."
        )
    else:
        next_action = "Wait for a new template-match generator or method-track instruction."
    return {
        "family": "template_match_role_recolor",
        "status": status,
        "live_solver_effect": "none",
        "latest_generator": latest,
        "review": {
            "artifact": "tmp/template_match_role_recolor_latest_review.json",
            "generated_cdt": review.get("generated_cdt"),
            "verdict": review.get("verdict"),
            "oracle_mismatches": review.get("oracle_mismatches"),
            "admitted_counts": review.get("admitted_counts", {}),
            "review_scope": review.get("review_scope", {}),
        },
        "review_alignment": align,
        "blockers": blockers,
        "deferred_survivors": deferred,
        "next_required_action": next_action,
        "notes": [
            "Method-track only; derived from 7b0280bc-class ideas and not live Kaggle evidence.",
            "A pass here would still require separate live candidate gates before solver integration.",
        ],
    }


def count_marked_entry(watch: dict) -> dict:
    latest = latest_download(watch, "count_marked_objects")
    status = "external_method_shipped_unverified_by_codex" if latest else "pending_generator"
    return {
        "family": "count_marked_objects",
        "status": status,
        "live_solver_effect": "none",
        "latest_generator": latest,
        "review": {
            "artifact": None,
            "verdict": "reported_shipped_by_claude_v5" if latest else None,
        },
        "blockers": [],
        "scope_limits_reported": [
            "region-grow/category-c: objects-in-margin not certified",
            "N>7 tail not certified",
            "object-size>6 tail not certified",
        ] if latest else [],
        "next_required_action": (
            "No live action. If this family becomes admission-critical, add a Codex cold-review artifact "
            "similar to template_match_role_recolor."
        ),
        "notes": [
            "Mailbox reports v5 shipped to the scoped generalization ledger.",
            "Codex has fingerprinted the generator but has not added an independent count-family reviewer.",
        ],
    }


def live_solver_entry(sentinel: dict, sia_policy: dict) -> dict:
    ready = sentinel.get("integration_ready", []) or []
    manual = sentinel.get("manual_review_candidates", []) or []
    parked = sentinel.get("parked_candidates", []) or []
    return {
        "family": "live_solver_candidates",
        "status": "action_required" if ready or manual else "no_live_work",
        "integration_ready": ready,
        "manual_review_candidates": manual,
        "parked_candidates": parked,
        "sia_policy": {
            "recommendation": sia_policy.get("recommendation"),
            "sia_worker_expected": sia_policy.get("sia_worker_expected"),
            "exhausted_flat_targets": sia_policy.get("exhausted_flat_targets", []),
            "admissible_signal_targets": sia_policy.get("admissible_signal_targets", []),
        },
        "next_required_action": (
            "Manually verify integration-ready/manual-review candidates before any live solver change."
            if ready or manual
            else "No live integration. Keep verifier running and wait for a new generator/candidate."
        ),
    }


def main() -> None:
    now = datetime.now(ZoneInfo("America/Chicago"))
    watch = load_json("tmp/claude_artifact_watch_latest.json")
    review = load_json("tmp/template_match_role_recolor_latest_review.json")
    sentinel = load_json("tmp/codex_sia_all23_sentinel.json")
    sia_policy = load_json("tmp/sia_search_policy_latest.json")
    entries = [
        template_match_entry(watch, review),
        count_marked_entry(watch),
        live_solver_entry(sentinel, sia_policy),
    ]
    out = {
        "artifact": "synthetic_family_ledger_latest",
        "generated_cdt": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "entries": entries,
        "summary": {
            "live_integration_ready": bool((sentinel.get("integration_ready", []) or []) or (sentinel.get("manual_review_candidates", []) or [])),
            "template_latest_reviewed": (watch.get("template_match_review_alignment", {}) or {}).get("latest_is_reviewed"),
            "template_status": entries[0]["status"],
            "count_marked_status": entries[1]["status"],
            "sia_recommendation": sia_policy.get("recommendation"),
        },
        "notes": [
            "Generalization-ledger evidence is separate from live Kaggle solver evidence.",
            "This ledger is for coordination; it does not execute generators or admit candidates.",
        ],
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(
        f"wrote {OUT.relative_to(WORKSPACE)} "
        f"template={entries[0]['status']} live={entries[2]['status']}"
    )


if __name__ == "__main__":
    main()
