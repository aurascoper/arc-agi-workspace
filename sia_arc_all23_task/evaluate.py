"""SIA-compatible evaluator entrypoint for the all-23 ARC task.

SIA calls this with `--gen-dir <runs/run_N/gen_M>`. We evaluate the generated
`target_agent.py` as a `propose(train) -> [(name, transform)]` agent using the
hardened quarantined all-23 evaluator, then write `results.json` into the gen
directory for SIA's feedback loop.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALUATOR = HERE / "evaluator.py"


def _load_evaluator():
    spec = importlib.util.spec_from_file_location("sia_all23_evaluator", EVALUATOR)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen-dir", required=True)
    args = ap.parse_args()
    gen_dir = Path(args.gen_dir).resolve()
    agent = gen_dir / "target_agent.py"
    evaluator = _load_evaluator()
    base = evaluator._load_base()
    if not agent.exists():
        result = {
            "status": "error",
            "fitness": -100.0,
            "reason": f"missing target agent: {agent}",
        }
    else:
        result = base.evaluate(agent)
        result["status"] = "success"
        result["task"] = "arc2_all23_sia"
        result["agent_path"] = str(agent)
    (gen_dir / "results.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
