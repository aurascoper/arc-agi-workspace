# Literature Scan Log

## Scan Date: 2026-04-04
## Period: Last 90 days (2026-01-04 to 2026-04-04)
## Sources: arXiv (9 queries), Semantic Scholar (7 queries, 1 rate-limited)

---

## Paper Counts

| Search Query | Source | Results |
|---|---|---|
| "Abstraction and Reasoning Corpus" | arXiv | 6 |
| "ARC-AGI" | arXiv | 14 |
| "program synthesis" AND "grid" | arXiv | 0 |
| "domain specific language" AND "program induction" | arXiv | 0 |
| "inductive logic programming" AND "visual" | arXiv | 0 |
| "MLX" AND inference/Apple Silicon | arXiv | 4 |
| KV cache/TurboQuant AND quantization | arXiv | 15 |
| "Qwen" AND quantization/fine-tuning/distillation | arXiv | 15 |
| "Qwen" AND reasoning/code generation | arXiv | 15 |
| ARC-AGI abstract reasoning | S2 | 10 |
| program synthesis grid transformation | S2 | 10 |
| neurosymbolic reasoning visual patterns | S2 | 10 |
| MLX on-device inference Apple Silicon | S2 | 6 |
| KV cache quantization low-bit inference | S2 | 10 |
| Qwen quantization optimization | S2 | rate-limited |
| Qwen reasoning code generation | S2 | 10 |

**Total unique papers reviewed:** ~80 (after deduplication across queries)
**Relevant papers selected:** 32

## Technique Counts by Category

| Category | Count | Description |
|---|---|---|
| A: ARC-AGI Helper Functions | 12 | DSL primitives, grid operations, solver strategies |
| B: Inference Optimization | 14 | KV cache, MLX, quantization, Apple Silicon |
| C: Qwen Model Optimization | 6 | Fine-tuning, distillation, prompt strategies |
| **Total** | **32** | |

## Top 3 Most Interesting Papers

### 1. ITQ3_S: High-Fidelity 3-bit LLM Inference via Interleaved Ternary Quantization with Rotation-Domain Smoothing
- **arXiv:** 2603.27914 (2026-03-30)
- **Why:** Directly builds on TurboQuant (TQ) rotation-domain strategy with FWHT. Provides the missing CUDA kernel implementation that TurboQuant lacked, fusing inverse FWHT into the quantization pipeline. On RTX 5090, achieves FP16-competitive perplexity at 3-bit with >1.5x throughput over 4-bit. This is the most directly actionable paper for the TurboQuant component of the ARC pipeline.

### 2. Procedural Refinement by LLM-driven Algorithmic Debugging for ARC-AGI-2 (ABPR)
- **arXiv:** 2603.20334 (2026-03-20)
- **Why:** Achieves 56.67% Pass@2 on ARC-AGI-2 by coupling LLMs with formal algorithmic debugging (Shapiro's APD). Uses Prolog as target language with tree-structured execution traces for systematic bug localization. Directly applicable to the codopt refinement loop: instead of blind re-generation, present structured execution traces to the LLM for targeted program repair.

### 3. Embarrassingly Simple Self-Distillation Improves Code Generation (SSD)
- **arXiv:** 2604.01193 (2026-04-01)
- **Why:** Shows that simply sampling solutions from a model and fine-tuning on correct ones improves Qwen3-30B from 42.4% to 55.3% pass@1 on code generation. Zero-cost technique requiring no external data, teacher model, or RL. Directly applicable to Qwen3.5-9B-4bit for ARC: generate candidate DSL programs, filter correct ones, SFT. The mechanism (suppressing distractor tails while preserving exploration diversity) is well-understood.

## Notable Findings

- **ARC-AGI-3 is now live** (2603.24621): Interactive benchmark, 64x64 grids, 16 colors, 7 actions, RHAE scoring. Frontier AI scores <1% vs humans at 100%. This is a fundamentally different challenge requiring exploration, planning, and memory.
- **Refinement loops confirmed as winning strategy** (2601.10904): ARC Prize 2025 report confirms evolutionary program synthesis with feedback loops is the dominant approach. Validates codopt architecture.
- **Performance degradation 2-3x across ARC versions** (2603.13372): Living survey of 82 approaches shows all paradigms degrade similarly from AGI-1 to AGI-2, indicating fundamental compositional generalization limits.
- **KV cache compression is exploding**: 15+ papers in 90 days on KV cache quantization alone. The TurboQuant/FWHT rotation approach is gaining significant traction with multiple derivative works (ITQ3_S, TurboAngle, TurboESM).
- **RoPE-rotation incompatibility solved** (2603.26110): TurboESM paper derives the correct ordering: apply RoPE BEFORE orthogonal rotation to avoid fundamental incompatibility. Critical fix for applying TurboQuant to Qwen (which uses RoPE).
- **vllm-mlx** (2601.19139): Major infrastructure paper - 21-87% higher throughput than llama-cpp on Apple Silicon with continuous batching. Should be evaluated as inference backend replacement.
