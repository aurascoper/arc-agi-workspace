"""
benchmark_dsl.py — Evaluate dsl.py against ARC training tasks.
Used by codopt as the --command benchmark.

Modes (set via BENCHMARK_MODE env var):
  fast (default) — 60% helper coverage + 40% prompt generation. ~30s.
  full           — 50% helper + 25% prompt + 25% helper composition. ~90s.
                   Writes enriched metric.json with component scores.

For codopt: writes metric.json with {"score": <float>}
"""

import json
import sys
import os
import random
import threading
from pathlib import Path

ARC_DATA = Path(os.environ.get("ARC_DATA", "./arc_agi_2_data/training"))
SAMPLE_SIZE = int(os.environ.get("BENCHMARK_SAMPLE", "20"))
BENCHMARK_MODE = os.environ.get("BENCHMARK_MODE", "fast")


def grid_to_str(grid):
    if not grid or not isinstance(grid, list):
        return str(grid)
    try:
        return "\n".join("".join(str(c) for c in row) for row in grid)
    except Exception:
        return str(grid)


def load_dsl():
    """Load and exec dsl.py, return the namespace."""
    ns = {"grid_to_str": grid_to_str}
    try:
        code = open("dsl.py").read()
        exec(code, ns)
        return ns, None
    except Exception as e:
        return None, str(e)


def test_helpers_on_task(ns, task_data):
    """Test if HELPER_CODE_PREFIX functions work on this task's grids."""
    helper_code = ns.get("HELPER_CODE_PREFIX", "")
    if not helper_code:
        return False, "No HELPER_CODE_PREFIX"

    helper_ns = {}
    try:
        exec(helper_code, helper_ns)
    except Exception as e:
        return False, f"Helper exec failed: {e}"

    # Test core functions on the first training example
    pair = task_data["train"][0]
    grid = pair["input"]

    tests_passed = 0
    tests_total = 0

    core_functions = [
        ("detect_background_color", (grid,)),
        ("get_objects", (grid,)),
        ("shape", (grid,)),
        ("palette", (grid,)),
        ("color_counts", (grid,)),
        ("copy_grid", (grid,)),
        ("rotate_cw", (grid,)),
        ("mirror_h", (grid,)),
    ]

    for fname, args in core_functions:
        tests_total += 1
        fn = helper_ns.get(fname)
        if fn is None:
            continue
        try:
            result = [None]
            error = [None]

            def run():
                try:
                    result[0] = fn(*args)
                except Exception as e:
                    error[0] = e

            t = threading.Thread(target=run, daemon=True)
            t.start()
            t.join(timeout=2)
            if not t.is_alive() and error[0] is None and result[0] is not None:
                tests_passed += 1
        except Exception:
            pass

    return tests_passed == tests_total, f"{tests_passed}/{tests_total} core functions passed"


def test_build_prompt(ns, task_data):
    """Test if build_prompt works on this task."""
    build_prompt = ns.get("build_prompt")
    if build_prompt is None:
        return False, "No build_prompt function"

    try:
        result = [None]
        error = [None]

        def run():
            try:
                result[0] = build_prompt(task_data)
            except Exception as e:
                error[0] = e

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(timeout=5)

        if t.is_alive():
            return False, "build_prompt timed out"
        if error[0]:
            return False, f"build_prompt error: {error[0]}"
        if result[0] and len(result[0]) > 50:
            return True, "OK"
        return False, "build_prompt returned empty/short result"
    except Exception as e:
        return False, str(e)


def test_helper_composition(ns, task_data):
    """Test that helpers compose correctly: call sequences of functions on grids."""
    helper_code = ns.get("HELPER_CODE_PREFIX", "")
    if not helper_code:
        return False, "No HELPER_CODE_PREFIX"

    helper_ns = {}
    try:
        exec(helper_code, helper_ns)
    except Exception as e:
        return False, f"Helper exec failed: {e}"

    grid = task_data["train"][0]["input"]
    compositions_passed = 0
    compositions_total = 0

    # Composition 1: copy then rotate
    compositions_total += 1
    try:
        copy_fn = helper_ns.get("copy_grid")
        rot_fn = helper_ns.get("rotate_cw")
        if copy_fn and rot_fn:
            copied = copy_fn(grid)
            rotated = rot_fn(copied)
            if rotated and isinstance(rotated, list):
                compositions_passed += 1
    except Exception:
        pass

    # Composition 2: detect_background then get_objects
    compositions_total += 1
    try:
        bg_fn = helper_ns.get("detect_background_color")
        obj_fn = helper_ns.get("get_objects")
        if bg_fn and obj_fn:
            bg = bg_fn(grid)
            objs = obj_fn(grid)
            if isinstance(bg, int) and objs is not None:
                compositions_passed += 1
    except Exception:
        pass

    # Composition 3: shape + palette + color_counts consistency
    compositions_total += 1
    try:
        shape_fn = helper_ns.get("shape")
        palette_fn = helper_ns.get("palette")
        cc_fn = helper_ns.get("color_counts")
        if shape_fn and palette_fn and cc_fn:
            s = shape_fn(grid)
            p = palette_fn(grid)
            cc = cc_fn(grid)
            # palette colors should be subset of color_counts keys
            if s and p is not None and cc is not None:
                compositions_passed += 1
    except Exception:
        pass

    # Composition 4: mirror_h then mirror_h should give back original
    compositions_total += 1
    try:
        mirror_fn = helper_ns.get("mirror_h")
        copy_fn = helper_ns.get("copy_grid")
        if mirror_fn and copy_fn:
            original = copy_fn(grid)
            mirrored = mirror_fn(grid)
            double_mirror = mirror_fn(mirrored)
            if double_mirror == original:
                compositions_passed += 1
    except Exception:
        pass

    # Composition 5: test on ALL training pairs, not just first
    compositions_total += 1
    all_pairs_ok = True
    for pair in task_data["train"]:
        try:
            g = pair["input"]
            shape_fn = helper_ns.get("shape")
            if shape_fn:
                s = shape_fn(g)
                if not s or len(s) != 2:
                    all_pairs_ok = False
                    break
            else:
                all_pairs_ok = False
                break
        except Exception:
            all_pairs_ok = False
            break
    if all_pairs_ok:
        compositions_passed += 1

    score = compositions_passed / compositions_total if compositions_total > 0 else 0.0
    return score >= 0.8, f"{compositions_passed}/{compositions_total} compositions passed"


def main():
    ns, err = load_dsl()
    if ns is None:
        print(f"FATAL: dsl.py failed to load: {err}")
        json.dump({"score": 0.0}, open("metric.json", "w"))
        return

    task_files = list(ARC_DATA.glob("*.json"))
    if not task_files:
        print(f"No tasks found in {ARC_DATA}")
        json.dump({"score": 0.0}, open("metric.json", "w"))
        return

    random.seed(42)
    sample = random.sample(task_files, min(SAMPLE_SIZE, len(task_files)))

    helper_pass = 0
    prompt_pass = 0
    compose_pass = 0

    for tf in sample:
        with open(tf) as f:
            task_data = json.load(f)

        ok, msg = test_helpers_on_task(ns, task_data)
        if ok:
            helper_pass += 1

        ok2, msg2 = test_build_prompt(ns, task_data)
        if ok2:
            prompt_pass += 1

        if BENCHMARK_MODE == "full":
            ok3, msg3 = test_helper_composition(ns, task_data)
            if ok3:
                compose_pass += 1

    helper_score = helper_pass / len(sample)
    prompt_score = prompt_pass / len(sample)

    if BENCHMARK_MODE == "full":
        compose_score = compose_pass / len(sample)
        # Full mode: 50% helper + 25% prompt + 25% composition
        combined = helper_score * 0.5 + prompt_score * 0.25 + compose_score * 0.25

        print(f"Helper coverage: {helper_pass}/{len(sample)} ({helper_score:.2%})")
        print(f"Prompt generation: {prompt_pass}/{len(sample)} ({prompt_score:.2%})")
        print(f"Helper composition: {compose_pass}/{len(sample)} ({compose_score:.2%})")
        print(f"Combined score (full): {combined:.4f}")

        json.dump({
            "score": combined,
            "helper_score": helper_score,
            "prompt_score": prompt_score,
            "compose_score": compose_score,
        }, open("metric.json", "w"))
    else:
        # Fast mode (default): 60% helper + 40% prompt
        combined = helper_score * 0.6 + prompt_score * 0.4

        print(f"Helper coverage: {helper_pass}/{len(sample)} ({helper_score:.2%})")
        print(f"Prompt generation: {prompt_pass}/{len(sample)} ({prompt_score:.2%})")
        print(f"Combined score: {combined:.4f}")

        json.dump({"score": combined}, open("metric.json", "w"))


if __name__ == "__main__":
    main()
