"""DSL Recognition Model — DreamCoder-style function relevance ranker.

Given failing ARC tasks, ranks DSL functions by relevance to include in
LLM prompts. Replaces naive sigs[-50:] with task-aware selection.

Stdlib-only. Cached index rebuilds automatically when dsl.py changes.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

RESULTS_DIR = Path(__file__).parent / "evolution_results"
INDEX_PATH = RESULTS_DIR / "dsl_function_index.json"
HYPOTHESIS_TYPES_FILE = RESULTS_DIR / "hypothesis_type_scores.json"
HYPOTHESES_FILE = RESULTS_DIR / "hypotheses.jsonl"

# Reuse the same keyword taxonomy from evolve_qwen_arc.py
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "symmetry": ["symmetr", "mirror", "reflect", "flip"],
    "flood_fill": ["flood", "fill", "paint", "region"],
    "connected_components": ["connect", "component", "object", "blob", "segment"],
    "color_logic": ["color", "palette", "histogram", "frequency", "recolor"],
    "spatial_relation": ["spatial", "relation", "adjacen", "neighbor", "touching", "overlap"],
    "pattern_tile": ["pattern", "tile", "repeat", "stamp", "template", "period"],
    "transform_geom": ["rotate", "scale", "resize", "crop", "translate", "shift", "gravity", "drop", "slide"],
    "grid_decompose": ["decompos", "split", "quadrant", "strip", "partition", "separator"],
    "topology": ["topology", "layer", "occlu", "z_order", "stack"],
    "counting_arithmetic": ["count", "arith", "sum", "multiply", "sort", "rank", "max", "min"],
    "boundary_edge": ["boundar", "edge", "border", "contour", "outline", "perimete"],
    "masking_boolean": ["mask", "boolean", "xor", "intersection", "union", "overlay"],
}

# Core functions always included regardless of score
CORE_FUNCTIONS = {
    "detect_background_color", "get_objects", "shape", "palette",
    "color_counts", "copy_grid", "rotate_cw", "mirror_h",
}

# Grid feature → category relevance mapping
FEATURE_CATEGORY_MAP: dict[str, list[tuple[str, float]]] = {
    "symmetry_h":           [("symmetry", 0.9), ("transform_geom", 0.4)],
    "symmetry_v":           [("symmetry", 0.9), ("transform_geom", 0.4)],
    "high_color_count":     [("color_logic", 0.8), ("counting_arithmetic", 0.5)],
    "color_delta":          [("color_logic", 0.7), ("masking_boolean", 0.5)],
    "many_objects":         [("connected_components", 0.9), ("spatial_relation", 0.7)],
    "size_change":          [("transform_geom", 0.8), ("pattern_tile", 0.6), ("grid_decompose", 0.4)],
    "has_border_frame":     [("boundary_edge", 0.9), ("grid_decompose", 0.5)],
    "has_repeating_pattern":[("pattern_tile", 0.9)],
    "single_object":        [("topology", 0.5), ("masking_boolean", 0.4)],
}

# ---------------------------------------------------------------------------
# FUNCTION INDEX — parse, classify, cache
# ---------------------------------------------------------------------------

def _compute_hash(helper_code: str) -> str:
    """Fast hash for staleness check."""
    snippet = f"{len(helper_code)}:{helper_code[:1024]}:{helper_code[-1024:]}"
    return hashlib.md5(snippet.encode()).hexdigest()


def _parse_functions(helper_code: str) -> list[dict]:
    """Extract (name, signature, docstring) for every function in helper_code."""
    # Match def lines and optionally grab a following one-line docstring
    pattern = re.compile(
        r'(def\s+(\w+)\s*\([^)]*\))'       # group 1=full sig, group 2=name
        r'[^:]*:\s*\n'                       # colon + newline
        r'(?:\s+(?:\"\"\"|\'\'\')(.+?)(?:\"\"\"|\'\'\'))?',  # group 3=docstring (optional)
        re.DOTALL,
    )
    functions = []
    for m in pattern.finditer(helper_code):
        sig = m.group(1).strip()
        name = m.group(2)
        doc = (m.group(3) or "").strip().split("\n")[0]  # first line only
        functions.append({"name": name, "signature": sig, "docstring": doc})
    # Fallback: also catch sigs the complex regex missed (multi-line params, etc.)
    simple_sigs = re.findall(r"(def\s+(\w+)\s*\([^)]*\))", helper_code)
    seen = {f["name"] for f in functions}
    for sig, name in simple_sigs:
        if name not in seen:
            functions.append({"name": name, "signature": sig.strip(), "docstring": ""})
            seen.add(name)
    return functions


def _classify_function(name: str, docstring: str) -> list[str]:
    """Classify a function into 1-2 categories using keyword matching."""
    text = (name + " " + docstring).lower()
    scored = []
    for cat, keywords in CATEGORY_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            scored.append((cat, hits))
    scored.sort(key=lambda x: x[1], reverse=True)
    if not scored:
        return ["general"]
    # Return top 1-2 categories (second only if it has decent overlap)
    cats = [scored[0][0]]
    if len(scored) > 1 and scored[1][1] >= scored[0][1] * 0.5:
        cats.append(scored[1][0])
    return cats


def build_function_index(helper_code: str) -> dict:
    """Parse all functions, classify, return index dict."""
    functions = _parse_functions(helper_code)
    category_index: dict[str, list[str]] = {cat: [] for cat in CATEGORY_KEYWORDS}
    category_index["general"] = []

    for func in functions:
        cats = _classify_function(func["name"], func["docstring"])
        func["categories"] = cats
        for cat in cats:
            category_index[cat].append(func["name"])

    return {
        "dsl_hash": _compute_hash(helper_code),
        "functions": functions,
        "category_index": category_index,
    }


def _load_or_build_index(helper_code: str) -> dict:
    """Load cached index or rebuild if stale."""
    current_hash = _compute_hash(helper_code)
    if INDEX_PATH.exists():
        try:
            idx = json.loads(INDEX_PATH.read_text())
            if idx.get("dsl_hash") == current_hash:
                return idx
        except (json.JSONDecodeError, OSError, KeyError):
            pass
    idx = build_function_index(helper_code)
    try:
        INDEX_PATH.write_text(json.dumps(idx, indent=1))
    except OSError:
        pass  # non-fatal if cache write fails
    return idx


def invalidate_cache() -> None:
    """Delete cached index. Next call to get_relevant_signatures rebuilds."""
    try:
        INDEX_PATH.unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# GRID FEATURE EXTRACTION — pure Python, no numpy
# ---------------------------------------------------------------------------

def _extract_grid_features(task_data: dict) -> dict[str, float]:
    """Extract heuristic features from a task's train pairs."""
    features: dict[str, float] = {
        "symmetry_h": 0.0,
        "symmetry_v": 0.0,
        "high_color_count": 0.0,
        "color_delta": 0.0,
        "many_objects": 0.0,
        "size_change": 0.0,
        "has_border_frame": 0.0,
        "has_repeating_pattern": 0.0,
        "single_object": 0.0,
    }

    train = task_data.get("train", [])
    if not train:
        return features

    sym_h_vals, sym_v_vals = [], []
    color_counts, color_deltas = [], []
    obj_counts = []
    size_changes = []
    border_frames = []
    repeat_flags = []

    for pair in train:
        inp = pair.get("input", [])
        out = pair.get("output", [])
        if not inp or not inp[0]:
            continue

        rows, cols = len(inp), len(inp[0])

        # --- Symmetry ---
        h_match = v_match = total = 0
        for r in range(rows):
            for c in range(cols // 2):
                total += 1
                if inp[r][c] == inp[r][cols - 1 - c]:
                    h_match += 1
        sym_h_vals.append(h_match / max(total, 1))

        total = 0
        for r in range(rows // 2):
            for c in range(cols):
                total += 1
                if inp[r][c] == inp[rows - 1 - r][c]:
                    v_match += 1
        sym_v_vals.append(v_match / max(total, 1))

        # --- Color count ---
        in_colors = set()
        for row in inp:
            in_colors.update(row)
        out_colors = set()
        for row in out:
            out_colors.update(row)
        color_counts.append(len(in_colors))
        color_deltas.append(abs(len(in_colors) - len(out_colors)))

        # --- Object count proxy (scanline bg→non-bg transitions) ---
        # Detect background as most common border value
        border_vals = []
        if rows > 0 and cols > 0:
            border_vals.extend(inp[0])
            border_vals.extend(inp[-1])
            for r in range(1, rows - 1):
                border_vals.append(inp[r][0])
                border_vals.append(inp[r][-1])
        bg = max(set(border_vals), key=border_vals.count) if border_vals else 0
        transitions = 0
        for r in range(rows):
            prev_bg = True
            for c in range(cols):
                is_bg = (inp[r][c] == bg)
                if prev_bg and not is_bg:
                    transitions += 1
                prev_bg = is_bg
        obj_counts.append(transitions)

        # --- Size change ---
        in_area = rows * cols
        out_rows = len(out)
        out_cols = len(out[0]) if out else 0
        out_area = out_rows * out_cols
        if in_area > 0:
            size_changes.append(out_area / in_area)

        # --- Border frame ---
        if rows >= 3 and cols >= 3:
            border_color = inp[0][0]
            is_frame = all(inp[0][c] == border_color for c in range(cols))
            is_frame = is_frame and all(inp[-1][c] == border_color for c in range(cols))
            is_frame = is_frame and all(inp[r][0] == border_color for r in range(rows))
            is_frame = is_frame and all(inp[r][-1] == border_color for r in range(rows))
            border_frames.append(1.0 if is_frame else 0.0)

        # --- Repeating pattern (row periodicity) ---
        found_period = False
        for p in range(1, max(rows // 2, 1) + 1):
            if all(
                inp[r][c] == inp[r + p][c]
                for r in range(rows - p)
                for c in range(cols)
            ):
                found_period = True
                break
        repeat_flags.append(1.0 if found_period else 0.0)

    # Aggregate across train pairs
    def avg(vals):
        return sum(vals) / len(vals) if vals else 0.0

    features["symmetry_h"] = avg(sym_h_vals)
    features["symmetry_v"] = avg(sym_v_vals)
    features["high_color_count"] = 1.0 if avg(color_counts) > 4 else (0.5 if avg(color_counts) > 2 else 0.0)
    features["color_delta"] = min(avg(color_deltas) / 3.0, 1.0)  # normalize
    features["many_objects"] = min(avg(obj_counts) / 5.0, 1.0)
    features["size_change"] = min(abs(avg(size_changes) - 1.0), 1.0) if size_changes else 0.0
    features["has_border_frame"] = avg(border_frames)
    features["has_repeating_pattern"] = avg(repeat_flags)
    features["single_object"] = 1.0 if avg(obj_counts) <= 1.5 else 0.0

    return features


def _aggregate_features(task_data_list: list[dict]) -> dict[str, float]:
    """Average grid features across multiple failing tasks."""
    all_features = [_extract_grid_features(td) for td in task_data_list]
    if not all_features:
        return {}
    keys = all_features[0].keys()
    return {k: max(f[k] for f in all_features) for k in keys}  # max, not avg — any signal counts


# ---------------------------------------------------------------------------
# CATEGORY RELEVANCE — map grid features to category scores
# ---------------------------------------------------------------------------

def _category_relevance(features: dict[str, float]) -> dict[str, float]:
    """Compute per-category relevance scores from grid features."""
    scores: dict[str, float] = {cat: 0.0 for cat in CATEGORY_KEYWORDS}
    scores["general"] = 0.3  # base relevance for core utilities

    for feat_name, feat_val in features.items():
        if feat_val < 0.3:  # threshold: ignore weak signals
            continue
        mappings = FEATURE_CATEGORY_MAP.get(feat_name, [])
        for cat, weight in mappings:
            scores[cat] = max(scores[cat], feat_val * weight)

    return scores


# ---------------------------------------------------------------------------
# SCORING & RANKING
# ---------------------------------------------------------------------------

def _load_hypothesis_win_rates() -> dict[str, float]:
    """Load category win rates from hypothesis_type_scores.json."""
    if not HYPOTHESIS_TYPES_FILE.exists():
        return {}
    try:
        data = json.loads(HYPOTHESIS_TYPES_FILE.read_text())
        return {
            cat: info["wins"] / max(info["total"], 1)
            for cat, info in data.items()
        }
    except (json.JSONDecodeError, OSError, KeyError):
        return {}


def _load_recent_function_names(n: int = 10) -> set[str]:
    """Load function names from the last N hypothesis rounds."""
    if not HYPOTHESES_FILE.exists():
        return set()
    names = set()
    try:
        lines = HYPOTHESES_FILE.read_text().strip().split("\n")
        for line in lines[-n:]:
            try:
                entry = json.loads(line)
                for fn in entry.get("proposed_functions", []):
                    names.add(fn)
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return names


def _score_functions(
    index: dict,
    category_scores: dict[str, float],
    win_rates: dict[str, float],
    recent_names: set[str],
) -> list[tuple[str, float]]:
    """Score each function and return (signature, score) sorted descending."""
    scored = []
    for func in index["functions"]:
        name = func["name"]
        cats = func.get("categories", ["general"])

        # Base score: max category relevance
        base = max(category_scores.get(c, 0.0) for c in cats)

        # Boost from proven hypothesis types
        best_win = max((win_rates.get(c, 0.0) for c in cats), default=0.0)
        boost = 1.0 + 0.3 * best_win

        # Penalty for recently tried functions
        recency_penalty = 0.5 if name in recent_names else 1.0

        score = base * boost * recency_penalty
        scored.append((func["signature"], name, score))

    scored.sort(key=lambda x: x[2], reverse=True)
    return scored


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def get_relevant_signatures(
    helper_code: str,
    task_data_list: list[dict],
    n: int = 50,
) -> list[str]:
    """Return top-N DSL function signatures ranked by relevance to failing tasks.

    Args:
        helper_code: The HELPER_CODE_PREFIX string from dsl.py
        task_data_list: List of task dicts, each with "train" key containing
                        input/output grid pairs
        n: Number of signatures to return

    Returns:
        List of signature strings like "def flood_fill(grid, start, ...)"
    """
    index = _load_or_build_index(helper_code)

    # Extract and aggregate grid features
    features = _aggregate_features(task_data_list)
    cat_scores = _category_relevance(features)

    # Load auxiliary signals
    win_rates = _load_hypothesis_win_rates()
    recent_names = _load_recent_function_names(10)

    # Score and rank
    scored = _score_functions(index, cat_scores, win_rates, recent_names)

    # Always include core functions
    result_sigs = []
    result_names = set()
    for sig, name, _score in scored:
        if name in CORE_FUNCTIONS and name not in result_names:
            result_sigs.append(sig)
            result_names.add(name)

    # Fill remaining slots with top-scored non-core functions
    for sig, name, _score in scored:
        if len(result_sigs) >= n:
            break
        if name not in result_names:
            result_sigs.append(sig)
            result_names.add(name)

    return result_sigs


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    dsl_path = Path(__file__).parent / "dsl.py"
    if not dsl_path.exists():
        print("dsl.py not found")
        sys.exit(1)

    # Load HELPER_CODE_PREFIX
    dsl_code = dsl_path.read_text()
    m = re.search(r"HELPER_CODE_PREFIX\s*=\s*r?'''(.*?)'''", dsl_code, re.DOTALL)
    if not m:
        m = re.search(r'HELPER_CODE_PREFIX\s*=\s*r?"""(.*?)"""', dsl_code, re.DOTALL)
    if not m:
        print("Could not extract HELPER_CODE_PREFIX")
        sys.exit(1)
    helper_code = m.group(1)

    # Build index
    print(f"Parsing {len(helper_code)} chars of helper code...")
    idx = build_function_index(helper_code)
    print(f"Found {len(idx['functions'])} functions")
    for cat, names in sorted(idx["category_index"].items()):
        print(f"  {cat}: {len(names)} functions")

    # Test with a synthetic task (horizontally symmetric, 5 colors)
    fake_task = {
        "train": [{
            "input": [
                [0, 1, 2, 1, 0],
                [3, 4, 0, 4, 3],
                [0, 1, 2, 1, 0],
            ],
            "output": [
                [0, 1, 2, 1, 0],
                [3, 4, 0, 4, 3],
                [0, 1, 2, 1, 0],
                [3, 4, 0, 4, 3],
            ],
        }]
    }
    print("\nTest task: symmetric input, 5 colors, size change 1.33x")
    features = _extract_grid_features(fake_task)
    for k, v in features.items():
        if v > 0:
            print(f"  {k}: {v:.2f}")

    sigs = get_relevant_signatures(helper_code, [fake_task], n=20)
    print(f"\nTop 20 relevant signatures:")
    for s in sigs:
        print(f"  {s}")
