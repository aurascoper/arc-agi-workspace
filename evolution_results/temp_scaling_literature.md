# Temperature Scaling Literature Findings (2026-04-05)

## Sources Scanned
- arXiv: 4 queries, 180-day lookback
- OpenAlex: 4 queries
- MCP arxiv + semantic scholar: 5 targeted searches
- Total papers found: 20 (listing) + 7 (deep analysis)

## Key Papers

### 1. "Hot or Cold? AdapT" (2309.02772, Zhu et al. 2023)
- For **pass@1**: temps **0.2-0.4** outperform greedy
- For **pass@k** (k>1): temps **0.6-0.8** are better for diversity
- Fixed temperature is suboptimal — adaptive per-token temperature is ideal

### 2. "Bag of Tricks for Inference-time Computation" (2502.07191, Liu et al. 2025)
- 20,000+ A100 GPU hours, 1,000+ experiments across **Llama, Qwen, Mistral**
- "Tuning temperature can improve reasoning by up to **5%**"
- Optimal for reasoning: **0.3-0.5 range**
- For Best-of-N with verification, moderate temps beat both greedy and high temp

### 3. "Reliability Under Randomness: Sparse vs Dense Models" (2601.00942, Grover 2026)
- **MoE architecture does NOT need special temp treatment when instruction-tuned**
- Sparse instruction-tuned (Mixtral) ≈ dense instruction-tuned (Qwen2.5) across all temps
- Sparse base models degrade at high temp, but this is instruction-tuning effect, not architecture
- Safe range for instruction-tuned MoE: up to ~0.6-0.8

### 4. "OSCA" (2410.22480, Zhang et al. 2024)
- A **portfolio of temperatures** is better than a single one
- Learned allocation across temps achieves same accuracy with **128x less compute**
- Directly validates multi-temperature beam search approach

### 5. "Global Forking Tokens" (2510.05132, Jia et al. 2025)
- For **hard problems**, temp above ~0.5 adds more noise than useful diversity
- High temp introduces noise at ALL token positions, not just decision-critical ones
- Combine moderate temp with other diversity mechanisms

### 6. "SSD on Qwen3" (2604.01193, Zhang et al. 2026)
- Studies Qwen3-30B-Instruct specifically
- Identifies "precision-exploration conflict" in decoding
- A spread of temperatures captures different solution modes better than one fixed temp

### 7. "Codex/HumanEval" (2107.03374, Chen et al. 2021)
- Foundational: T=0.0/0.2 best for pass@1; T=0.8 best for pass@100
- T=0.75 appropriate only with 50-100+ candidates and strong verifier

## Actionable Synthesis

### Current config [0.0, 0.35, 0.75] is suboptimal:
- **T=0.75 is too high** for small k (5 candidates). Literature shows noise threshold at ~0.5-0.6 for hard reasoning.
- 60% of candidates (3/5) are at T=0.75 — wastes compute on incoherent outputs.

### Recommended config: [0.0, 0.3, 0.5]
- Keeps max temp below 0.5-0.6 noise threshold
- Provides meaningful diversity (0.0 → 0.3 → 0.5 spread)
- Supported by Bag of Tricks (0.3-0.5 sweet spot for reasoning)
- OSCA validates multi-temp portfolio approach

### For reflection passes: use lower temp
- AdapT shows "confident tokens" (repair context) need less exploration
- Reflection already has structured error feedback → lower temp is better
- Recommendation: reflection at **0.1** (near-greedy targeted repair)

### MoE (Qwen3) is safe:
- Grover 2026 paper is definitive: instruction-tuning dominates, MoE architecture is irrelevant
- No special handling needed

### Sweep configs to prioritize:
1. **C [0.0, 0.3, 0.5]** — literature-recommended (PRIORITY)
2. **B [0.0, 0.2, 0.4]** — viable but may be too conservative
3. **D [0.0, 0.1, 0.3, 0.5]** — fine-grained with 4 unique temps
4. **A [0.0, 0.35, 0.75]** — baseline for comparison only
5. **E [0.0, 0.15, 0.35, 0.6]** — test 0.6 boundary
6. **F [0.0, 0.1, 0.2]** — test if exploration is needed at all
