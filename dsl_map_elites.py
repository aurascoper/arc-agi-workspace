#!/usr/bin/env python3
"""
dsl_map_elites.py — MAP-Elites archive for DSL function diversity.

Maintains a 2D archive indexed by (hypothesis_type, grid_size_bin).
Each cell stores the best-scoring DSL function for that behavioral niche.

Based on Mouret & Clune (2015) "Illuminating search spaces by mapping elites"
and Lehman et al. (2022) "Evolution through Large Models" (ELM).
"""

import json
import re
import time
from collections import defaultdict
from pathlib import Path

ARCHIVE_PATH = Path(__file__).resolve().parent / "evolution_results" / "map_elites_dsl.json"

# Hypothesis type keywords (mirrors evolve_qwen_arc.py)
HYPOTHESIS_TYPE_KEYWORDS = {
    "symmetry": ["symmetr", "mirror", "reflect", "flip"],
    "flood_fill": ["flood", "fill", "paint", "region"],
    "connected_components": ["connect", "component", "object", "blob", "segment"],
    "color_logic": ["color", "palette", "histogram", "frequency", "recolor"],
    "spatial_relation": ["spatial", "relation", "adjacen", "neighbor", "touching"],
    "pattern_tile": ["pattern", "tile", "repeat", "stamp", "template", "period"],
    "transform_geom": ["rotate", "scale", "resize", "crop", "translate", "shift", "gravity"],
    "grid_decompose": ["decompos", "split", "quadrant", "strip", "partition"],
    "topology": ["topology", "layer", "occlu", "z_order", "stack"],
    "counting_arithmetic": ["count", "arith", "sum", "multiply", "sort", "rank"],
    "boundary_edge": ["boundar", "edge", "border", "contour", "outline"],
    "masking_boolean": ["mask", "boolean", "xor", "intersection", "union", "overlay"],
}

GRID_SIZE_BINS = ["small", "medium", "large"]  # <=5, 6-15, 16-30


def classify_type(name: str, code: str = "") -> str:
    """Classify a function by hypothesis type based on name + code keywords."""
    text = (name + " " + code).lower()
    best_type, best_count = "other", 0
    for htype, keywords in HYPOTHESIS_TYPE_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > best_count:
            best_type, best_count = htype, hits
    return best_type


def classify_grid_size(code: str) -> str:
    """Heuristic: classify which grid sizes a function targets.

    Looks for size-related constants and patterns in code.
    """
    text = code.lower()
    # Look for size checks or constants
    small_indicators = ["1x1", "2x2", "3x3", "4x4", "5x5", "< 6", "<= 5", "small"]
    large_indicators = ["16", "20", "25", "30", "> 15", ">= 16", "large"]

    small_hits = sum(1 for s in small_indicators if s in text)
    large_hits = sum(1 for s in large_indicators if s in text)

    if small_hits > large_hits:
        return "small"
    elif large_hits > small_hits:
        return "large"
    return "medium"  # default — most functions work on medium grids


class DSLMapElites:
    """MAP-Elites archive for DSL functions."""

    def __init__(self, path: Path = ARCHIVE_PATH):
        self.path = path
        # Key: (hypothesis_type, grid_size_bin) -> dict with func info
        self.archive: dict[tuple[str, str], dict] = {}
        self._load()

    def _load(self):
        """Load archive from disk."""
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
            for entry in data.get("cells", []):
                key = (entry["hypothesis_type"], entry["grid_size_bin"])
                self.archive[key] = entry
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self):
        """Save archive to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        cells = list(self.archive.values())
        self.path.write_text(json.dumps({"cells": cells, "updated": time.time()}, indent=2))

    def update(self, func_name: str, code: str, score: float,
               metadata: dict = None) -> bool:
        """Insert a function if it's the best for its cell.

        Returns True if the cell was updated (new or improved).
        """
        htype = classify_type(func_name, code)
        gsize = classify_grid_size(code)
        key = (htype, gsize)

        existing = self.archive.get(key)
        if existing is None or score > existing["score"]:
            self.archive[key] = {
                "hypothesis_type": htype,
                "grid_size_bin": gsize,
                "func_name": func_name,
                "code": code[:2000],  # truncate for storage
                "score": score,
                "timestamp": time.time(),
                "metadata": metadata or {},
            }
            self._save()
            return True
        return False

    def get_empty_cells(self) -> list[tuple[str, str]]:
        """Return all (hypothesis_type, grid_size_bin) pairs with no entry."""
        all_types = list(HYPOTHESIS_TYPE_KEYWORDS.keys()) + ["other"]
        empty = []
        for htype in all_types:
            for gsize in GRID_SIZE_BINS:
                if (htype, gsize) not in self.archive:
                    empty.append((htype, gsize))
        return empty

    def get_weak_cells(self, threshold: float = 0.5) -> list[tuple[str, str, float]]:
        """Return cells with score below threshold."""
        weak = []
        for key, entry in self.archive.items():
            if entry["score"] < threshold:
                weak.append((key[0], key[1], entry["score"]))
        return weak

    def coverage_report(self) -> str:
        """Generate a human-readable coverage report."""
        all_types = list(HYPOTHESIS_TYPE_KEYWORDS.keys()) + ["other"]
        lines = ["MAP-Elites DSL Coverage:"]
        lines.append(f"  {'Type':<25} {'small':>8} {'medium':>8} {'large':>8}")
        lines.append("  " + "-" * 51)
        for htype in all_types:
            cells = []
            for gsize in GRID_SIZE_BINS:
                entry = self.archive.get((htype, gsize))
                if entry:
                    cells.append(f"{entry['score']:.2f}")
                else:
                    cells.append("  ---")
            lines.append(f"  {htype:<25} {cells[0]:>8} {cells[1]:>8} {cells[2]:>8}")

        filled = len(self.archive)
        total = len(all_types) * len(GRID_SIZE_BINS)
        lines.append(f"\n  Coverage: {filled}/{total} cells ({filled/total:.0%})")
        return "\n".join(lines)

    def format_gaps_for_prompt(self, max_gaps: int = 5) -> str:
        """Format empty/weak cells as prompt guidance for the LLM.

        Prioritizes empty cells, then weak cells.
        """
        empty = self.get_empty_cells()
        weak = self.get_weak_cells(threshold=0.5)

        if not empty and not weak:
            return ""

        lines = ["## MAP-Elites COVERAGE GAPS — prioritize filling these niches:"]

        shown = 0
        for htype, gsize in empty[:max_gaps]:
            keywords = ", ".join(HYPOTHESIS_TYPE_KEYWORDS.get(htype, ["general"])[:3])
            lines.append(f"  EMPTY [{htype} x {gsize}]: No function exists for {keywords} "
                         f"on {gsize} grids. Propose one!")
            shown += 1

        for htype, gsize, score in sorted(weak, key=lambda x: x[2])[:max_gaps - shown]:
            if shown >= max_gaps:
                break
            lines.append(f"  WEAK [{htype} x {gsize}]: Current best scores only {score:.2f}. "
                         f"Can you improve it?")
            shown += 1

        lines.append(f"  ({len(empty)} empty + {len(weak)} weak out of "
                     f"{(len(HYPOTHESIS_TYPE_KEYWORDS) + 1) * len(GRID_SIZE_BINS)} total cells)")
        return "\n".join(lines)

    def seed_from_dsl(self, dsl_path: Path, default_score: float = 0.5):
        """Bootstrap the archive from existing DSL functions.

        Scans dsl.py for function definitions and classifies each one.
        """
        try:
            code = dsl_path.read_text()
        except OSError:
            return 0

        # Extract individual functions
        pattern = re.compile(
            r'^(def (\w+)\s*\([^)]*\).*?(?=\ndef |\Z))',
            re.MULTILINE | re.DOTALL
        )

        count = 0
        for match in pattern.finditer(code):
            func_code = match.group(1)
            func_name = match.group(2)
            if func_name.startswith("_"):
                continue
            if self.update(func_name, func_code, default_score):
                count += 1

        return count


# Module-level singleton
_map_elites: DSLMapElites | None = None


def get_map_elites() -> DSLMapElites:
    """Get or create the module-level MAP-Elites singleton."""
    global _map_elites
    if _map_elites is None:
        _map_elites = DSLMapElites()
    return _map_elites
