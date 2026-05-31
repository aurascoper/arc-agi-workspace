# ARC2 Next Deep Research Brief

Use this instead of pasting the entire prior report when starting the next Deep Research pass.

## What To Ignore

- Ignore the huge local git history and any failed full-branch push context. It dragged old large blobs such as optimizer checkpoints and synthetic JSONL histories; it is irrelevant to the research question.
- Ignore generic pixel repair, object keep/remove/recolor, symmetry/periodic, naive object-extension, and broad TTA as primary next directions. Local standalone probes have already falsified these on the current 23 strict design misses.
- Do not treat train-exact alone as evidence. The host-apex router for `3dc255db` shows the trap: train-exact and even one LOO-style check can still fail the held-out readout or select the wrong marker role.

## Current Evidence Baseline

- Strict hidden-facing design estimate before this handoff: `57/80`, pair `74/108`.
- Strict hidden-facing calibration estimate: `29/40`, pair `39/59`.
- Public guard remained `120/120`, pair `167/167` in the last verified solver state.
- Current 23 genuine design misses are classified as:
  - `renderer=14`
  - `decomposition=7`
  - `selector=1`
  - `parameter=1`
- The close but unsolved cases are:
  - `dd6b8c4b`: fill-panel render is expressible with oracle consumed markers, but the input-only consumed-marker selector is not solved.
  - `3dc255db`: ray/segment render is expressible, but host/marker role, apex/direction, and parameter selection remain unstable.
- `cb2d8a2c` and `36a08778` are not simple object extension. They look like conditional path/bracket routing plus recolor.

## Research Question For The Next Pass

Design a competition-feasible typed object-graph program synthesis system for ARC-AGI-2 that can be implemented incrementally in the existing solver.

Focus on:

1. A minimal but expressive DSL for:
   - multi-view object parsing,
   - relation graphs,
   - shape/decomposition prediction,
   - marker-host binding,
   - apex/pointing detection,
   - orthogonal/bracket routing,
   - redraw/stamp/pack operations,
   - bounded residual repair.
2. A typed sketch enumerator:
   - shapes/decomposition first,
   - object-role binding second,
   - route/redraw execution third,
   - repair last.
3. Learned guidance:
   - predict shape family,
   - predict sketch family,
   - predict likely role bindings,
   - rank candidates.
4. Synthetic generators:
   - route/bracket tasks,
   - marker-host binding tasks,
   - panel/decomposition tasks,
   - redraw/stamp/serialization tasks.
5. Admission:
   - exact train,
   - leave-one-train-out,
   - synthetic invariance,
   - no task IDs/templates/public-signature replay,
   - local design/calibration readout only after pre-registration.

## Desired Output

Return a concrete implementation spec, not another generic survey:

- object-graph IR schema,
- DSL primitive signatures,
- sketch grammar,
- search/pruning algorithm,
- learned proposer/ranker inputs and outputs,
- synthetic task generator recipes,
- runtime budget plan for Kaggle,
- first 48-hour prototype tasks,
- first five acceptance tests.

## Files In This Handoff Branch

- `ARC2_PROGRAM_SYNTHESIS_DEEP_RESEARCH.md`: full prior Deep Research output.
- `ARC2_DEEP_RESEARCH_PROMPT.md`: original prompt plus companion Claude prompt.
- `ARC2_AGENT_COORDINATION_STATUS.md`: coordination ledger and verified evidence.
- `arc2_*`: standalone probes and falsification scripts.
- `tmp/claude*.json`, `tmp/codex*.json`: result snapshots.
