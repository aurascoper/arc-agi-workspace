"""Build the quarantined SIA all-23 design-miss task split.

data/public/<tid>.json   = {"train": [...], "test": [{"input": ...}]}   # NO test outputs
data/private/<tid>.json  = {"test_outputs": [...]}                       # evaluator log-only

Run:
    ARC2_EVAL_DIR=/path/to/arc_agi_2_data/evaluation python3 build_task.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = Path(os.environ.get("ARC2_EVAL_DIR", HERE.parent / "arc_agi_2_data" / "evaluation"))
TARGETS = [
    "5dbc8537", "edb79dae", "dd6b8c4b", "88bcf3b4", "cb2d8a2c", "142ca369",
    "3dc255db", "195c6913", "36a08778", "4a21e3da", "16b78196", "446ef5d2",
    "7b0280bc", "abc82100", "d8e07eb2", "271d71e2", "faa9f03d", "35ab12c3",
    "20a9e565", "2d0172a1", "6ffbe589", "e87109e9", "89565ca0",
]


def main():
    (HERE / "data" / "public").mkdir(parents=True, exist_ok=True)
    (HERE / "data" / "private").mkdir(parents=True, exist_ok=True)
    for tid in TARGETS:
        task = json.loads((EVAL / f"{tid}.json").read_text())
        public = {"train": task["train"], "test": [{"input": t["input"]} for t in task["test"]]}
        private = {"test_outputs": [t["output"] for t in task["test"]]}
        (HERE / "data" / "public" / f"{tid}.json").write_text(json.dumps(public))
        (HERE / "data" / "private" / f"{tid}.json").write_text(json.dumps(private))
    print(f"wrote {len(TARGETS)} public train+test-input files and private log-only output files")


if __name__ == "__main__":
    main()
