#!/usr/bin/env python3
"""
program_archive.py — Go-Explore-style archive for ARC program synthesis.

Maintains a structured archive indexed by (task_id, score_bucket, transform_type).
Each cell stores the single best-scoring program. Selection weights favor
under-explored cells (novelty) while still preferring higher scores (quality).

Based on Ecoffet et al. "First return, then explore" (Nature 2021) adapted
for LLM-based program synthesis.
"""

import json
import random
import re
import time
from collections import defaultdict
from pathlib import Path

ARCHIVE_PATH = Path(__file__).resolve().parent / "evolution_results" / "program_archive.jsonl"
SCORE_BUCKETS = [0.0, 0.25, 0.5, 0.75, 0.9, 1.0]

# Reuse hypothesis type keywords from evolve_qwen_arc
TRANSFORM_TYPE_KEYWORDS = {
    "symmetry": ["symmetr", "mirror", "reflect", "flip"],
    "flood_fill": ["flood", "fill", "paint", "region"],
    "connected_components": ["connect", "component", "object", "blob", "segment"],
    "color_logic": ["color", "palette", "histogram", "frequency", "recolor"],
    "spatial_relation": ["spatial", "relation", "adjacen", "neighbor", "touching", "overlap"],
    "pattern_tile": ["pattern", "tile", "repeat", "stamp", "template", "period"],
    "transform_geom": ["rotate", "scale", "resize", "crop", "translate", "shift", "gravity", "drop"],
    "grid_decompose": ["decompos", "split", "quadrant", "strip", "partition", "separator"],
    "topology": ["topology", "layer", "occlu", "z_order", "stack"],
    "counting_arithmetic": ["count", "arith", "sum", "multiply", "sort", "rank"],
    "boundary_edge": ["boundar", "edge", "border", "contour", "outline", "perimete"],
    "masking_boolean": ["mask", "boolean", "xor", "intersection", "union", "overlay"],
}


def _score_bucket(score: float) -> float:
    """Discretize score into bucket."""
    for i in range(len(SCORE_BUCKETS) - 1):
        if score < SCORE_BUCKETS[i + 1]:
            return SCORE_BUCKETS[i]
    return SCORE_BUCKETS[-1]


def _classify_transform_type(code: str) -> str:
    """Classify program code into a transformation type by keyword matching."""
    text = code.lower()
    best_type, best_count = "other", 0
    for ttype, keywords in TRANSFORM_TYPE_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > best_count:
            best_type, best_count = ttype, hits
    return best_type


class ProgramArchive:
    """Go-Explore archive for program synthesis candidates."""

    def __init__(self, path: Path = ARCHIVE_PATH, max_cells: int = 10000):
        self.path = path
        self.max_cells = max_cells
        # Key: (task_id, score_bucket, transform_type) -> entry dict
        self.cells: dict[tuple, dict] = {}
        self.selection_counts: dict[tuple, int] = defaultdict(int)
        self._load()

    def _load(self):
        """Load archive from disk."""
        if not self.path.exists():
            return
        try:
            with open(self.path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        key = tuple(entry["cell_key"])
                        # Keep best score per cell
                        existing = self.cells.get(key)
                        if existing is None or entry["score"] > existing["score"]:
                            self.cells[key] = entry
                    except (json.JSONDecodeError, KeyError):
                        continue
        except OSError:
            pass

    def _append_to_disk(self, entry: dict):
        """Append a single entry to the archive file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _compact_if_needed(self):
        """Evict lowest-quality stale entries if over max_cells."""
        if len(self.cells) <= self.max_cells:
            return
        now = time.time()
        scored = []
        for key, entry in self.cells.items():
            age_days = (now - entry.get("timestamp", now)) / 86400
            decay = 0.95 ** age_days
            scored.append((key, entry["score"] * decay))
        scored.sort(key=lambda x: x[1])
        # Remove bottom 10%
        to_remove = len(scored) - self.max_cells
        for key, _ in scored[:to_remove]:
            del self.cells[key]
        # Rewrite archive file
        self._rewrite()

    def _rewrite(self):
        """Rewrite the archive file from current cells."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            for entry in self.cells.values():
                f.write(json.dumps(entry) + "\n")

    def update(self, task_id: str, score: float, code: str,
               metadata: dict = None):
        """Add or update an archive entry. Keeps best score per cell."""
        bucket = _score_bucket(score)
        ttype = _classify_transform_type(code)
        key = (task_id, bucket, ttype)
        existing = self.cells.get(key)

        if existing is None or score > existing["score"]:
            entry = {
                "cell_key": list(key),
                "task_id": task_id,
                "score": score,
                "score_bucket": bucket,
                "transform_type": ttype,
                "code": code,
                "timestamp": time.time(),
                "metadata": metadata or {},
            }
            self.cells[key] = entry
            self._append_to_disk(entry)
            self._compact_if_needed()
            return True
        return False

    def select(self, task_id: str, k: int = 3) -> list[dict]:
        """Select k diverse archive entries for a task using Go-Explore weighting.

        Weight = score * (1 / (selection_count + 1)) * (1 / (type_count + 1))
        This balances quality, novelty (under-explored), and diversity.
        """
        candidates = [
            (key, entry) for key, entry in self.cells.items()
            if key[0] == task_id
        ]
        if not candidates:
            return []

        # Count how many candidates share each transform type
        type_counts: dict[str, int] = defaultdict(int)
        for key, _ in candidates:
            type_counts[key[2]] += 1

        weights = []
        for key, entry in candidates:
            sel_count = self.selection_counts[key]
            w = entry["score"] + 0.1  # base quality (avoid zero)
            w *= 1.0 / (sel_count + 1)  # favor under-explored
            w *= 1.0 / (type_counts[key[2]])  # diversity bonus for rare types
            weights.append(max(w, 1e-6))

        selected = []
        remaining_indices = list(range(len(candidates)))
        remaining_weights = list(weights)

        for _ in range(min(k, len(candidates))):
            if not remaining_indices:
                break
            idx = random.choices(range(len(remaining_indices)),
                                 weights=remaining_weights, k=1)[0]
            real_idx = remaining_indices[idx]
            key, entry = candidates[real_idx]
            self.selection_counts[key] += 1
            selected.append(entry)
            remaining_indices.pop(idx)
            remaining_weights.pop(idx)

        return selected

    def get_near_solved(self, min_score: float = 0.5, max_score: float = 0.99) -> list[str]:
        """Return task IDs that have archive entries in the 'almost solved' range."""
        task_best: dict[str, float] = {}
        for key, entry in self.cells.items():
            tid = key[0]
            if entry["score"] > task_best.get(tid, 0):
                task_best[tid] = entry["score"]
        return [tid for tid, score in task_best.items()
                if min_score <= score <= max_score]

    def stats(self) -> dict:
        """Return summary statistics."""
        task_ids = set(k[0] for k in self.cells)
        types = defaultdict(int)
        for k in self.cells:
            types[k[2]] += 1
        return {
            "total_cells": len(self.cells),
            "unique_tasks": len(task_ids),
            "transform_types": dict(types),
            "score_distribution": {
                str(b): sum(1 for k in self.cells if k[1] == b)
                for b in SCORE_BUCKETS
            },
        }

    def format_for_prompt(self, task_id: str, k: int = 2) -> str:
        """Format selected archive entries as prompt context for beam search."""
        entries = self.select(task_id, k=k)
        if not entries:
            return ""
        lines = ["## Prior best attempts for this task (from archive):"]
        for i, e in enumerate(entries):
            lines.append(f"### Attempt {i+1} (score={e['score']:.2f}, type={e['transform_type']})")
            # Truncate code to keep prompt manageable
            code = e["code"]
            if len(code) > 1500:
                code = code[:1500] + "\n# ... (truncated)"
            lines.append(f"```python\n{code}\n```")
        lines.append("Build on or diverge from these approaches.")
        return "\n".join(lines)


# Module-level singleton for easy import
_archive: ProgramArchive | None = None


def get_archive() -> ProgramArchive:
    """Get or create the module-level archive singleton."""
    global _archive
    if _archive is None:
        _archive = ProgramArchive()
    return _archive
