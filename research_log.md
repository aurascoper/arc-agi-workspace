# ARC Prize 2026 — Research Log

Tracks: ARC-AGI-2 (static) + ARC-AGI-3 (interactive) + Paper Track
Format: date | change | metric delta | notes

---

## 2026-04-04

### Switched beam search from Ollama to MLX
- `beam_search_local.py`: Added MLX backend dispatcher, defaults to `mlx` instead of `ollama`
- `target_mlx_arc.py`: Added `max_tokens` parameter for beam search (2048) vs ARC solve (1024)
- Eliminated HTTP overhead; reuses single Qwen3.5-9B-4bit model instance with TurboQuant 3-bit KV cache
- Ollama remains as fallback via `BEAM_BACKEND=ollama`

### Switched hypothesis generation from deepseek-coder-v2 to Qwen3.5-9B (MLX)
- `evolve_qwen_arc.py`: Replaced Ollama `generate()` with MLX dispatcher (`EVOLVE_BACKEND=mlx`)
- **Before**: deepseek-coder-v2 produced garbage hypotheses — 5 identical `replace_value_X_with_Y` functions (~2000 chars)
- **After**: Qwen3.5-9B produces spatial transformation functions (`apply_mirror_and_copy`, `detect_symmetry_axis`, `xor_halves_with_marker`) — 10954 chars, reasoning about grid structure
- **Key insight**: Model quality matters far more than inference speed for hypothesis generation

### Raised temperature floor 0.4 -> 0.6
- `evolve_qwen_arc.py`: `temp = min(0.6 + stagnant_streak * 0.1, 0.9)`
- Prevents repetitive safe outputs when stagnation is low

### Reduced tier3 evaluation from 5 tasks to 2
- `evolve_qwen_arc.py`: `TIER3_TASKS` default 5 -> 2
- Tier3 solve capped at 1024 tokens (was unlimited — one response was 7905 chars for a failing task)
- Round time: ~45 min -> ~25 min estimated

### Fixed solve_after metric (earlier today)
- Was reading `compose_score` from metric.json (always 1.0 at ceiling)
- Now uses beam search blended score (0.7*base + 0.3*tier3_solve)
- First real scores: 0.9439, 0.7 (no longer all 1.0)

### Round 1 results (Qwen3.5 + MLX)
- Hypothesis: `apply_mirror_and_copy_to_grid_base_and_expand` — task-specific but spatially aware
- Beam search baseline: 0.8633
- 3 mutations scored: 0.7, 0.739, pending
- Solve score: 0.4398 -> 0.8633 (but metric still 1.0 -> stagnant)
- Mutation generation: ~440s each at 4096 tokens; capped to 2048 for next round

### Round 2 results (Qwen3.5 + MLX, all tier1+2 perfect)
- Tier 1+2: 50/50 perfect — DSL covers all known tasks
- Tier 3 frontier: tasks 34b99a2b, b6afb2da both SOLVE_FAIL
- Hypothesis: `decompose_and_convert_pattern` (10194 chars)
- Beam search baseline: 0.7000
- Mutation 0: 0.8215 (tier3 solve 40%) — improvement
- Mutation 1: 0.8229 (tier3 solve 41%) — slight further improvement
- Mutation 2: evaluating (33 functions injected at 4096 tokens — bloat, exactly what 2048 cap fixes)

### ABPR integration (literature-driven)
- Added execution trace capture to `try_code_on_task()` (5-element tuples with traceback)
- `solve_task_single()` now returns `(score, traces)` with failure diagnostics
- `build_diagnostic_prompt()` enriched with "What went WRONG" section showing errors + tracebacks
- Beam search `_mini_solve_eval()` now averages pixel accuracy across ALL failing pairs, not just first
- Source: ABPR paper (arXiv 2603.20334) — 56.67% Pass@2 on AGI-2 via algorithmic debugging

### Cross-track DSL sharing
- Created `dsl_core.py` — curated registry of 30 primitives from dsl.py (769 functions)
- 5 categories: object_detection (5), spatial (9), color (6), measurement (6), composition (4)
- Ready for AGI-3 codopt prompt injection

### Literature scan (32 techniques extracted)
- Ran locally using arXiv + Semantic Scholar MCP tools
- Top findings: ABPR (trace debugging), SSD (self-distillation), vllm-mlx (21-87% faster inference)
- TurboQuant ecosystem expanding: ITQ3_S, TurboESM (RoPE fix), TurboAngle
- Results saved to `evolution_results/literature_hints.json`

### Negative result: deepseek-coder-v2 for ARC hypothesis generation
- Produced only value-replacement functions regardless of task context
- Blacklist mechanism insufficient — model generates semantically identical functions with different names
- Temperature 0.4 too conservative for exploration
