"""Write a compact Claude-artifact watch artifact.

Claude often drops synthetic-family generators into ~/Downloads while Codex
reviews them from the repo. This watcher records the versioned files Codex can
see, hashes them, and checks whether the latest template-match generator is the
one currently reviewed. It is coordination-only and never imports or executes
unreviewed generator code.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


WORKSPACE = Path(__file__).resolve().parent.parent
DOWNLOADS = Path.home() / "Downloads"
OUT = WORKSPACE / "tmp" / "claude_artifact_watch_latest.json"
PATTERNS = {
    "template_match_role_recolor": "template_match_role_recolor_v*.py",
    "count_marked_objects": "count_marked_objects*v*.py",
}
WORKSPACE_ARTIFACTS = [
    "CLAUDE_TRACK_STATUS.md",
    "CLAUDE_TRACK_RESULTS.json",
    "arc2_relational_synth_report.md",
    "arc2_synthesis_architecture_plan.md",
    "tmp/claude_relational_synth_results.json",
    "tmp/claude_sketch_enumeration.json",
    "tmp/template_match_role_recolor_latest_review.json",
]


def version_key(path: Path) -> tuple[int, float, str]:
    match = re.search(r"_v(\d+)\.py$", path.name)
    version = int(match.group(1)) if match else -1
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (version, mtime, path.name)


def fingerprint(path: Path) -> dict:
    data = path.read_bytes()
    return {
        "name": path.name,
        "path": str(path),
        "version": version_key(path)[0],
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "mtime_cdt": datetime.fromtimestamp(path.stat().st_mtime, ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M:%S %Z"),
    }


def load_json(rel: str) -> dict:
    path = WORKSPACE / rel
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        return {"_error": repr(exc)}


def workspace_artifact(rel: str) -> dict:
    path = WORKSPACE / rel
    row = {"path": rel, "exists": path.exists()}
    if path.exists():
        row.update({
            "size_bytes": path.stat().st_size,
            "mtime_cdt": datetime.fromtimestamp(path.stat().st_mtime, ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M:%S %Z"),
        })
    return row


def main() -> None:
    now = datetime.now(ZoneInfo("America/Chicago"))
    downloads = {}
    for key, pattern in PATTERNS.items():
        files = [fingerprint(path) for path in sorted(DOWNLOADS.glob(pattern), key=version_key)]
        downloads[key] = {
            "pattern": str(DOWNLOADS / pattern),
            "count": len(files),
            "latest": files[-1] if files else None,
            "files": files,
        }

    review = load_json("tmp/template_match_role_recolor_latest_review.json")
    latest_template = downloads["template_match_role_recolor"]["latest"]
    review_alignment = {
        "latest_template_exists": latest_template is not None,
        "review_exists": bool(review),
        "latest_name": latest_template.get("name") if latest_template else None,
        "latest_version": latest_template.get("version") if latest_template else None,
        "latest_sha256": latest_template.get("sha256") if latest_template else None,
        "reviewed_name": review.get("generator_name"),
        "reviewed_version": review.get("generator_version"),
        "reviewed_sha256": review.get("generator_sha256"),
    }
    review_alignment["latest_is_reviewed"] = bool(
        latest_template
        and review
        and latest_template.get("name") == review.get("generator_name")
        and latest_template.get("sha256") == review.get("generator_sha256")
    )
    if latest_template and not review_alignment["latest_is_reviewed"]:
        review_alignment["action"] = "run review_template_match_role_recolor.py before using template-match evidence"
    elif latest_template:
        review_alignment["action"] = "latest template-match generator is reviewed"
    else:
        review_alignment["action"] = "no template-match generator visible"

    out = {
        "artifact": "claude_artifact_watch_latest",
        "generated_cdt": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "downloads": downloads,
        "workspace_artifacts": [workspace_artifact(rel) for rel in WORKSPACE_ARTIFACTS],
        "template_match_review_alignment": review_alignment,
        "notes": [
            "This watcher fingerprints Claude drop files but does not import or execute them.",
            "The template-match reviewer, not this watcher, performs the cold synthetic-family review.",
        ],
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(
        f"wrote {OUT.relative_to(WORKSPACE)} "
        f"template_latest={review_alignment['latest_name']} reviewed={review_alignment['latest_is_reviewed']}"
    )


if __name__ == "__main__":
    main()
