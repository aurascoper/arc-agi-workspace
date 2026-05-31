"""Reference wrapper for the all-23 SIA task.

The real seed is the self-contained full-library agent in
`../sia_arc_shape_task/strong_seed_agent.py`. This wrapper keeps the all-23 task
lightweight while making the default evaluator command work. For a SIA run, copy
or point the target template at `strong_seed_agent.py` if the loop expects a
single mutable file.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

SEED = Path(__file__).resolve().parents[1] / "sia_arc_shape_task" / "strong_seed_agent.py"
spec = importlib.util.spec_from_file_location("strong_seed_agent", SEED)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def propose(train):
    return mod.propose(train)
