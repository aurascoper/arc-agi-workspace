# ARC-AGI DSL Evolution

## Goal
Evolve `dsl.py` to solve more ARC-AGI tasks. The file contains `HELPER_CODE_PREFIX` — a string of Python helper functions that get prepended to LLM-generated `transform()` functions.

## What to optimize
Add new helper functions to `HELPER_CODE_PREFIX` that implement common ARC transformation patterns:
- Symmetry detection and completion
- Pattern repetition and tiling
- Object extraction, filtering, and recoloring
- Grid partitioning and recombination
- Rule inference from input/output pairs

## Constraints
- `HELPER_CODE_PREFIX` must remain a valid Python string that can be exec'd
- All existing functions must be preserved (don't remove working code)
- New functions should be self-contained or use only other functions in the prefix
- Keep functions focused — one clear operation per function
- Use numpy sparingly; prefer pure Python for portability

## Scoring
The benchmark evaluates: (1) whether helpers execute without errors on real ARC grids, and (2) whether `build_prompt()` successfully generates prompts for tasks.
