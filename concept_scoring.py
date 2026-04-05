"""ConceptSearch-inspired concept-based scoring for beam search.

Instead of pure pixel accuracy, asks the LLM to describe the transformation
concept, then scores whether generated output captures that concept.

Based on: ConceptSearch (Singhal & Shroff, 2412.07322)
  - Concept-based scoring is ~30% more efficient than Hamming distance
  - LLM NL scoring describes transformation then evaluates match

Integration: called from beam_search_local._mini_solve_eval() and
evolve_qwen_arc.solve_task_single() as an optional score augmentation.
"""

from __future__ import annotations

import json
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Concept description — ask LLM to describe the transformation rule
# ---------------------------------------------------------------------------

CONCEPT_PROMPT_TEMPLATE = """/no_think
You are analyzing an ARC-AGI task. Given input-output grid pairs, describe the transformation rule in ONE sentence.

{examples}

Describe the transformation rule in exactly ONE sentence. Be specific about spatial operations, color changes, and object manipulations. Do NOT write code."""


def _format_grid(grid: list[list[int]], label: str = "Grid") -> str:
    """Compact grid representation."""
    rows = [" ".join(str(c) for c in row) for row in grid]
    return f"{label} ({len(grid)}x{len(grid[0]) if grid else 0}):\n" + "\n".join(rows)


def _format_examples(task_data: dict) -> str:
    """Format training pairs for concept prompt."""
    parts = []
    for i, pair in enumerate(task_data.get("train", [])[:3]):  # max 3 examples
        parts.append(f"Example {i+1}:")
        parts.append(_format_grid(pair["input"], "Input"))
        parts.append(_format_grid(pair["output"], "Output"))
        parts.append("")
    return "\n".join(parts)


def describe_concept(task_data: dict, generate_fn, temperature: float = 0.1,
                     max_tokens: int = 150) -> str | None:
    """Ask LLM to describe the transformation concept in one sentence.

    Args:
        task_data: ARC task dict with train/test pairs
        generate_fn: callable(prompt, temperature, max_tokens) -> str
        temperature: low temp for deterministic description
        max_tokens: keep short — one sentence

    Returns:
        One-sentence concept description, or None on failure.
    """
    examples = _format_examples(task_data)
    prompt = CONCEPT_PROMPT_TEMPLATE.format(examples=examples)

    try:
        response = generate_fn(prompt, temperature=temperature, max_tokens=max_tokens)
        # Strip thinking tags if present
        if "</think>" in response:
            response = response.split("</think>")[-1]
        concept = response.strip().split("\n")[0].strip()
        if len(concept) < 10:
            return None
        return concept
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Concept-based scoring — does the output match the described concept?
# ---------------------------------------------------------------------------

CONCEPT_SCORE_PROMPT = """/no_think
You are evaluating whether a predicted output grid matches a transformation concept.

Concept: {concept}

Input grid:
{input_grid}

Expected output:
{expected_grid}

Predicted output:
{predicted_grid}

On a scale of 0 to 10, how well does the predicted output capture the described concept?
- 10: Perfect match (correct transformation applied)
- 7-9: Mostly correct (right idea, minor errors)
- 4-6: Partially correct (some aspects of concept captured)
- 1-3: Wrong approach (different transformation applied)
- 0: Completely wrong or empty

Reply with ONLY a single integer 0-10."""


def score_concept_match(concept: str, input_grid: list[list[int]],
                        expected_grid: list[list[int]],
                        predicted_grid: list[list[int]] | None,
                        generate_fn, temperature: float = 0.1) -> float:
    """Score how well predicted output matches the transformation concept.

    Returns float 0.0-1.0 (normalized from 0-10 scale).
    """
    if predicted_grid is None:
        return 0.0

    prompt = CONCEPT_SCORE_PROMPT.format(
        concept=concept,
        input_grid=_format_grid(input_grid, "Input"),
        expected_grid=_format_grid(expected_grid, "Expected"),
        predicted_grid=_format_grid(predicted_grid, "Predicted"),
    )

    try:
        response = generate_fn(prompt, temperature=temperature, max_tokens=20)
        if "</think>" in response:
            response = response.split("</think>")[-1]
        # Extract first integer from response
        for token in response.strip().split():
            token = token.strip(".,;:")
            if token.isdigit():
                score = int(token)
                return min(max(score, 0), 10) / 10.0
        return 0.0
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Blended scoring — combine pixel accuracy with concept score
# ---------------------------------------------------------------------------

def blended_concept_score(pixel_accuracy: float, concept_score: float,
                          concept_weight: float = 0.3) -> float:
    """Blend pixel accuracy with concept-based score.

    Default: 70% pixel + 30% concept (same weight as SOLVE_WEIGHT in beam search).
    Concept score helps differentiate between "close but wrong approach" and
    "right approach with minor pixel errors".
    """
    return pixel_accuracy * (1 - concept_weight) + concept_score * concept_weight


# ---------------------------------------------------------------------------
# Full concept-aware evaluation for a single task attempt
# ---------------------------------------------------------------------------

def evaluate_with_concept(task_data: dict, code: str, generate_fn,
                          concept: str | None = None,
                          concept_weight: float = 0.3) -> tuple[float, str | None]:
    """Evaluate a program with concept-aware scoring.

    Args:
        task_data: ARC task dict
        code: Python code with def transform(grid)
        generate_fn: LLM generate function
        concept: pre-computed concept description (or None to generate)
        concept_weight: blend weight for concept score

    Returns:
        (blended_score, concept_description)
    """
    from target_mlx_arc import try_code_on_task, calculate_pixel_accuracy

    passed, failures = try_code_on_task(code, task_data)
    if passed:
        return 1.0, concept

    if not failures:
        return 0.0, concept

    # Get concept description (cached if provided)
    if concept is None:
        concept = describe_concept(task_data, generate_fn)

    # Calculate pixel accuracy
    pair_pas = []
    concept_scores = []
    for fail in failures:
        inp, expected, predicted = fail[0], fail[1], fail[2]
        pa = calculate_pixel_accuracy(expected, predicted) if predicted is not None else 0.0
        pair_pas.append(pa)

        # Concept scoring only if we have a concept and a prediction
        if concept and predicted is not None:
            cs = score_concept_match(concept, inp, expected, predicted, generate_fn)
            concept_scores.append(cs)

    avg_pa = sum(pair_pas) / len(pair_pas) if pair_pas else 0.0

    if concept_scores:
        avg_cs = sum(concept_scores) / len(concept_scores)
        return blended_concept_score(avg_pa, avg_cs, concept_weight), concept
    else:
        return avg_pa, concept


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Test concept description with a simple task
    test_task = {
        "train": [
            {"input": [[0, 0, 1], [0, 1, 0], [1, 0, 0]],
             "output": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
            {"input": [[0, 2, 0], [2, 0, 2], [0, 2, 0]],
             "output": [[0, 2, 0], [2, 0, 2], [0, 2, 0]]},
        ],
        "test": [{"input": [[3, 0, 0], [0, 3, 0], [0, 0, 3]]}]
    }
    examples = _format_examples(test_task)
    print("[concept] Example prompt:")
    print(CONCEPT_PROMPT_TEMPLATE.format(examples=examples))
    print("\n[concept] Module loaded OK. Use describe_concept() + score_concept_match().")
