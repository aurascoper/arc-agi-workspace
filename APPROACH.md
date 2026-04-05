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
| Generalize from few examples | 800 composable helpers reduce search space | `dsl.py` (783KB, 800 functions) | Living artifact |
| $50/task compute budget | Qwen2.5-14B on 2xT4 (fp8, TP=2) | `target_kaggle_arc.py` (vLLM backend) | Working |
| Offline Kaggle notebook | %%writefile + kaggle dataset modules | `target-arc2-agi-dsl.ipynb` | Working |
| Partial credit (pixel accuracy) | Spatial Hausdorff + color accuracy metric | `target_mlx_arc.py:calculate_pixel_accuracy` | Working |

### ARC-AGI-3 (Interactive, API)

| Criterion | Our Approach | Artifact | Status |
|-----------|-------------|----------|--------|
| Explore unknown environments | Phase 1: systematic probing (9 actions, causal model) | `target_arc3_agent.py:NeurosymbolicAgent` | WIP |
| Plan and act in real-time | Phase 2: BFS over causal graph + optional LLM assist | `target_arc3_agent.py:choose_action` | WIP |
| Adapt policy per episode | POLICY_CODE string evolved by codopt | `target_arc3_agent.py:POLICY_CODE` | Scaffolded |
| Agent lifecycle compliance | Extends official `Agent` base class | `ARC-AGI-3-Agents/agents/agent.py` | Working |

### Local Development (M4 16GB)

| Capability | Implementation | Artifact |
|-----------|---------------|----------|
| Local LLM inference | Qwen3.5-9B-4bit via MLX (~5.5GB) | `target_mlx_arc.py` |
| KV cache compression | TurboQuant 3-bit (Walsh-Hadamard + Lloyd-Max) | `turboquant-mlx/` |
| DSL evolution | Autoresearch outer loop + codopt inner loop | `evolve_qwen_arc.py` |
| Fitness evaluation | 3-tier: helper coverage, prompt gen, solve accuracy | `benchmark_dsl.py` |
| Correctness gate | Syntax + function existence + grid operation tests | `tests_dsl.py` |
| Function dedup | Name-based dedup at injection to prevent duplicates | `beam_search_local.py` |
| ABPR execution traces | Traceback + pixel accuracy in diagnostic prompts | `evolve_qwen_arc.py` |
| Remote monitoring | Overnight agent analyzes evolution progress via GitHub | Remote trigger |
| Literature scout | Daily arXiv + Semantic Scholar scan for new techniques | Remote trigger |
| Auto-push | Evolution results pushed to GitHub after each round | `evolve_qwen_arc.py` |

---

## 2. Architecture: Three Nested Loops

```
Autoresearch (evolve_qwen_arc.py) — hypothesis generation, experiment tracking
  |
  +-- Per round: EVALUATE -> DIAGNOSE -> HYPOTHESIZE -> INJECT -> EXPERIMENT -> ANALYZE -> DECIDE -> RECORD -> COMMIT
  |
  +-- Codopt (codex-optimize) — beam-search mutation tournament
  |     |
  |     +-- N branches mutate dsl.py in parallel
  |     +-- benchmark_dsl.py scores each variant
  |     +-- tests_dsl.py gates correctness
  |     +-- Winners survive to next round
  |
  +-- TurboQuant-MLX (inner) — 3-bit KV compressed inference
        |
        +-- Qwen3-30B-A3B-4bit generates candidate solutions
        +-- Adaptive cache: 3-bit body, fp16 first/last 4 layers
```

---

## 3. Novelty Claims

### What is new (verified against literature, April 2026)

1. **LLM-guided DSL evolution for ARC** — Prior work evolves model weights (SOAR, Pourcel et al. 2025) or uses fixed DSLs (ARGA, TransCoder). We evolve the DSL itself using an LLM as mutation proposer and codopt as selector. Closest paradigm: FunSearch (Romera-Paredes et al. 2023, Nature), which was never applied to ARC DSL growth.

2. **Diagnostic autoresearch loop with ABPR-style execution traces** — The outer loop diagnoses *why* tasks fail (3-tier scoring), generates hypotheses grounded in ARC research literature, and targets DSL growth at specific capability gaps. Inspired by ABPR (Qiu 2026), failing candidates' tracebacks and pixel accuracies are fed back into diagnostic prompts so the LLM can debug, not just guess. No published system combines execution-trace-informed hypothesis generation with code evolution for ARC.

3. **800-function evolved DSL** — Largest known DSL for ARC. ARGA uses ~50 hand-crafted ops. DreamCoder discovers abstractions via compression but was never applied to ARC. Our DSL grows empirically via LLM proposal + tournament selection, with function dedup to prevent bloat.

4. **Local quantized evolution** — Running the full evolution loop on M4 16GB via Qwen3.5-9B-4bit + TurboQuant 3-bit KV cache compression. No other ARC system runs at this scale locally. Directly addresses Chollet's thesis: intelligence = skill-acquisition efficiency, not raw compute.

5. **Self-repairing orchestration** — PROMPT-FIX MODE evolves not just the DSL toolbox but the strategy for using it (`build_prompt`, `analyze_task_deeply`). No published ARC system evolves its own orchestration layer.

6. **Autonomous overnight evolution with remote monitoring** — Evolution loop auto-pushes results to GitHub; a remote Claude agent monitors progress every 3 hours, detects stagnation, and proposes corrections. A second remote agent scans arXiv + Semantic Scholar daily for new techniques to inject into the literature hints.

7. **ARC-AGI-3 policy synthesis via codopt** — No published work on evolving POLICY_CODE for interactive ARC agents.

### Universality argument

The codopt + autoresearch architecture is **domain-agnostic**. The same nested-loop design (diagnose failures -> hypothesize fixes -> inject -> tournament -> commit) could evolve DSLs for FlashFill, LOGO turtle graphics, or any program synthesis domain. Only the fitness function (`benchmark_dsl.py`) and data (`arc_agi_2_data/`) are ARC-specific. This is the strongest argument for Universality scoring.

### Nearest competitors

| System | Approach | Key Difference |
|--------|---------|---------------|
| ABPR (Qiu 2026) | Prolog + algorithmic debugging, 56.7% ARC-2 | Fixed language (Prolog), debugs programs not DSL. Closest competitor |
| SOAR (Pourcel 2025) | LLM + evolutionary search, 52% ARC-1 | Evolves model weights, not DSL |
| FunSearch (DeepMind 2023) | LLM-guided code evolution | Applied to cap sets, not ARC |
| DreamCoder (Ellis 2021) | Library learning via compression | E-graph refactoring, not LLM-guided |
| ARGA (Xu 2022) | Graph DSL + Tabu search | Fixed 50-op DSL, no evolution |
| KGMoN (Sorokin 2025) | Fine-tuned 4B model, 24% ARC-2 | No DSL, pure neural, Kaggle winner |
| Poetiq (2026) | Gemini 3 meta-system, 54% ARC-2 | Unconstrained ($30/task), no DSL |
| Greenblatt (2024) | GPT-4o generates ~8K Python programs/task | Fixed program space (Python), no DSL evolution |

---

## 4. Theoretical Framework

### Framing: Approximate Solomonoff Induction over a Learnable UTM

| Component | Role | Theory |
|-----------|------|--------|
| `dsl.py` (622 functions) | Universal Turing Machine bias | Solomonoff invariance theorem: UTM choice shifts complexity by O(1) |
| Codopt tournament | Approximate MAP inference | Selects p* = argmin \|p\| s.t. p(input) = output |
| Autoresearch loop | Active learning in program space | Diagnoses high-information failures, targets DSL growth |
| DSL evolution | Compression optimization | Each new helper reduces description length of solutions using it |
| LLM (Qwen3-30B) | Approximate Solomonoff prior | Wan & Mei (2025): LLM training approximates Solomonoff via loss minimization |

### Key theoretical results supporting this approach

1. **Chollet (2019)** — Intelligence = skill-acquisition efficiency. ARC tests generalization with minimal priors. Our system's fixed DSL + evolution measures exactly this.

2. **Wan & Mei (2025)** — LLMs approximate Solomonoff induction. When our LLM proposes DSL mutations, it samples from an approximate Solomonoff prior over programs.

3. **Rathmanner & Hutter (2011)** — Solomonoff prior assigns higher probability to shorter programs (Occam's razor). Shorter DSL compositions should be preferred — encodable as regularization in codopt fitness.

4. **Lattimore & Hutter (2011)** — Universal bias succeeds across all structured domains, countering NFL theorems. Our DSL evolution discovers this bias empirically.

5. **DreamCoder (Ellis 2021)** — Library learning converges toward compression-optimal DSL. Our approach uses LLM-guided generation instead of E-graph refactoring but targets the same convergence.

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

3. **Two-level evolution.** The system evolves at two timescales:
   - **Fast (codopt):** Given the current DSL, find the best composition of existing
     helpers for each task. This is approximate MAP inference over programs.
   - **Slow (autoresearch):** When fast search fails, grow the DSL with new primitives.
     This is meta-learning — learning the hypothesis space itself.
   
   This mirrors the distinction between learning (fast) and evolution (slow) in
   biological intelligence, and between skill use vs. skill acquisition in Chollet's
   framework.

4. **Prompt-fix mode as self-repair.** When the system detects that failures come from
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
| DSL benchmark (composite) | 1.0000 (tier 1+2 ceiling) | 2026-04-04 |
| Helper coverage (helper_score) | 1.00 | 2026-04-04 |
| Prompt generation (prompt_score) | 1.00 | 2026-04-04 |
| Composition (compose_score) | 1.00 | 2026-04-04 |
| DSL function count | 800 | 2026-04-04 |
| Evolution rounds completed | 49+ (multiple restart cycles) | 2026-04-04 |
| Commits from evolution | 3 (44f80e3, 4aa3e2c, 98d190f) | 2026-04-03 |
| GitHub repo | `aurascoper/arc-agi-workspace` (private) | 2026-04-04 |
| Remote triggers | Overnight monitor (3h) + Literature scout (daily) | 2026-04-04 |
| ARC-AGI-3 levels completed | 0 (framework scaffolded) | 2026-04-02 |

### Bottleneck Analysis

Tier 1+2 metrics have hit ceiling (1.0). The current bottleneck is **tier 3 solve accuracy** —
the LLM (Qwen3.5-9B) must compose DSL functions into correct solutions for unseen tasks.
The system now focuses exclusively on tier 3 improvements: proposing new DSL primitives
that help the LLM solve the 2 remaining tier 3 failures (e.g., `34b99a2b.json`, `b6afb2da.json`).

ABPR-style execution traces (tracebacks + pixel accuracy) are now included in diagnostic
prompts to help the LLM debug failures rather than guessing blindly. Function dedup prevents
the model from injecting semantically identical functions with different names.

### SOTA Context (ARC-AGI-2, April 2026)

| System | ARC-AGI-2 Score | Cost/Task | Approach |
|--------|----------------|-----------|----------|
| Opus 4.6 (unconstrained) | 68.8% | high | Pure neural |
| ABPR (Qiu 2026) | 56.7% Pass@2 | moderate | Prolog + algorithmic debugging + Gemini-3-Flash |
| Poetiq (Gemini 3) | 54% | $30.57 | Meta-system, unconstrained |
| Anthropic Opus 4.5 | 37.6% | $2.20 | Thinking mode |
| KGMoN (Kaggle 1st, 2025) | 24% | $0.20 | Fine-tuned 4B model |
| **Target (our system)** | **>25%** | **<$50** | DSL evolution + codopt |

Note: All paradigms show 2-3x performance drops from ARC-AGI-1 to ARC-AGI-2
(ARC Prize technical report). The 85% Grand Prize ($200K) has never been claimed.
Paper Prize: $75K top, $375K outstanding pool, scored on 6 dimensions.

### Experiment Log

See `evolution_results/hypotheses.jsonl` for per-round records:
```json
{"round": N, "hypothesis": "...", "metric_before": 0.72, "metric_after": ..., "status": "accepted|rejected"}
```

---

## 6. Artifact Inventory

### Core Pipeline

| File | Purpose | Track |
|------|---------|-------|
| `evolve_qwen_arc.py` | Autoresearch outer loop (~1150 lines) | ARC-2 |
| `dsl.py` | Evolved DSL (783KB, 800 functions) | ARC-2 + ARC-3 |
| `benchmark_dsl.py` | Codopt fitness function | ARC-2 |
| `tests_dsl.py` | Codopt correctness gate | ARC-2 |
| `target_mlx_arc.py` | Local M4 inference backend | ARC-2 |
| `target_kaggle_arc.py` | Kaggle A100/T4 inference backend | ARC-2 |
| `target_arc3_agent.py` | Interactive neurosymbolic agent | ARC-3 |
| `run_codopt.sh` | Codopt launcher script | ARC-2 |
| `imu_live.py` | Apple Silicon IMU dashboard (curses TUI) | Diagnostics |

### Remote Agents (claude.ai scheduled triggers)

| Trigger | Schedule | Repo | Purpose |
|---------|----------|------|---------|
| ARC Evolution Overnight Monitor | Every 3h (midnight-6AM CDT) | `aurascoper/arc-agi-workspace` | Analyze evolution progress, detect stagnation, propose corrections |
| ARC-AGI Literature Scout | Daily 2:30PM CDT | `aurascoper/arc-agi-workspace` | Scan arXiv + Semantic Scholar, extract technique ideas |

### Data

| Directory | Contents |
|-----------|----------|
| `arc_data/data/training/` | ARC-AGI-1 (400 tasks) |
| `arc_agi_2_data/training/` | ARC-AGI-2 (1000+ tasks) |
| `evolution_results/` | Hypothesis log, diagnostics |

### Dependencies

| Repo | Role |
|------|------|
| `codex-optimize/` | Beam-search code mutation (inner loop) |
| `turboquant-mlx/` | 3-bit KV cache compression |
| `arc-dsl/` | Reference DSL (165 primitives, v0 seed) |
| `ARC-AGI-3-Agents/` | Official interactive agent framework |
| `autoresearch/` | Karpathy's experiment loop (reference) |
| `model_baseline/` | OpenAI baseline (alternative approach) |

---

## 7. Dependency Graph

```
evolve_qwen_arc.py (outer)
+-- dsl.py (mutated target)
|   +-- HELPER_CODE_PREFIX (evolved functions)
|   +-- build_prompt() (task encoding)
+-- codopt (middle)
|   +-- benchmark_dsl.py (fitness: helper + prompt + composition)
|   +-- tests_dsl.py (correctness gate)
+-- target_mlx_arc.py (Tier 3 solve eval)
|   +-- mlx-lm + Qwen3-30B-A3B-4bit
|   +-- turboquant-mlx (3-bit KV cache)
+-- evolution_results/hypotheses.jsonl

target_kaggle_arc.py (standalone, cloud)
+-- vLLM or HF transformers
+-- dsl.py (helpers + prompt)

target_arc3_agent.py (standalone, interactive)
+-- dsl.py (frame analysis)
+-- POLICY_CODE (codopt target)
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
| 11 | Qiu et al., "ABPR" (arxiv 2603.20334) | 2026 | Prolog + algorithmic debugging, 56.7% ARC-AGI-2. Closest neuro-symbolic competitor |
| 12 | Chaudhry et al., "Recursive Concept Evolution" (arxiv 2602.15725) | 2026 | Compositional reasoning gaps — latent-space analog of our DSL evolution |
| 13 | Greenblatt, "Getting 50% on ARC-AGI with GPT-4o" | 2024 | ~8K programs/task, 85% would need ~100M programs. Fixed program space |
| 14 | ARC-TGI, "Task Generators for ARC" (arxiv 2603.05099) | 2026 | Synthetic data generation for ARC training |
