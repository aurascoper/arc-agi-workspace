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
| Generalize from few examples | 559 composable helpers reduce search space | `dsl.py` (558KB, 559 functions) | Living artifact |
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
| Local LLM inference | Qwen3-30B-A3B-4bit via MLX (~7GB) | `target_mlx_arc.py` |
| KV cache compression | TurboQuant 3-bit (Walsh-Hadamard + Lloyd-Max) | `turboquant-mlx/` |
| DSL evolution | Autoresearch outer loop + codopt inner loop | `evolve_qwen_arc.py` |
| Fitness evaluation | 3-tier: helper coverage, prompt gen, solve accuracy | `benchmark_dsl.py` |
| Correctness gate | Syntax + function existence + grid operation tests | `tests_dsl.py` |

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

2. **Diagnostic autoresearch loop** — The outer loop diagnoses *why* tasks fail (3-tier scoring), generates hypotheses grounded in ARC research literature, and targets DSL growth at specific capability gaps. No published system combines diagnosis-driven hypothesis generation with code evolution for ARC.

3. **559-function evolved DSL** — Largest known DSL for ARC. ARGA uses ~50 hand-crafted ops. DreamCoder discovers abstractions via compression but was never applied to ARC. Our DSL grows empirically via LLM proposal + tournament selection.

4. **Local quantized evolution** — Running the full evolution loop on M4 16GB via TurboQuant 3-bit KV cache compression. No other ARC system runs at this scale locally.

5. **ARC-AGI-3 policy synthesis via codopt** — No published work on evolving POLICY_CODE for interactive ARC agents.

### Nearest competitors

| System | Approach | Key Difference |
|--------|---------|---------------|
| SOAR (Pourcel 2025) | LLM + evolutionary search, 52% ARC-1 | Evolves model weights, not DSL |
| FunSearch (DeepMind 2023) | LLM-guided code evolution | Applied to cap sets, not ARC |
| DreamCoder (Ellis 2021) | Library learning via compression | E-graph refactoring, not LLM-guided |
| ARGA (Xu 2022) | Graph DSL + Tabu search | Fixed 50-op DSL, no evolution |
| KGMoN (Sorokin 2025) | Fine-tuned 4B model, 24% ARC-2 | No DSL, pure neural, Kaggle winner |
| Poetiq (2026) | Gemini 3 meta-system, 54% ARC-2 | Unconstrained ($30/task), no DSL |

---

## 4. Theoretical Framework

### Framing: Approximate Solomonoff Induction over a Learnable UTM

| Component | Role | Theory |
|-----------|------|--------|
| `dsl.py` (559 functions) | Universal Turing Machine bias | Solomonoff invariance theorem: UTM choice shifts complexity by O(1) |
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
| DSL benchmark (fast mode) | 0.72 | 2026-04-02 |
| DSL function count | 559 | 2026-04-02 |
| Helper coverage | 100% (8/8 core functions) | 2026-04-02 |
| Prompt generation | ~30% | 2026-04-02 |
| Evolution rounds completed | 0 (Round 1 diagnostic generated) | 2026-04-02 |
| ARC-AGI-3 levels completed | 0 (framework scaffolded) | 2026-04-02 |

### SOTA Context (ARC-AGI-2, April 2026)

| System | Private Score | Cost/Task |
|--------|-------------|-----------|
| Poetiq (Gemini 3) | 54% | $30.57 |
| Anthropic Opus 4.5 | 37.6% | $2.20 |
| KGMoN (Kaggle winner) | 24% | $0.20 |
| **Target (our system)** | **>25%** | **<$50** |

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
| `evolve_qwen_arc.py` | Autoresearch outer loop (830 lines) | ARC-2 |
| `dsl.py` | Evolved DSL (558KB, 559 functions) | ARC-2 + ARC-3 |
| `benchmark_dsl.py` | Codopt fitness function | ARC-2 |
| `tests_dsl.py` | Codopt correctness gate | ARC-2 |
| `target_mlx_arc.py` | Local M4 inference backend | ARC-2 |
| `target_kaggle_arc.py` | Kaggle A100/T4 inference backend | ARC-2 |
| `target_arc3_agent.py` | Interactive neurosymbolic agent | ARC-3 |
| `run_codopt.sh` | Codopt launcher script | ARC-2 |

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
| 5 | Pourcel et al., "SOAR" | 2025 | Closest competitor: self-improving LLM for ARC |
| 6 | Xu et al., "ARGA" (AAAI) | 2022 | Graph DSL + constraint search for ARC |
| 7 | Rathmanner & Hutter, "Solomonoff Induction" | 2011 | Formal basis for Occam's razor in program search |
| 8 | Chollet et al., "ARC Prize 2025 Technical Report" | 2026 | Competition results, winning paradigms |
| 9 | Vahdati et al., "The ARC of Progress towards AGI" | 2026 | Living survey of ARC approaches |
| 10 | Macfarlane & Bonnet, "Latent Program Network" | 2024 | Alternative: gradient-based program search |
