"""Build the SIA task data split for the 7 shape-change ARC misses.

data/public/<tid>.json   = {"train": [...], "test": [{"input": ...}]}   # NO test outputs (agent sees this)
data/private/<tid>.json  = {"test_outputs": [...]}                       # held out; evaluator log-only

Run: python3 build_task.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = Path(os.environ.get("ARC2_EVAL_DIR", HERE.parent / "arc_agi_2_data" / "evaluation"))
TARGETS = ["5dbc8537", "edb79dae", "20a9e565", "2d0172a1", "6ffbe589", "e87109e9", "89565ca0"]


def main():
    (HERE / "data" / "public").mkdir(parents=True, exist_ok=True)
    (HERE / "data" / "private").mkdir(parents=True, exist_ok=True)
    for tid in TARGETS:
        task = json.loads((EVAL / f"{tid}.json").read_text())
        public = {"train": task["train"], "test": [{"input": t["input"]} for t in task["test"]]}
        private = {"test_outputs": [t["output"] for t in task["test"]]}
        (HERE / "data" / "public" / f"{tid}.json").write_text(json.dumps(public))
        (HERE / "data" / "private" / f"{tid}.json").write_text(json.dumps(private))
    print(f"wrote {len(TARGETS)} public (train+test-input) and private (test-output) splits")
    print("public has NO test outputs; the agent only ever sees data/public.")


if __name__ == "__main__":
    main()
