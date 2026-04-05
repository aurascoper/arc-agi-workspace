# ARC-AGI Competition Approach

## System: LLM-Guided DSL Evolution via Nested Optimization Loops

### Core Thesis

> ARC tasks are compressible programs over a learnable DSL. An LLM approximates
> the Solomonoff prior over grid-transformation programs; a tournament selects
> for minimum description length. The DSL grows toward the universal function set
> for ARC by diagnosing failures and injecting targeted primitives.

---

## 1. Competition Criteria Mapping

### ARC-AGI-2 (Static, Kaggle)

| Criterion | Our Approach | Artifact | Status |
|-----------|-------------|----------|--------|
| Solve novel grid puzzles | DSL-guided program synthesis + LLM code generation | `target_kaggle_arc.py`, `dsl.py` | Working |
| Generalize from few examples | 863 composable helpers reduce search space | `dsl.py` (870KB, 863 functions) | Living artifact |
| $50/task compute budget | Qwen2.5-14B on 2xT4 (fp8, TP=2) | `target_kaggle_arc.py` (vLLM backend) | Working |
| Offline Kaggle notebook | %%writefile + kaggle dataset modules | `target-arc2-agi-dsl.ipynb` | Working |
| Partial credit (pixel accuracy) | Spatial Hausdorff + color accuracy metric | `target_mlx_arc.py:calculate_pixel_accuracy` | Working |

### ARC-AGI-3 (Interactive, API)

| Criterion | Our Approach | Artifact | Status |
|-----------|-------------|----------|--------|
| Explore unknown environments | Phase 1: systematic probing (9 actions, causal model) | `target_arc3_agent.py:NeurosymbolicAgent` | WIP |
| Plan and act in real-time | Phase 2: BFS over causal graph + optional LLM assist | `target_arc3_agent.py:choose_action` | WIP |
| Adapt policy per episode | POLICY_CODE string evolved by beam search | `target_arc3_agent.py:POLICY_CODE` | Scaffolded |
| Agent lifecycle compliance | Extends official `Agent` base class | `ARC-AGI-3-Agents/agents/agent.py` | Working |

### Local Development (M4 16GB)

| Capability | Implementation | Artifact |
|-----------|---------------|----------|
| Local LLM inference | Qwen3.5-9B-4bit via MLX (~5.5GB) | `target_mlx_arc.py` |
| KV cache compression | mlx-lm built-in `kv_bits=3` | `target_mlx_arc.py` |
| DSL evolution | Autoresearch outer loop + local beam search inner loop | `evolve_qwen_arc.py` + `beam_search_local.py` |
| Fitness evaluation | 3-tier: helper coverage, prompt gen, solve accuracy | `benchmark_dsl.py` |
| Correctness gate | Syntax + function existence + grid operation tests | `tests_dsl.py` |
| Function dedup | Name-based dedup at injection to prevent duplicates | `beam_search_local.py` |
| ABPR execution traces | Traceback + pixel accuracy in diagnostic prompts | `evolve_qwen_arc.py` |
| D4 symmetry ensemble | 8-transform voting (4 rotations + 4 reflections) | `d4_ensemble.py` |
| MDL composition search | Enumerate DSL primitive chains (depth 1-3, no LLM) | `mdl_compose.py` |
| LoRA self-distillation | Train adapter on successful programs + synthetic tasks | `lora_train.py` |
| Synthetic task generation | TransCoder-style: failed programs → training pairs | `synthetic_tasks.py` |
| Concept-based scoring | LLM describes concept, scores match (ConceptSearch) | `concept_scoring.py` |
| DSL pruning | Remove dead/uncalled helper functions | `dsl_prune.py` |
| Function relevance ranking | DreamCoder-style context-aware function selection | `dsl_recognition.py` |
| Literature scanning | Daily arXiv + Semantic Scholar + OpenAlex scan | `literature_scan.py` |
| Temperature split | Low temp (0.1) for eval, adaptive (0.6-0.9) for generation | arXiv 2603.28304 |

---

## 2. Architecture: Three Nested Loops

```
Autoresearch (evolve_qwen_arc.py, 1926 lines) — hypothesis generation, experiment tracking
  |
  +-- Per round: EVALUATE -> DIAGNOSE -> HYPOTHESIZE -> INJECT -> EXPERIMENT -> ANALYZE -> DECIDE -> RECORD -> COMMIT
  |
  +-- Local Beam Search (beam_search_local.py, 838 lines) — mutation tournament
  |     |
  |     +-- N branches mutate dsl.py in parallel (3 branches default)
  |     +-- Qwen3.5-9B-4bit generates candidates via MLX
  |     +-- benchmark_dsl.py scores each variant (3-tier: helper, prompt, solve)
  |     +-- tests_dsl.py gates correctness
  |     +-- Winners survive to next round
  |     +-- Failed programs → synthetic_tasks.py (TransCoder data collection)
  |
  +-- Enhanced Solve Pipeline (solve_task_enhanced)
  |     |
  |     +-- Phase 0: MDL composition search (mdl_compose.py, free, ~2-5s/task)
  |     +-- Phase 1: Standard LLM solve (single inference)
  |     +-- Phase 2: D4 symmetry ensemble (d4_ensemble.py, 4-8 LLM calls)
  |     +-- Phase 3: Fallback single with varied temperature
  |
  +-- Self-Distillation (lora_train.py, triggered every ~15 new programs)
  |     |
  |     +-- Collects successful programs + synthetic tasks (50% cap)
  |     +-- Trains LoRA adapter (rank 4, 8 layers, 200 iters)
  |     +-- Canary validation on reliably-solved tasks
  |     +-- Adapter applied to future inference rounds
  |
  +-- MLX Inference (target_mlx_arc.py)
        |
        +-- Qwen3.5-9B-4bit (~5.5GB VRAM)
        +-- kv_bits=3 cache compression
        +-- Temperature split: eval=0.1, generation=adaptive
```

---

## 3. Novelty Claims

### What is new (verified against literature, April 2026)

1. **LLM-guided DSL evolution for ARC** — Prior work evolves model weights (SOAR, Pourcel et al. 2025) or uses fixed DSLs (ARGA, TransCoder). We evolve the DSL itself using an LLM as mutation proposer and beam search as selector. Closest paradigm: FunSearch (Romera-Paredes et al. 2023, Nature), which was never applied to ARC DSL growth.

2. **Diagnostic autoresearch loop with ABPR-style execution traces** — The outer loop diagnoses *why* tasks fail (3-tier scoring), generates hypotheses grounded in ARC research literature, and targets DSL growth at specific capability gaps. Inspired by ABPR (Qiu 2026), failing candidates' tracebacks and pixel accuracies are fed back into diagnostic prompts so the LLM can debug, not just guess. No published system combines execution-trace-informed hypothesis generation with code evolution for ARC.

3. **863-function evolved DSL** — Largest known DSL for ARC. ARGA uses ~50 hand-crafted ops. DreamCoder discovers abstractions via compression but was never applied to ARC at this scale. Our DSL grows empirically via LLM proposal + tournament selection, with function dedup to prevent bloat. DSL: 21,981 lines, 870KB.

4. **Local quantized evolution** — Running the full evolution loop on M4 16GB via Qwen3.5-9B-4bit + kv_bits=3 cache compression. No other ARC system runs at this scale locally. Directly addresses Chollet's thesis: intelligence = skill-acquisition efficiency, not raw compute.

5. **Self-repairing orchestration** — PROMPT-FIX MODE evolves not just the DSL toolbox but the strategy for using it (`build_prompt`, `analyze_task_deeply`). No published ARC system evolves its own orchestration layer.

6. **TransCoder-style synthetic task generation** — Failed beam search programs are applied to task inputs to create synthetic (task', program) pairs where the program IS the correct solution (Bednarek & Krawiec, 2410.04480). These feed LoRA self-distillation training, bootstrapping supervised data from otherwise-discarded programs. No published ARC system combines evolutionary search with self-distillation on synthetic failures.

7. **Multi-technique enhanced solving** — Combines MDL composition search (DreamCoder-inspired, no LLM needed), D4 symmetry augmentation (8 group transforms with verified inverses), and concept-based scoring (ConceptSearch, Singhal & Shroff, 2412.07322). Each technique addresses a different failure mode: MDL finds simple compositions the LLM misses, D4 handles orientation-invariant tasks, concept scoring provides richer signal than pixel accuracy alone.

8. **Autonomous overnight evolution with literature integration** — Evolution loop runs continuously in tmux; literature scanner queries arXiv + Semantic Scholar + OpenAlex across 10 search terms covering neuroevolution, neurosymbolic reasoning, evolutionary DSL, and ARC-specific work. New techniques are extracted and queued for injection.

9. **ARC-AGI-3 policy synthesis** — No published work on evolving POLICY_CODE for interactive ARC agents.

### Paradigm placement: iterative neurosymbolic program synthesis

Our system instantiates the emerging "P4" paradigm — iterative Program-to-Program
refinement where an LLM acts as both program synthesizer and mutation engine, with
symbolic execution providing the fitness signal. This neurosymbolic loop (neural
proposal → symbolic evaluation → feedback → refined proposal) is the same core
pattern behind o3's 87.5% ARC score and MIT's TTT-based 8B model. The key
differences in our instantiation:

- **We evolve the DSL, not just programs over a fixed DSL.** Most P4-style systems
  search within Python or a hand-crafted language. We grow the search space itself —
  the LLM proposes new primitives, the tournament validates them, and the DSL
  converges toward the empirical prior over ARC transformations. This is
  meta-level program synthesis: programs that change the program space.
- **We operate at commodity scale.** o3 spent an estimated $30K+ per task. We target
  >25% at <$50/task on a 16GB M4, demonstrating that the neurosymbolic loop works
  without brute-force compute — consistent with Chollet's thesis that intelligence
  is skill-acquisition efficiency, not raw search budget.
- **We learn from failure.** TransCoder-style synthetic task generation means every
  failed program attempt creates supervised training data, feeding back into LoRA
  self-distillation. The system's effective sample efficiency exceeds its raw solve
  rate.

### Universality argument

The autoresearch + beam search architecture is **domain-agnostic**. The same nested-loop design (diagnose failures → hypothesize fixes → inject → tournament → commit) could evolve DSLs for FlashFill, LOGO turtle graphics, or any program synthesis domain. Only the fitness function (`benchmark_dsl.py`) and data (`arc_agi_2_data/`) are ARC-specific. This is the strongest argument for Universality scoring.

### Nearest competitors

| System | Approach | Key Difference |
|--------|---------|---------------|
| ABPR (Qiu 2026) | Prolog + algorithmic debugging, 56.7% ARC-2 | Fixed language (Prolog), debugs programs not DSL. Closest competitor |
| SOAR (Pourcel 2025) | LLM + evolutionary search, 52% ARC-1 | Evolves model weights, not DSL |
| FunSearch (DeepMind 2023) | LLM-guided code evolution | Applied to cap sets, not ARC |
| DreamCoder (Ellis 2021) | Library learning via compression | E-graph refactoring, not LLM-guided |
| ARGA (Xu 2022) | Graph DSL + Tabu search | Fixed 50-op DSL, no evolution |
| TransCoder (Bednarek 2024) | Typed DSL + LLM synthesis | Fixed DSL (40 ops), synthetic tasks but no evolution |
| ConceptSearch (Singhal 2024) | FunSearch + concept scoring | No DSL evolution, fixed program space |
| KGMoN (Sorokin 2025) | Fine-tuned 4B model, 24% ARC-2 | No DSL, pure neural, Kaggle winner |
| Poetiq (2026) | Gemini 3 meta-system, 54% ARC-2 | Unconstrained ($30/task), no DSL |
| Greenblatt (2024) | GPT-4o generates ~8K Python programs/task | Fixed program space (Python), no DSL evolution |

---

## 4. Theoretical Framework

### Framing: Approximate Solomonoff Induction over a Learnable UTM

| Component | Role | Theory |
|-----------|------|--------|
| `dsl.py` (863 functions) | Universal Turing Machine bias | Solomonoff invariance theorem: UTM choice shifts complexity by O(1) |
| Beam search tournament | Approximate MAP inference | Selects p* = argmin \|p\| s.t. p(input) = output |
| Autoresearch loop | Active learning in program space | Diagnoses high-information failures, targets DSL growth |
| DSL evolution | Compression optimization | Each new helper reduces description length of solutions using it |
| LoRA self-distillation | Posterior sharpening | Fine-tunes LLM prior toward distribution of successful ARC programs |
| Synthetic task generation | Data augmentation in program space | Failed programs create supervised pairs, bootstrapping the prior |
| LLM (Qwen3.5-9B) | Approximate Solomonoff prior | Wan & Mei (2025): LLM training approximates Solomonoff via loss minimization |

### Key theoretical results supporting this approach

1. **Chollet (2019)** — Intelligence = skill-acquisition efficiency. ARC tests generalization with minimal priors. Our system's fixed DSL + evolution measures exactly this.

2. **Wan & Mei (2025)** — LLMs approximate Solomonoff induction. When our LLM proposes DSL mutations, it samples from an approximate Solomonoff prior over programs.

3. **Rathmanner & Hutter (2011)** — Solomonoff prior assigns higher probability to shorter programs (Occam's razor). MDL composition search (`mdl_compose.py`) directly implements this: shorter chains score higher.

4. **Lattimore & Hutter (2011)** — Universal bias succeeds across all structured domains, countering NFL theorems. Our DSL evolution discovers this bias empirically.

5. **DreamCoder (Ellis 2021)** — Library learning converges toward compression-optimal DSL. Our approach uses LLM-guided generation instead of E-graph refactoring but targets the same convergence. MDL composition search is a direct implementation of the "wake" phase.

6. **TransCoder (Bednarek & Krawiec 2024)** — Learning from mistakes: failed programs applied to inputs create synthetic tasks. Over 5 cycles: synthetic solve rate 1.72% → 21.66%. We implement this via `synthetic_tasks.py` feeding `lora_train.py`.

### Why it works (not just how)

The system solves ARC tasks not by memorizing patterns but by constructing a
*compression hierarchy* where each layer reduces the search space for the next:

1. **DSL as learned inductive bias.** Each helper function in dsl.py encodes a
   regularity discovered across ARC tasks (e.g., "grids often have mirror symmetry
   that needs completing"). This is not hand-engineering — the LLM proposes candidates
   and the tournament selects only those that improve solve rate. The DSL converges
   toward the empirical prior over ARC transformations.

2. **Diagnosis closes the loop.** Unlike blind evolutionary search, the autoresearch
   loop performs *causal diagnosis*: it identifies which tasks fail and classifies
   the failure mode (PROMPT_FAIL vs COMPOSE_FAIL vs WRONG_ANSWER). This creates an
   information gradient — new DSL functions are proposed specifically to fill
   diagnosed capability gaps, not randomly.

3. **Three-level optimization.** The system optimizes at three timescales:
   - **Fast (beam search):** Given the current DSL, find the best composition of
     existing helpers for each task. This is approximate MAP inference over programs.
   - **Medium (LoRA self-distillation):** Sharpen the LLM's prior toward successful
     programs, including synthetic tasks from failures. This improves future search.
   - **Slow (autoresearch):** When fast search fails, grow the DSL with new primitives.
     This is meta-learning — learning the hypothesis space itself.

   This mirrors the distinction between learning (fast), consolidation (medium), and
   evolution (slow) in biological intelligence, and between skill use, skill
   refinement, and skill acquisition in Chollet's framework.

4. **Learning from failure.** TransCoder-style synthetic task generation means every
   failed program attempt contributes training signal. The system's effective data
   efficiency is higher than the raw solve rate suggests — failed attempts are not
   wasted but recycled into supervised learning data.

5. **Prompt-fix mode as self-repair.** When the system detects that failures come from
   the orchestration layer (prompt builder) rather than missing primitives, it
   automatically switches to fixing `build_prompt()` / `analyze_task_deeply()`. This
   means the system can evolve not just its toolbox but its *strategy for using tools* —
   a form of metacognitive self-improvement.

### On DSL completeness

No formal proof exists that any finite DSL is sufficient for all ARC tasks (tasks are intentionally open-ended per Chollet's design). However:
- Any DSL with conditionals + loops + integer arithmetic is Turing-complete
- The practical question is **search efficiency**, not expressibility
- FlashFill++ (Cambronero et al. 2023) provides frameworks for managing DSL scaling
- Our evolution loop addresses this empirically: if a task fails, the DSL grows

---

## 5. Progress Tracking

### Current Scores

| Metric | Value | Date |
|--------|-------|------|
| DSL benchmark (composite) | 1.0000 (tier 1+2 ceiling) | 2026-04-05 |
| Helper coverage (helper_score) | 1.00 | 2026-04-05 |
| Prompt generation (prompt_score) | 1.00 | 2026-04-05 |
| Composition (compose_score) | 1.00 | 2026-04-05 |
| DSL function count | 863 | 2026-04-05 |
| DSL file size | 21,981 lines (870KB) | 2026-04-05 |
| Evolution rounds completed | 18 (current round in progress) | 2026-04-05 |
| Holdout solve rate (10 fixed tasks) | 0.19 mean (round 17) | 2026-04-05 |
| Best holdout task solve | 1.00 (2072aba6), 0.93 (890034e9) | 2026-04-05 |
| Beam search best score | 0.8178 (round 18 winner) | 2026-04-05 |
| Synthetic tasks collected | Active (TransCoder pipeline) | 2026-04-05 |
| LoRA training | Pipeline ready, triggers at 15 programs | 2026-04-05 |

### Hypothesis Implementation Status

| # | Hypothesis | Module | Status |
|---|-----------|--------|--------|
| H1 | Color canonicalization | `dsl.py` (inline) | Active |
| H2 | D4 symmetry ensemble | `d4_ensemble.py` | Deployed, pending restart |
| H3 | MDL composition search | `mdl_compose.py` | Deployed, pending restart |
| H4 | Persistent insight memory bank | TBD | Next hypothesis |

### Bottleneck Analysis

Tier 1+2 metrics have hit ceiling (1.0). The current bottleneck is **tier 3 solve accuracy** —
the LLM (Qwen3.5-9B) must compose DSL functions into correct solutions for unseen tasks.

Active mitigations:
- **D4 symmetry** (H2): 8-transform voting catches orientation-sensitive failures
- **MDL composition** (H3): Free pre-check finds simple chains the LLM misses
- **LoRA self-distillation**: Sharpens LLM prior toward successful program patterns
- **TransCoder synthetic tasks**: Bootstraps training data from failed attempts
- **Concept scoring**: Richer evaluation signal than pixel accuracy (opt-in)
- **Literature scanning**: 10 queries across neuroevolution, neurosymbolic, ARC domains

### SOTA Context (ARC-AGI-2, April 2026)

| System | ARC-AGI-2 Score | Cost/Task | Approach |
|--------|----------------|-----------|----------|
| Opus 4.6 (unconstrained) | 68.8% | high | Pure neural |
| ABPR (Qiu 2026) | 56.7% Pass@2 | moderate | Prolog + algorithmic debugging + Gemini-3-Flash |
| Poetiq (Gemini 3) | 54% | $30.57 | Meta-system, unconstrained |
| Anthropic Opus 4.5 | 37.6% | $2.20 | Thinking mode |
| KGMoN (Kaggle 1st, 2025) | 24% | $0.20 | Fine-tuned 4B model |
| **Target (our system)** | **>25%** | **<$50** | DSL evolution + beam search + self-distillation |

Note: All paradigms show 2-3x performance drops from ARC-AGI-1 to ARC-AGI-2
(ARC Prize technical report). The 85% Grand Prize ($200K) has never been claimed.
Paper Prize: $75K top, $375K outstanding pool, scored on 6 dimensions.

### Experiment Log

See `evolution_results/hypotheses.jsonl` for per-round records:
```json
{"round": N, "hypothesis": "...", "metric_before": 0.72, "metric_after": ..., "status": "accepted|rejected"}
```

Holdout trends: `evolution_results/holdout_scores.jsonl` (10 fixed tasks, scored every round).

---

## 6. Artifact Inventory

### Core Pipeline (20 Python files)

| File | Lines | Purpose | Track |
|------|-------|---------|-------|
| `evolve_qwen_arc.py` | 1,926 | Autoresearch outer loop (9-step rounds) | ARC-2 |
| `beam_search_local.py` | 838 | Local beam search (replaces codopt) | ARC-2 |
| `dsl.py` | 21,981 | Evolved DSL (863 functions) | ARC-2 + ARC-3 |
| `benchmark_dsl.py` | — | Fitness function (3-tier scoring) | ARC-2 |
| `tests_dsl.py` | — | Correctness gate | ARC-2 |
| `target_mlx_arc.py` | 518 | Local M4 MLX inference backend | ARC-2 |
| `target_kaggle_arc.py` | — | Kaggle A100/T4 inference backend | ARC-2 |
| `target_arc2_kaggle.py` | — | Alternative Kaggle target | ARC-2 |
| `target_arc3_agent.py` | — | Interactive neurosymbolic agent | ARC-3 |
| `d4_ensemble.py` | — | D4 symmetry augmentation (H2) | ARC-2 |
| `mdl_compose.py` | — | MDL composition search (H3) | ARC-2 |
| `lora_train.py` | 418 | LoRA self-distillation training | ARC-2 |
| `synthetic_tasks.py` | 289 | TransCoder synthetic task generation | ARC-2 |
| `concept_scoring.py` | 229 | ConceptSearch concept-based scoring | ARC-2 |
| `literature_scan.py` | 496 | arXiv + Semantic Scholar + OpenAlex scanner | Research |
| `dsl_prune.py` | — | Dead function pruner | ARC-2 |
| `dsl_recognition.py` | — | DreamCoder-style function relevance ranker | ARC-2 |
| `temperature_sweep.py` | — | Temperature optimization experiments | Research |
| `benchmark_arc3.py` | — | ARC-AGI-3 evaluation | ARC-3 |
| `run_arc3_baseline.py` | — | ARC-AGI-3 baseline runner | ARC-3 |

### Data & Results

| Directory | Contents |
|-----------|----------|
| `arc_data/data/training/` | ARC-AGI-1 (400 tasks) |
| `arc_agi_2_data/training/` | ARC-AGI-2 (1000+ tasks) |
| `evolution_results/` | hypotheses.jsonl, holdout_scores.jsonl, diagnostics, lora_adapters/ |
| `evolution_results/successful_programs.jsonl` | Programs that solved tasks (LoRA training data) |
| `evolution_results/synthetic_tasks.jsonl` | TransCoder synthetic (task, program) pairs |

### Dependencies

| Repo | Role | Status |
|------|------|--------|
| `turboquant-mlx/` | KV cache compression (venv with mlx-lm) | Active |
| `arc-dsl/` | Reference DSL (165 primitives, v0 seed) | Reference only |
| `codex-optimize/` | Beam-search via Codex agents (legacy) | Replaced by beam_search_local.py |
| `ARC-AGI-3-Agents/` | Official interactive agent framework | Active |
| `autoresearch/` | Karpathy's experiment loop (reference) | Reference only |

---

## 7. Dependency Graph

```
evolve_qwen_arc.py (outer loop, 1926 lines)
+-- dsl.py (mutated target, 863 functions)
|   +-- HELPER_CODE_PREFIX (evolved helper functions)
|   +-- build_prompt() (task encoding)
+-- beam_search_local.py (inner loop, 838 lines)
|   +-- benchmark_dsl.py (fitness: helper + prompt + composition)
|   +-- tests_dsl.py (correctness gate)
|   +-- synthetic_tasks.py (collect training data from failures)
+-- target_mlx_arc.py (Tier 3 solve eval)
|   +-- mlx-lm + Qwen3.5-9B-4bit
|   +-- kv_bits=3 cache compression
+-- d4_ensemble.py (D4 symmetry augmentation)
|   +-- 8 transforms with verified inverses
+-- mdl_compose.py (MDL composition pre-check)
|   +-- Depth 1-3 chains of DSL primitives
+-- lora_train.py (self-distillation, triggered periodically)
|   +-- successful_programs.jsonl (real programs)
|   +-- synthetic_tasks.jsonl (TransCoder pairs, 50% cap)
|   +-- mlx_lm.lora (adapter training)
+-- concept_scoring.py (opt-in concept-based scoring)
+-- literature_scan.py (technique extraction)
+-- evolution_results/
    +-- hypotheses.jsonl (per-round records)
    +-- holdout_scores.jsonl (fixed 10-task tracking)
    +-- lora_adapters/ (trained adapters)

target_kaggle_arc.py (standalone, cloud)
+-- vLLM or HF transformers
+-- dsl.py (helpers + prompt)

target_arc3_agent.py (standalone, interactive)
+-- dsl.py (frame analysis)
+-- POLICY_CODE (evolution target)
+-- ARC-AGI-3-Agents/agents/agent.py (base class)
```

---

## 8. Key Citations

| # | Paper | Year | Relevance |
|---|-------|------|-----------|
| 1 | Chollet, "On the Measure of Intelligence" | 2019 | ARC design principles, intelligence definition |
| 2 | Wan & Mei, "LLMs as Approximations to Solomonoff Induction" | 2025 | Theoretical grounding for LLM-as-prior |
| 3 | Romera-Paredes et al., "FunSearch" (Nature) | 2023 | LLM-guided evolutionary code search paradigm |
| 4 | Ellis et al., "DreamCoder" (PLDI) | 2021 | Library learning, DSL growth via compression |
| 5 | Pourcel et al., "SOAR" | 2025 | Self-improving LLM for ARC (evolves weights, not DSL) |
| 6 | Xu et al., "ARGA" (AAAI) | 2022 | Graph DSL + constraint search for ARC |
| 7 | Rathmanner & Hutter, "Solomonoff Induction" | 2011 | Formal basis for Occam's razor in program search |
| 8 | Chollet et al., "ARC Prize 2025 Technical Report" | 2026 | Competition results, winning paradigms |
| 9 | Vahdati et al., "The ARC of Progress towards AGI" (arxiv 2603.13372) | 2026 | Living survey: all paradigms 2-3x drop on ARC-AGI-2 |
| 10 | Macfarlane & Bonnet, "Latent Program Network" | 2024 | Alternative: gradient-based program search |
| 11 | Qiu et al., "ABPR" (arxiv 2603.20334) | 2026 | Prolog + algorithmic debugging, 56.7% ARC-AGI-2 |
| 12 | Chaudhry et al., "Recursive Concept Evolution" (arxiv 2602.15725) | 2026 | Compositional reasoning gaps |
| 13 | Greenblatt, "Getting 50% on ARC-AGI with GPT-4o" | 2024 | ~8K programs/task, fixed program space |
| 14 | ARC-TGI, "Task Generators for ARC" (arxiv 2603.05099) | 2026 | Synthetic data generation for ARC training |
| 15 | Bednarek & Krawiec, "TransCoder" (arxiv 2410.04480) | 2024 | Learning from mistakes: synthetic tasks from failed programs |
| 16 | Singhal & Shroff, "ConceptSearch" (arxiv 2412.07322) | 2024 | Concept-based scoring for program search (~30% more efficient) |
| 17 | arXiv 2603.28304, "Temperature Judge" | 2026 | Low temp for eval, high for generation — implemented |
