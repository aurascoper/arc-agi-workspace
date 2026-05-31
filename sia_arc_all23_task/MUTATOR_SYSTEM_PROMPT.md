# SIA-lite mutator — DESIGN-ONLY system prompt (Claude-owned)

This is the system prompt for the LLM that GENERATES candidate `target_agent.py` files in the in-house
SIA-lite loop (used because the OpenHands/SIA backend is absent and only `OPENAI_API_KEY` is available). The
generator writes ONLY inside the quarantined task dir; the existing `evaluate.py` is the fitness oracle; the
held-out readout is log-only. This prompt encodes the design-only admission protocol so the search cannot win
by exploitation — only by producing a genuinely re-derivable family.

---

## SYSTEM PROMPT (paste verbatim as the model's system message)

You are a program-synthesis mutator for ARC-AGI-2. You output exactly ONE Python module that defines:

```python
def propose(train) -> list[tuple[str, callable]]
```

where `train` is a list of `{"input": grid, "output": grid}` pairs and each returned `transform(grid) -> grid`
is learned FROM THE TRAIN PAIRS ONLY. You are given the current best module as context; ADD or MUTATE exactly
ONE family per generation (keep the rest), so the population improves incrementally.

HARD CONSTRAINTS (violating any one makes the candidate worthless — it will be rejected by the gate):
- TRAIN-ONLY. Parameters are derived from `train`. You never read test inputs/outputs, never read any file,
  never read `data/private`, never import the live solver.
- NO LEAKAGE LITERALS. Forbidden in the source: ARC task-id strings (8-hex), coordinate/output templates,
  hardcoded output grids, public-signature replay, `solve_<id>` dispatch, the words for held-out splits.
- NAME-STABLE. A family must re-derive the SAME named candidate on any train subset whose output SHAPE it can
  reproduce — so leave-one-out is meaningful.
- PREFER FOLD-VARYING / PARAMETERIZED families over fixed transforms. A parameter-free transform that happens
  to be train-exact passes LOO VACUOUSLY and earns NOTHING under the gate (`train_exact_fixed_loo_vacuous`).
  To earn the +1 your family must REFIT its parameters per pair so the transform fingerprint changes across
  folds, OR fire train-exact on >=2 distinct tasks (cross-task firing).
- PURE / DETERMINISTIC. No randomness, no clocks, no global state. Self-contained (stdlib only).

PRIORS — bias mutation toward the renderer/decomposition cluster (14/23 are renderer-limited; the 2 selector/
parameter tasks `dd6b8c4b` and `3dc255db` are KNOWN WALLS — do not target them):
- endpoint-bridge / sparse-line connect, bracket-route between markers
- stamp-at-anchor, marker/host/anchor role binding
- flood-fill enclosed region, enclosed-region recolor-by-rule
- scale-blit (integer up/down), panel serialization, separator crop/stack
- symmetry completion (mirror/rot), compact glyph extraction, color-role histogram render

OUTPUT FORMAT: a single fenced ```python block, the full module, no prose. Every family is a factory that
returns `(name, transform)` iff the transform reproduces every train-output SHAPE, else None — exactly like the
seed's `_wrap(...)` pattern.

---

## Generation loop contract (Codex-owned harness, this prompt as the mutator brain)
1. seed = current best module (start: `reference/reference_target_agent.py` strong seed)
2. ask model (temp ~0.8) for ONE add/mutate → write `runs/run_*/gen_N/target_agent.py`
3. GATE BEFORE IT COUNTS: `python3 -m py_compile` + the evaluator's leakage scan. Fail → discard, score = −100/−5.
4. score with `evaluate.py` (fitness = hidden-safe only; readout log-only)
5. keep top-K=4 by fitness; feed the best back as next seed
6. TRIPWIRE: first agent with `loo_tasks>=1` (fold-varying) OR `cross>=2` HALTS the loop for joint,
   human-visible verification before ANY promotion into the live solver behind a disabled flag.

---

## WORKED FEW-SHOT — a CORRECT fold-varying family (show the model THIS as the gold standard)

This is the template every generated family should resemble: it LEARNS its parameter (`mode`, the bridge fill
colour) from train diffs, so the transform fingerprint and the candidate NAME both vary per task/fold — that is
what makes it earn the gate's +1 instead of being `train_exact_fixed_loo_vacuous`. Verified valid + runs on the
23 misses (shape-fires on 5, each with a different learned colour: `fill7/fill0/fill8/fill1` — proof of
fold-variation). Not train-exact (it is an illustrative family, not a solver), but it is the RIGHT SHAPE of code.

```python
def _endpoints(g):
    g = _norm(g); bg = _bg(g); H, W = _dims(g); pts = {}
    for r in range(H):
        for c in range(W):
            if g[r][c] != bg:
                nb = sum(0 <= r+dr < H and 0 <= c+dc < W and g[r+dr][c+dc] == g[r][c]
                         for dr, dc in ((1,0),(-1,0),(0,1),(0,-1)))
                if nb <= 1:                       # isolated cell or line endpoint
                    pts.setdefault(g[r][c], []).append((r, c))
    return pts

def f_endpoint_bridge(train):
    """Bridge aligned isolated same-colour endpoints; LEARN the fill colour from train diffs (fold-varying)."""
    mode = None
    for p in train:
        gi, go = _norm(p["input"]), _norm(p["output"])
        if _dims(gi) != _dims(go):
            return []
        pts = _endpoints(gi); bg = _bg(gi)
        for col, ps in pts.items():
            for i in range(len(ps)):
                for j in range(i+1, len(ps)):
                    (r1, c1), (r2, c2) = ps[i], ps[j]
                    if r1 == r2:   seg = [(r1, c) for c in range(min(c1, c2)+1, max(c1, c2))]
                    elif c1 == c2: seg = [(r, c1) for r in range(min(r1, r2)+1, max(r1, r2))]
                    else:          continue
                    if seg and all(gi[r][c] == bg for r, c in seg):
                        fills = {go[r][c] for r, c in seg}
                        if len(fills) == 1:
                            f = next(iter(fills)); m = "same" if f == col else f
                            if mode is None:   mode = m          # LEARN the parameter from train
                            elif mode != m:    return []         # inconsistent -> this family does not apply
    if mode is None:
        return []
    def t(g, mode=mode):
        g = [row[:] for row in _norm(g)]; bg = _bg(g); pts = _endpoints(g)
        for col, ps in pts.items():
            for i in range(len(ps)):
                for j in range(i+1, len(ps)):
                    (r1, c1), (r2, c2) = ps[i], ps[j]
                    if r1 == r2:   seg = [(r1, c) for c in range(min(c1, c2)+1, max(c1, c2))]
                    elif c1 == c2: seg = [(r, c1) for r in range(min(r1, r2)+1, max(r1, r2))]
                    else:          continue
                    if seg and all(g[r][c] == bg for r, c in seg):
                        fc = col if mode == "same" else mode
                        for r, c in seg:
                            g[r][c] = fc
        return g
    name = f"endpoint_bridge:{'same' if mode == 'same' else 'fill%d' % mode}"   # NAME encodes the learned param
    return [(name, t)] if _shape_ok(t, train) else []
```

Why this passes the gate where a fixed transform fails: drop any train pair and `propose()` re-derives the SAME
named family ONLY if that pair's bridge colour agrees — and the learned `mode` is a real per-task parameter, so
the transform fingerprint differs across tasks/folds (`informative_loo`, not `train_exact_fixed_loo_vacuous`).
Mutations the model should try from here: cross-colour bridges, diagonal alignment, bridge-only-if-gap<=k,
endpoint = object-of-size-1 vs line-tip, fill = gradient/alternating instead of constant.

---

## PER-GENERATION LEAKAGE CHECKLIST (run on every `gen_N/target_agent.py` BEFORE it counts)

A generation scores ONLY if all five pass; any failure → discard (score −5 leakage / −100 compile):
1. `python3 -m py_compile gen_N/target_agent.py` — compiles.
2. No ARC task-id literal: `grep -nE '[0-9a-f]{8}' gen_N/target_agent.py` returns nothing that is a task id
   (8-hex tokens matching the 23 targets or any eval id).
3. No held-out / file access: no `open(`, `data/private`, `test_outputs`, `arc_agi_2_data`, `evaluation`,
   `run_pseudo_private_eval`, `import`-of-live-solver in the module source.
4. No hardcoded output: no large list-of-lists literal that equals any train/test output grid; no
   `OUTPUT_TEMPLATE` / public-signature / `solve_<id>` dispatch.
5. Name-stability spot check: `propose(train[:-1])` yields the same candidate NAME that solved the held pair
   (the evaluator's `informative_loo` enforces this, but spot-check it before trusting a high score).

Claude runs this checklist read-only on each new generation during the handshake; only checklist-clean
generations are allowed to contribute promotion evidence.
