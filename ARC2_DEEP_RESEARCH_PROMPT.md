# ARC-AGI-2 Deep Research Prompt

Use this in a browser Deep Research session to investigate the next solver direction:
per-task / learned program synthesis over a richer ARC DSL.

```text
You are a research engineer helping design a competitive ARC-AGI-2 solver. I need a deep literature and systems review focused on per-task / learned program synthesis for abstract grid transformations, especially richer DSL search with routing, redraw, object graphs, abstraction growth, and learned proposal/ranking.

Context:
- We already have a symbolic ARC solver with many generalized operators, strict leave-one-train-out gates, synthetic invariance tests, and a hidden-facing mode.
- Remaining misses appear representation-limited: simple pixel repair, object keep/remove/recolor, periodic/symmetry, line extension, and local residual repair all fail under LOO.
- The hard cases require compositional construction: routing paths/brackets, redrawing structures, marker-host relational parameters, object-role selection, output-shape/decomposition, and abstraction growth.
- We need methods that can work per task from 2-5 train examples, avoid test leakage, and produce two ranked predictions under Kaggle runtime constraints.

Research goals:
1. Survey the strongest relevant work:
   - ARC solvers and ARC-AGI-2 approaches.
   - DreamCoder / library learning / wake-sleep abstraction growth.
   - Inductive program synthesis with neural guidance.
   - CEGIS, enumerative search, version-space algebra, constraint solving.
   - Object-centric visual reasoning and graph-based program synthesis.
   - Test-time training or neural proposal models for ARC-like tasks.
   - LLM-generated programs for ARC, including verification/ranking methods.
2. Extract practical design patterns that could improve a real ARC-AGI-2 notebook:
   - DSL primitives for routing, redraw, object graph edits, panels, serialization, symmetry, containment, contact, and marker-host relations.
   - Search strategy: enumerative, stochastic, MCTS, beam search, e-graphs, constraint-guided, or neural-guided.
   - Learned proposal/ranker design from synthetic ARC-like tasks.
   - How to generate synthetic tasks that teach routing/redraw/abstraction rather than memorized templates.
   - How to use LLM/code proposals safely without public/test leakage.
3. Recommend an implementation architecture:
   - A minimal but expressive object-graph DSL.
   - Program representation and type system.
   - Search loop and pruning constraints.
   - LOO and synthetic invariance gates.
   - Candidate ranking/verifier.
   - Kaggle runtime/module packaging plan.
4. Give a concrete 2-week build plan and a 48-hour prototype plan.
5. Identify risks:
   - overfitting to public eval,
   - train-exact but non-general rules,
   - task-ID/template leakage,
   - runtime blowups,
   - neural model dependency/package issues.
6. Output:
   - prioritized bibliography with links,
   - summary table of methods,
   - recommended solver architecture,
   - DSL primitive list,
   - synthetic data plan,
   - evaluation/admission protocol,
   - first 5 experiments to implement.

Bias toward actionable engineering details, not a generic AI survey. Include citations and links. If evidence is weak or anecdotal, label it as such.
```

## Companion Prompt For Claude

```text
Use the Deep Research output to design standalone ARC-AGI-2 program-synthesis probes only. Do not edit arc2_candidate_solver.py or submission_helper.py.

Coordinate with Codex through ARC2_AGENT_COORDINATION_STATUS.md. For every prototype, report:
- train exactness,
- leave-one-train-out,
- synthetic invariance,
- local design/calibration readout,
- leakage/static scan,
- whether a concrete transform handoff exists.

Prioritize probes for:
1. object-graph routing/redraw,
2. marker-host apex/pointing parameters,
3. bracket/path routing with recolor,
4. output-shape decomposition/rendering,
5. abstraction-growth/library learning over reusable ARC DSL fragments.

Only hand off to Codex when a transform is train-exact, LOO-stable, and has a concrete implementation sketch without task IDs, public templates, coordinate signatures, or test-output-derived rules.
```
