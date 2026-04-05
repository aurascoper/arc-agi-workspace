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

---

## 2026-04-05 — Dream-Phase Synthesis (Reflective Consolidation)

### Pattern analysis across 54 evolution rounds

**1. Metric ceiling is masking real progress and misdirecting the loop**
- `metric` (helper coverage / compose_score) hit 1.0 at round ~14 and never moved
- The evolve loop marks rounds "stagnant" when metric=1.0→1.0, even when tier3 solve improves dramatically (e.g. 0.44→0.87)
- Of 54 rounds: 24 marked "stagnant", 28 "keep", 1 "crash" — but "stagnant" rounds often contain genuine tier3 improvement
- **Root cause:** The DECIDE step at [7/9] compares `metric_before` vs `metric_after`. Since metric=1.0 always, no commits are created for solve-improving rounds
- **Fix needed:** Switch decision metric from helper coverage to blended solve score (0.7*base + 0.3*tier3)

**2. solve_before variance is too high — confounds progress tracking**
- solve_before ranges from 0.0 to 0.78 across rounds due to random tier3 task sampling
- This means the loop can't tell if solve improved because of new functions vs. easier random tasks
- **Fix needed:** Use a fixed holdout set of ~10 tier3 tasks for consistent measurement, separate from the 2-task diagnostic sample

**3. Hypothesis generation: Qwen3.5-9B dramatically outperforms deepseek-coder-v2**
- deepseek-coder-v2 (rounds 1-6, Apr 3): ~2000 char responses, value-replacement only, ~60% "no valid functions"
- Qwen3.5-9B (rounds 7+, Apr 4): ~8000-15000 char responses, spatial/symmetry/pattern functions, ~30% "no valid functions"
- Quality examples: `propagate_symmetry_markers`, `transform_quadrant_boundary_patterns`, `apply_hole_fill_pattern`
- Anti-examples: `replace_twos_with_eights`, `function_name`, `replace_specific_values_with_fours` (still some garbage)
- **Conclusion:** Model switch was correct. Remaining quality issues are prompt/temperature-related, not model-limited

**4. Task-specific overfitting is common but may not be harmful**
- Functions like `transform_pattern_b6afb2da`, `function_specific_to_task_137eaa0f` are clearly task-memorized
- However, they still pass through beam search evaluation on different tasks
- The compose_score=1.0 indicates the broader DSL still handles the 50 tier1+2 tasks
- Risk: dsl.py bloat (20,659 lines) — dead functions accumulate but don't hurt

**5. Literature techniques ranked by expected tier3 lift**

| Rank | Technique | Expected Lift | Effort | Source |
|------|-----------|---------------|--------|--------|
| 1 | Color canonicalization | +5-10% solve | Low | Symbol-Equivariant (2603.02193) |
| 2 | D4 symmetry augmentation (8x ensemble voting) | +8-15% solve | Medium | ARC-AGI-2 Report (2603.06590) |
| 3 | MDL-guided composition of existing primitives | +10-20% solve | Medium | RCE (2602.15725) |
| 4 | Persistent insight memory bank | +5-10% solve | Medium | Empirical-MCTS (2602.04248) |
| 5 | Self-distillation on correct solutions | +10-15% solve | High | SSD (2604.01193) |
| 6 | ABPR execution traces (partially done) | +3-5% solve | Low | ABPR (2603.20334) |

### Next 3 evolution hypotheses (ranked by expected tier3 lift)

**H1: `canonicalize_colors(grid)` — Color normalization primitive** (Expected: +5-10%)
- Maps grid colors to frequency-ordered canonical form before processing
- Removes color permutation as a confounding variable for the LLM solver
- Source: Symbol-Equivariant paper (2603.02193) — "only 2M params needed" with equivariant layers
- DSL equivalent: sort colors by frequency, remap. Inverse map after solving.
- Low effort, high leverage on tasks where color assignment is arbitrary

**H2: `solve_with_d4_augmentation(grid, solver)` — Symmetry ensemble** (Expected: +8-15%)
- Applies all 8 D4 group transforms (identity, 3 rotations, 4 reflections)
- Runs solver on each view, inverse-transforms solutions, pixel-majority vote
- Source: ARC-AGI-2 Technical Report (2603.06590) — core technique of top teams
- Effectively 8x more attempts with zero additional model calls if solver is deterministic
- Medium effort: need inverse transform pipeline + voting logic

**H3: `compose_primitives_mdl(grid, target, max_depth=3)` — MDL-guided composition** (Expected: +10-20%)
- Instead of generating new functions, compose existing 800+ DSL primitives
- Search: enumerate all compositions up to depth 3, select by minimum description length matching all examples
- Source: RCE (2602.15725) — "12-18 point gains on ARC-AGI-2 with Mistral-7B"
- High leverage: exploits the huge existing library that beam search doesn't fully utilize
- Medium effort: need fast enumeration + MDL scoring

### Quantitative trajectory analysis (53 rounds, Apr 3-5)

**Round status:** 26 keep, 26 stagnant, 1 crash — exactly 50/50 keep/stagnant
**Function proposal rate:** 35/53 rounds (66%) produced valid functions
**Function proposal count:** median 2, max 10 (latest round)

**CRITICAL FINDING: solve_before shows NO upward trend across 53 rounds.**
- Bounces randomly: 0.0, 0.48, 0.13, 0.66, 0.00, 0.56 — pure noise from random tier3 task sampling
- This means the evolve loop cannot observe its own progress
- Each round evaluates 2 random tier3 tasks, so baseline measurement has ~50% variance
- The DSL IS growing (559→800+ functions) but whether it's actually solving MORE tasks is unmeasurable with current setup

**Phase transition at round 42 (Apr 4 10:53):** solve_after drops from 1.0 to real values (0.94, 0.70, 0.86...)
- This is when the solve_after metric fix landed (blended score instead of compose_score)
- Real solve_after range post-fix: 0.70-0.93
- Best real solve_after: 0.93 (execute_symmetric_scaling, round 48)
- Mean real solve_after (rounds 42-53): 0.825

### Co-evolution restart configuration

**Immediate fixes needed in `evolve_qwen_arc.py` (for next session):**

1. **Fix decision metric:** Replace `metric_before`/`metric_after` comparison with `solve_after` as the commit decision. Threshold: commit if solve_after > 0.85 (current best is 0.87)
2. **Fixed holdout set:** Pick 10 fixed tier3 tasks for consistent baseline measurement. Current random sampling makes progress unobservable
3. **Dead function pruning:** Add a periodic step (every 10 rounds) that removes functions from dsl.py that aren't called by any beam search winner. Current 20,659 lines likely has >50% dead code
4. **Hypothesis quality gate:** Reject functions named `function_name`, `func1`, `replace_specific_values_with_*` (pattern: generic names = garbage output). Only inject functions with task-aware names

**Restart status:**
- Last evolution round: Round 4 (in progress as of 2026-04-05 05:44)
- Active beam worktree: `.beam_worktrees/r1_pbaseline_1/`
- Current dsl.py: 20,659 lines, ~800+ functions
- Tier 1+2: 50/50 perfect (ceiling)
- Best tier3 solve this session: 0.8652 (Round 3), 0.9269 (Round 48 overall)
- **Blocking issues:** (1) metric=1.0 ceiling prevents meaningful commit decisions, (2) random task sampling prevents progress tracking

### Literature x Blocker cross-reference

The 32 techniques in `literature_hints.json` fall into 3 categories:
- **Category A (12 techniques):** ARC-specific reasoning/architecture improvements
- **Category B (12 techniques):** KV cache / inference optimization
- **Category C (8 techniques):** Model training / fine-tuning

**Which techniques address which blockers:**

| Blocker | Relevant Techniques | Priority |
|---------|-------------------|----------|
| Metric ceiling | None directly — this is a pipeline bug, not an algorithm gap | P0 (code fix) |
| Random task sampling | ARC-TGI (synthetic data), fixed holdout design | P0 (code fix) |
| Hypothesis quality | SSD self-distillation, CoT fine-tuning, RCE composition | P1 |
| Solve rate plateau ~0.87 | D4 augmentation, color canonicalization, ABPR traces, MDL composition | P1 |
| Inference speed | vllm-mlx, persistent Q4 KV, JanusQuant 2-bit | P2 (not bottleneck) |

**Key insight:** The top 2 blockers are pipeline engineering, not algorithm. Fixing the decision metric and holdout set will immediately unblock the co-evolution loop. Algorithm improvements (H1-H3) can then be measured properly.

### Action plan for co-evolution restart

**Phase 1 — Unblock the loop (do first, ~1 hour):**
1. Fix DECIDE step in `evolve_qwen_arc.py`: use `solve_after` as commit metric, threshold 0.85
2. Create fixed holdout: select 10 diverse tier3 tasks, measure baseline solve rate
3. Add hypothesis name quality gate (reject `function_name`, `func1`, `replace_*_with_*`)

**Phase 2 — Inject H1-H3 into DSL (do next, ~2 hours):**
1. H1: `canonicalize_colors(grid)` — normalize color ordering by frequency
2. H2: `solve_with_d4_augmentation(grid, solver)` — 8x symmetry ensemble
3. H3: Composition search — enumerate primitive chains up to depth 3

**Phase 3 — Resume evolution (ongoing):**
- Run `evolve_qwen_arc.py --never-stop` with fixed metrics
- Monitor via fixed holdout: expect baseline solve to become observable trend
- Target: holdout solve rate >0.87 within 20 rounds
