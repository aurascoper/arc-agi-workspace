# Per-Task Program Synthesis for ARC-AGI-2

Your uploaded coverage-wall brief is a strong problem statement for what to build next, and I am treating it as the implementation-specific baseline for this review. fileciteturn0file0

## Framing and verdict

The literature points to a **mixed wall with a representation-limited center and a search/repair-limited edge**. In other words, there is probably a real tranche of misses that will flip under shape-first search plus bounded residual repair, but the miss families you named — routing, brackets, redraw, marker-host binding, output decomposition, and abstraction growth — are unlikely to yield to a larger beam alone because ARC-AGI-2 was explicitly designed to be less brute-force-friendly and to stress multi-rule composition, multi-step composition, contextual rule application, and in-context symbol definition. The official ARC Prize 2025 report likewise identifies the “refinement loop” as the defining theme of progress on ARC-AGI-2, while the benchmark paper emphasizes that the new tasks are deliberately more compositional and less susceptible to naive search. citeturn50view0turn44view0

The official benchmark numbers reinforce that point. In the ARC-AGI-2 paper’s semi-private table, as of May 14, 2025, o3-medium is listed at 3.0%, ARChitects at 2.5%, and Icecuber at 1.6%, and the paper notes that scores below 5% are generally not considered meaningful because they may reflect noise-level heuristics or incidental fits. That collapse of both frontier reasoning models and strong ARC-AGI-1 symbolic systems is hard to explain with “just search harder”; it is much more consistent with a representational mismatch on the deeper compositional tasks. citeturn50view0

The best evidence favoring a **search-heavy symbolic loop** comes from execution-guided synthesis, not from test-time gradient adaptation. Ouellette’s controlled ARC-style compositional generalization study reports that execution-guided neural program synthesis outperforms test-time fine-tuning, and his earlier ARC work explicitly contrasts learning in grid space, program space, and transform space, suggesting that learned guidance is most useful when it narrows the symbolic search over transformations rather than trying to predict raw outputs directly. That fits your setup unusually well because you already have a symbolic engine and need help mainly with coverage, composition depth, and proposal quality. citeturn17academia0turn17academia1

My engineering verdict is therefore this: **put the next two weeks into a richer object-graph DSL, output-shape/decomposition as a first-class stage, routing/redraw primitives, a bounded CEGIS-style repair loop, and a small learned proposal/ranker trained on synthetic generator families.** Do not spend the next two weeks mostly on pixel repair or on per-task gradient adaptation. The former will miss the compositional center of the wall, and the latter is both compute-hungry and weakly aligned with the strongest out-of-distribution ARC evidence. DreamCoder and related work also suggest that recurring multi-step repairs should become new abstractions, not stay as one-off patches. citeturn0academia1turn34academia2turn31academia1turn48academia3

One caveat matters. A **numerical** design-only flip-to-exact rate and confidence interval cannot be obtained from literature alone; that requires your own design-split logs. What the literature can provide is the correct experimental order: first test shape/decomposition plus bounded repair on the current misses, then add relation-rich representation and library growth if the repair tranche is small. A sensible pre-registered decision rule would be: if shape-first repair closes roughly one-third of design near-misses across at least two operator families, continue the search/repair agenda; if not, move the bulk of effort to representation growth. That rule is not in the literature verbatim, but it is well aligned with ARC-AGI-2’s compositional design, with execution-guided synthesis results, and with DreamCoder-style abstraction learning. citeturn50view0turn17academia0turn0academia1

## Methods landscape

The strongest transferable result from the broader literature is not any single solver. It is the convergence of several lines on the same architecture pattern: **few-shot examples define the task; a symbolic program space defines what can be done; learned components narrow which parts of that program space are worth searching; and a verifier or exact execution decides what survives.** This pattern appears in DeepCoder, Neural-Guided Deductive Search, DreamCoder, ARC graph/planning solvers, and even the better LLM-for-program-synthesis papers when they are forced to execute and verify candidates rather than free-form speculate. citeturn21academia1turn21academia0turn0academia1turn30academia0turn40academia1turn37academia2

| Method family | Representative work | What transfers well to your notebook | Main limitation for your use case | Evidence |
| --- | --- | --- | --- | --- |
| ARC benchmark lessons | ARC-AGI-2; ARC Prize 2025 citeturn50view0turn44view0 | Treat ARC-AGI-2 as a compositional benchmark, not a pattern-matching benchmark; expect per-task refinement loops to matter. | Benchmark framing, not an implementation recipe. | Strong |
| Execution-guided symbolic synthesis | Ouellette 2025; Alford et al. 2021 citeturn17academia0turn34academia1 | Use execution and inverse semantics to guide search; reason over partial programs and search graphs, not only token sequences. | Existing demos are promising but still small compared with a full competition-grade notebook. | Medium |
| Library learning and abstraction growth | DreamCoder; Decompiling Amortized Knowledge citeturn0academia1turn34academia2 | Mine recurring subprograms/micro-repairs into typed macros; retrain the proposal model after library growth. | Needs enough solved tasks or synthetic families to induce reusable abstractions. | Strong |
| Neural-guided PBE search | DeepCoder; NGDS; PCCoder citeturn21academia1turn21academia0turn21academia2 | Predict properties, branch choices, or next-step families to speed symbolic search by an order of magnitude; prune dead intermediates aggressively. | Original domains are simpler than ARC grids and object graphs. | Strong |
| Object-graph ARC solvers | ARGA; GPAR; Ferré MDL; ARC ILP; abductive symbolic solver citeturn30academia0turn40academia1turn29academia1turn29academia0turn30academia2 | Lift pixels into objects/graphs/pointers before search; use constraints, state hashing, planning restrictions, or MDL to tame combinatorics. | Coverage still depends on whether the object abstraction exposes the needed relations. | Medium |
| Learned perceptual/object bias | LLMs + object-based reps; ViTARC; modality study; VSA solver citeturn39academia1turn30academia3turn33academia0turn10academia2 | Flat pixel or flat text encodings are not enough; object-aware representations help both symbolic and learned layers. | Most results are still benchmark- or architecture-specific. | Medium |
| Search-space compaction | Version-space algebras / tree automata; egg; SYNGAR citeturn26academia0turn28academia0turn51academia3 | Share equivalent partial programs, use abstract semantics early, and avoid repeatedly enumerating spurious families. | Requires some engineering sophistication in the DSL runtime. | Strong |
| LLM program proposals and reranking | KAAR/RSPC; IPARC LLM study; NeuralInvariantRanker citeturn32academia1turn32academia3turn37academia2 | Freeze prompts, sample multiple sketches, execute and verify them, and rerank with a learned verifier. | High leakage risk and brittle reasoning unless tightly sandboxed. | Medium to weak |
| Test-time neural adaptation | ARC Prize 2024/2025 reports; TTFT-TRM citeturn48academia0turn44view0turn31academia1 | Confirms that per-task refinement matters. | Too compute-heavy and packaging-heavy for the notebook path you described; weaker OOD evidence than execution-guided synthesis. | Medium |

Two synthesis points matter most. First, **object-centric representations repeatedly help**: ARGA, GPAR, Ferré’s MDL work, ILP-based ARC synthesis, abductive symbolic ARC, LLM object encodings, and ViTARC all improve only after the solver stops treating the grid as an undifferentiated bitmap. Second, **learned guidance works best when it predicts structure around the search, not when it replaces the symbolic core**. That is exactly the regime your notebook is in. citeturn30academia0turn40academia1turn29academia1turn29academia0turn30academia2turn39academia1turn30academia3turn21academia1turn21academia0

## Practical design patterns

The decisive design pattern is to search over **latent variables that humans would actually name**: output canvas, decomposition, object roles, route anchors, containment relations, ordering relations, symmetry group, and composition order. ARC-AGI-2 itself says the hard tasks increasingly require multi-rule composition, multi-step sequencing, contextual gating, and symbols whose meaning is defined inside the task. That means a DSL that can only do local pixel rules, object keep/remove/recolor, symmetry snippets, and post hoc repair will almost certainly underrepresent the target tasks. citeturn50view0

A minimal but expressive primitive inventory for the next notebook should look like this:

| Primitive family | Minimal operators worth adding now | Why this family is high priority |
| --- | --- | --- |
| **Views and parsers** | `cc_by_color`, `cc_ignore_color`, `rectangles`, `frames`, `holes`, `line_segments`, `panels`, `repetition_groups`, `background_islands` | You need multiple compatible objectizations because different ARC tasks define “object” differently. |
| **Role selectors** | `argmax/argmin(metric)`, `nth(order)`, `nearest`, `farthest`, `unique_by(feature)`, `match_by_relation(marker, hostset)` | Many misses are not “draw this thing” but “draw this thing *chosen by another thing*.” |
| **Relation graph** | `contains`, `inside`, `touches`, `overlaps`, `aligned`, `left_of/right_of`, `above/below`, `same_shape`, `same_bbox`, `same_hole_count`, `same_color`, `contact_dir`, `order_in_row/col` | Routing, bracketing, marker-host binding, and decomposition all need explicit relations. |
| **Canvas and decomposition** | `predict_canvas`, `crop_to(region)`, `new_canvas(h,w,bg)`, `tile_layout`, `panelize`, `compose_layers`, `compose_panels` | Wrong-shape failures will not be fixed by pixel repair if the canvas and panel structure are wrong. |
| **Routing and drawing** | `ray_until`, `shortest_path`, `orth_path`, `bracket`, `connect_anchors`, `avoid_mask`, `draw_path`, `draw_outline`, `extend_line` | On 30×30 grids, exact pathfinding is cheap once anchors are known; the hard part is choosing anchors and route style. |
| **Redraw and assembly** | `extract_shape`, `normalize`, `translate`, `rotate`, `mirror`, `scale_discrete`, `fill_holes`, `outline`, `stamp`, `pack(order, spacing)` | ARC-AGI-2 contains crop/rescale/place and iterative placement patterns that are composition-heavy. |
| **Serialization and ordering** | `sort_objects(key)`, `serialize_row`, `serialize_col`, `stack`, `interleave`, `group_then_pack` | Many redraw/output-shape tasks are really “new canvas + ordered assembly.” |
| **Bounded local repair** | `recolor_subset`, `close_gap`, `snap_endpoint`, `fill_interior`, `remove_artifact`, `extend_to_contact` | This covers the near-exact residual tranche without turning the solver into unconstrained pixel search. |
| **Library macros** | `macro(name, typed_subprogram)` induced from solved tasks | Recurring multi-step repairs should become abstractions, not stay bespoke. |

This table is a synthesis of the benchmark’s compositional design and of the object-centric/planning literature, not a verbatim list from any single paper. The main justification comes from ARC-AGI-2’s task design, ARGA/GPAR’s graph and pointer abstractions, Ferré’s joint object models, and object-based representation work showing that the solver needs explicit entities and relations before either symbolic or neural guidance becomes reliable. citeturn50view0turn30academia0turn40academia1turn29academia1turn39academia1turn30academia3

The search pattern I would use is **shape-first, decomposition-second, sketch-third, repair-last**. First infer the output canvas family and whether the output is a crop, panel composition, serialization, redraw on same canvas, or new-canvas assembly. Then choose one or more object views. Then let a learned proposer emit a small set of typed sketches such as “select marker → bind host → derive anchors → route → draw,” “partition → solve panels → compose,” or “select objects → normalize → pack on new canvas.” Then enumerate within the sketch using inverse semantics, abstract constraints, and equivalence sharing. Only after you have a shape-correct or decomposition-correct candidate should you invoke bounded residual repair. That order is strongly supported by bidirectional ARC search, neural-guided deductive search, version-space/tree-automata compression, and abstraction-refinement synthesis. citeturn34academia1turn21academia0turn26academia0turn51academia3turn28academia0

Because ARC-AGI-2 uses only grids up to 30×30, route execution itself does not need to be approximate. Shortest-path, orthogonal-path, or ray-extension operators can be exact and deterministic; the learned part should predict **which** anchors, blockers, or route style matter. This is the DeepCoder/NGDS lesson in ARC form: learn to choose the promising branch, but keep the underlying executor symbolic and exact. citeturn52view0turn21academia1turn21academia0

For learned proposal and ranking, the best target is not “predict the output grid.” It is **predict the search distribution**: output-shape family, object view, sketch family, role pairs, probable terminal operators, and a candidate-quality prior. Ouellette’s grid-space/program-space/transform-space taxonomy, together with DeepCoder, NGDS, and DreamCoder, all point toward this middle ground: learn the transform space around the symbolic engine rather than learn pixels or full programs end to end. citeturn17academia1turn21academia1turn21academia0turn0academia1turn34academia2

LLM or code-model proposals can still help, but only in a very fenced-in way. The safe pattern is: use a frozen offline model to emit a **typed DSL sketch or macro proposal**, never a raw answer; sample several; execute them; verify them against train pairs; rerank them with a verifier-aware ranker; and keep complete provenance of prompts, outputs, and admission decisions. The moment retrieval or hidden-score feedback enters that loop, you are in contamination territory. ARC Prize 2025 explicitly warns about knowledge-dependent contamination, and the search-time contamination paper shows how online retrieval can leak benchmark answers even when the final model appears to be “reasoning.” citeturn32academia1turn32academia3turn37academia2turn49academia0turn49academia1

## Recommended solver architecture

The architecture that best matches your miss profile is a **typed object-graph synthesis system with an anytime search loop and a tiny learned prior**. It should be more structured than a flat operator library, but much smaller and more inspectable than a full unconstrained code generator. The strong enabling idea here is to represent candidate programs as a **typed DAG with explicit bindings and overlays**, not only as a tree of pixel transforms. Typed DAGs make it much easier to share common subexpressions, reuse object selections, and prune dead intermediate values, which is exactly what e-graph, tree-automata, and long-program synthesis work say you should do once programs become compositional. citeturn26academia0turn28academia0turn21academia2turn51academia3

A concrete module breakdown is below.

| Module | Recommendation | Why |
| --- | --- | --- |
| **Parser bank** | Build multiple deterministic views of each grid: color-connected objects, monochrome objects, rectangles/frames, holes, line segments, panels, repetition clusters. | No single segmentation is correct for all ARC tasks. |
| **Object-graph IR** | Store nodes for grids, regions, objects, markers, panels, routes, and overlays; edges for containment, contact, alignment, ordering, and host-marker relations. | Most of your hard misses are relational, not purely transformational. |
| **Shape/decomposition predictor** | A tiny learned classifier over task features and object-graph summaries predicting `same_canvas`, `crop`, `new_canvas_pack`, `panel_compose`, `tile`, `serialize`, `other`. | Wrong-shape errors should be blocked before deep enumeration. |
| **Sketch proposer** | A small GNN or transformer over the object graph, trained to emit top-k sketch families and likely primitive bundles. | This is the cheapest place to put learning. |
| **Typed enumerator** | Enumerate inside sketches with strict type checking, abstract guards, inverse constraints, state hashing, and equivalence merging. | You want deeper composition without search explosion. |
| **Route/redraw executor** | Keep routing exact: BFS/A*, orthogonal routing, rays, bracket generators, redraw/stamp/pack on new canvases. | Exact execution is cheap on these small grids. |
| **Repair loop** | Only after shape/decomposition is correct, run bounded local rewrites derived from train residual structure. | Prevents repair from becoming a second unconstrained solver. |
| **Verifier/ranker** | Hard gates for train exactness and leave-one-train-out; soft scores for MDL, stability, proposal prior, and synthetic invariance; mandatory diversity for top-2. | Your own context suggests ranking is not the main bottleneck, so keep this simple and robust. |
| **Library induction** | Periodically mine frequent typed subgraphs/subprograms from solved tasks and add them as macros after cross-task validation. | This is the clean path to abstraction growth. |

The type system can stay minimal. I would use `Grid`, `CanvasSpec`, `Region`, `Obj`, `ObjSet`, `Mask`, `Point`, `PointSet`, `Route`, `Color`, `Axis`, `Dir`, `Int`, and `Bool`. Two design choices matter. First, separate **selection** types from **drawing** types, so that search can narrow object roles before committing to paint operations. Second, make drawing pure by emitting overlays and then composing them, instead of mutating the grid in-place during enumeration; this makes equivalence sharing and verification much easier. Those are engineering recommendations, but they are strongly consonant with planning-style ARC solvers, DreamCoder’s typed compositionality, and e-graph-style sharing. citeturn40academia1turn0academia1turn28academia0

The search loop should be anytime and budget-aware:

1. Parse all views and build the relation graph.
2. Predict output shape/decomposition family.
3. Ask the learned proposer for the top sketch families.
4. Enumerate typed programs inside each sketch with inverse constraints and abstract pruning.
5. Stop early on exact train fits that also pass leave-one-train-out.
6. If the candidate is shape-correct but not exact, invoke bounded repair.
7. Rank at the **task level** and return two diverse program-level predictions.

That last detail matters because ARC-AGI-2 tasks can have multiple test pairs; the benchmark paper reports that while 68% of tested tasks had one test pair, the rest had two, three, or four. Your solver should therefore rank complete **task-level latent programs**, not independent per-grid guesses, and your top-2 should be diverse at the family level rather than two tiny perturbations of the same candidate. citeturn50view0

For packaging, keep the symbolic core pure Python and NumPy, with optional PyTorch only for the proposal/ranker model. Avoid exotic solver dependencies that are difficult to vendor into a competition notebook. Heavy TTFT-style pipelines are a bad fit here: the TTFT-TRM paper reports a 48-hour, 4×H100 pretraining run just to reach about 10% public performance before efficient post-training on competition tasks, and it explicitly contrasts that with competition compute limits. That is exactly the opposite of what a robust symbolic ARC notebook wants. citeturn31academia1

## Synthetic data plan

The synthetic data should not teach “what ARC public tasks look like.” It should teach **which latent relational/compositional choices matter**. ARC-TGI is useful here as a proof that compact task-family generators can produce many ARC-style variants while preserving a latent rule, and ConceptARC is useful as a reminder that concept-level generalization must be tested across families, not just within one surface form. H-ARC adds another useful ingredient: large numbers of human attempts and action traces on the public ARC set. citeturn38academia2turn41academia0turn40academia3

The generator families I would build first are the ones your solver currently lacks:

- **Routing families**: connect marker to host, connect ordered objects, draw brackets, draw orthogonal paths around blockers, and extend rays until contact.
- **Redraw families**: extract object parts, normalize, rescale, and stamp into a new canvas or into holes/frames.
- **Marker-host binding families**: choose targets by color cue, hole count, enclosure, nearest marker, or contextual role.
- **Panel and decomposition families**: crop framed subregions, solve per-panel subtasks, serialize panel outputs, and build new canvases from object orderings.
- **Symmetry-plus-repair families**: near-complete symmetries with one or two missing edits, interior-vs-outline ambiguity, or endpoint snapping.
- **Abstraction-growth families**: repeated microprograms composed into a larger rule, so that macros become statistically inducible.

Each generator should vary colors, sizes, numbers of distractors, object counts, panel layouts, and example counts, but the most important variation is **hypothesis disambiguation across train examples**. If a latent rule can be confused with a simpler shortcut, the examples must be sampled so that the shortcut fails. ARC-TGI explicitly argues for task-level constraints so that demonstrations collectively expose the needed variations; that is exactly the design discipline you want. citeturn38academia2

The learned targets should also be structural, not pixel-level. Train the proposal model to predict output-shape family, decomposition family, object view, sketch family, role bindings, and next operator family. Train the ranker to score candidate programs or sketches against the task features. Optionally use H-ARC traces as weak supervision for object salience, order-of-attention, or edit locality, but keep that auxiliary rather than decisive. citeturn40academia3turn21academia1turn21academia0turn37academia2

A crucial leak-control note: ARC-TGI is promising, but it explicitly includes generators covering ARC-Mini, ARC-AGI-1 tasks, and some ARC-AGI-2 tasks. That makes it a useful design reference and a possible source of **held-out-family** synthetic benchmarks, but it should not be naively dumped into the training pool for competition-facing learned components. Likewise, object-based encodings and LLM-generated reasoning chains are useful for development, but public-task-specific generators and traces should be separated from any competition-facing evaluation claims by family-level holdouts and frozen prompts. citeturn38academia2turn49academia1turn49academia0

## Evaluation and admission protocol

The evaluation discipline should be more like adaptive-science protocol design than ordinary model development. Generic Holdout and reusable holdout literature both exist to prevent exactly the kind of benchmark overfitting that ARC’s organizers worry about, and the ARC-AGI-2 paper explicitly documents how repeated leaderboard reuse can leak information about hidden tasks over time. For your notebook, that means one frozen calibration exposure per pre-specified family, limited information returned from the frozen set, and all threshold tuning done on the design split. citeturn25academia1turn25academia2turn52view0

The right internal taxonomy is not merely “solved” versus “unsolved.” It is at least these four buckets: **wrong shape**, **right shape with small residual**, **right shape with large residual**, and **wrong decomposition or role binding**. The reason to invest in this taxonomy is that it directly tells you whether to work on shape/decomposition, relational representation, or bounded repair. ARC-AGI-2’s own design examples support that decomposition: crop/rescale/place tasks, sequential placement tasks, contextual gating, and in-context symbol definition fail for different reasons, even if they all end up “wrong” at the pixel level. citeturn50view0

I would use the following admission protocol for new families:

1. **Design split only** for family design, thresholds, and sketch vocabulary.
2. **Exact train fit** as a hard gate.
3. **Leave-one-train-out exactness** as a second hard gate wherever the task has enough examples.
4. **Synthetic invariance** as a soft score unless you have overwhelming evidence that it helps that family. Given your own internal observations, it should not be a universal hard rejector. fileciteturn0file0
5. **Cross-task promotion** only if a new primitive, repair family, or macro helps at least two distinct design tasks or one design task plus one held-out synthetic family.
6. **One frozen evaluation per family**, logged and never revisited for tuning.
7. **Family stop condition** after a fixed number of design-side variants fail to add new coverage.

The main reported metrics should be task-exact@1, task-exact@2, design flip-to-exact rate by family, average runtime per task, and miss-bucket transitions. Reporting only exact accuracy will hide whether the solver is moving from wrong-shape to right-shape-small-residual, which is a crucial intermediate win for your current agenda. ConceptARC is also a good supplementary evaluation because it directly tests whether the solver has captured the intended abstraction or merely fit a surface-level pattern. citeturn41academia0turn25academia1turn25academia2

## Build plan and first experiments

The literature suggests a clear order of operations: build the object-graph and shape/decomposition stages first, then learned proposal/ranking, then library growth. That order is supported by the official ARC-AGI-2 task design, by ARGA/GPAR/Ferré-style object-centric search, and by the “refinement loop” lessons from ARC Prize. citeturn50view0turn30academia0turn40academia1turn29academia1turn44view0

### Forty-eight-hour prototype

| Time window | Deliverable | Success criterion |
| --- | --- | --- |
| **Hours 0–12** | Multi-view parser bank plus relation graph IR | Can parse current miss tasks into objects, frames, holes, lines, and panels without manual task code |
| **Hours 12–24** | Output shape/decomposition classifier and executor scaffolding | Correctly classifies same-canvas vs crop vs new-canvas assembly on a hand-labeled dev slice |
| **Hours 24–36** | Route/redraw primitives with exact executors | Can generate rays, orthogonal paths, brackets, stamps, and pack operations symbolically |
| **Hours 36–48** | Typed sketch enumerator plus bounded repair loop | Produces exact train fits for at least a few current design-side near misses and logs miss bucket transitions |

The point of the 48-hour prototype is not leaderboard movement. It is to answer one question: after you add shape/decomposition and route/redraw/search scaffolding, do your current “almost there” tasks become exact-train-correct under a generic family rather than a bespoke fix. If yes, you have found a real search/repair tranche. If no, you can stop romanticizing repair and move directly to larger representation growth. citeturn17academia0turn0academia1

### Two-week build plan

| Window | Main workstream | Deliverables |
| --- | --- | --- |
| **Days 1–3** | Representation | Parser bank, relation graph, canonical hashing, overlay-based pure executor |
| **Days 4–5** | Shape and decomposition | Shape family predictor, panel/crop/new-canvas operators, task-level candidate assembly |
| **Days 6–7** | Route/redraw search | Sketch vocabulary, inverse constraints, route/redraw primitives, exact executors |
| **Days 8–9** | Synthetic generators | First generator families for routing, redraw, marker-host, and decomposition |
| **Days 10–11** | Learned proposal/ranker | Tiny GNN/transformer proposer and contrastive candidate ranker |
| **Days 12–13** | Library induction | Frequent subprogram mining, macro scoring by compression and reuse |
| **Day 14** | Frozen packaging and eval | Deterministic notebook module layout, hard runtime caps, family-by-family design report |

### First five experiments

The first five experiments I would implement are these, in this exact order.

**Shape-first flip experiment.** Add only output-shape/decomposition prediction plus bounded repair, then measure design-side flip-to-exact rate by miss bucket. This is the fastest falsifier for the search-versus-representation question. If very little flips, stop over-investing in repair. citeturn17academia0turn25academia1

**Routing and bracket primitives.** Add anchor selection, ray extension, orthogonal routing, and bracket drawing, then test on tasks whose best current candidates already identify the correct objects but fail to draw the right connective geometry. Because route execution is exact and cheap on small grids, this experiment isolates whether the missing piece is representational rather than computational. citeturn52view0turn30academia0turn40academia1

**Object-role binding over relation graphs.** Build `marker -> host -> action` sketches and compare them against flat object selection baselines. This directly targets contextual rule application and in-context symbol definition, which the ARC-AGI-2 paper identifies as major sources of difficulty. citeturn50view0

**Learned transform-space prior.** Train a small proposal model to predict shape family, sketch family, and role bindings from synthetic graphs. Compare against blind enumeration at the same runtime cap. The expectation from DeepCoder, NGDS, and Ouellette is that this should buy much better search focus than raw output prediction would. citeturn21academia1turn21academia0turn17academia1

**Macro induction from solved subtasks.** Mine frequent typed subprograms from exact design solves and add only those that recur across families. Re-run the search on hard redraw/decomposition tasks. This is the first real test of whether DreamCoder-style abstraction growth is likely to pay off in your notebook rather than in an idealized research setting. citeturn0academia1turn34academia2turn34academia1

## Risks and prioritized bibliography

The main risks are all manageable, but only if you make them first-class design objects.

**Public-eval overfitting.** ARC-AGI-2 exists partly because repeated exposure to hidden tasks on ARC-AGI-1 created leakage and adaptation pressure. Family-level pre-registration and Generic Holdout-style limited exposure are not optional here. citeturn52view0turn25academia1turn25academia2

**Train-exact but nongeneral programs.** Exact train fit is necessary but not sufficient. Leave-one-train-out, family-level reuse, and held-out synthetic family validation are what separate reusable abstractions from memorized tricks. DreamCoder is useful here because it makes reuse measurable as compression and transfer, not just as local accuracy. citeturn0academia1turn34academia2

**Task-ID or template leakage.** ARC Prize 2025 warns about knowledge-bound contamination, and search-time contamination work shows that online retrieval can surface hidden answers. Keep evaluation offline, freeze any LLM prompts or model weights, and never let a proposal component see task identifiers, leaderboard feedback, or web sources. citeturn49academia1turn49academia0

**Runtime blowups.** Richer DSLs are dangerous without shape-first decomposition, sketch priors, abstract pruning, and equivalence sharing. The search-space compaction literature is directly relevant here: tree automata, e-graphs, and abstraction refinement are not academic extras; they are how you keep composition from exploding. citeturn26academia0turn28academia0turn51academia3

**Neural model dependency and packaging drag.** TTFT-style adaptation is both compute-heavy and difficult to package robustly inside a notebook. A tiny proposal/ranker model is much less brittle and better aligned with the strongest program-synthesis evidence. citeturn31academia1turn17academia0turn21academia0turn21academia1

### Priority reading

**Read first**

- **ARC-AGI-2: A New Challenge for Frontier AI Reasoning Systems.** The ground truth on task format, compositional design, leakage concerns, and why ARC-AGI-2 is qualitatively harder than ARC-AGI-1. citeturn42view0turn50view0turn52view0
- **ARC Prize 2025: Technical Report.** Best high-level summary of what actually moved the leaderboard in 2025 and why refinement loops matter. citeturn44view0
- **Out-of-Distribution Generalization in the ARC-AGI Domain: Comparing Execution-Guided Neural Program Synthesis and Test-Time Fine-Tuning.** The clearest direct evidence that execution-guided synthesis is a better bet than TTFT for compositional ARC-style generalization. citeturn17academia0
- **DreamCoder** and **Bayesian Program Learning by Decompiling Amortized Knowledge.** The strongest abstraction-growth template for turning recurring repairs into reusable macros. citeturn0academia1turn34academia2
- **Graphs, Constraints, and Search for ARC** and **Generalized Planning for ARC.** The most directly useful object-graph and pointer-style search papers for your setting. citeturn30academia0turn40academia1
- **Tackling ARC with Object-centric Models and the MDL Principle.** Especially useful for thinking about joint input/output descriptions and search bias toward simpler, human-like models. citeturn29academia1

**Read next**

- **DeepCoder** and **Neural-Guided Deductive Search.** Best references for “learn properties, then search symbolically.” citeturn21academia1turn21academia0
- **Neural-guided, Bidirectional Program Search for Abstraction and Reasoning.** Important for inverse semantics and sketch-based backward reasoning in ARC. citeturn34academia1
- **Version Space Algebras are Acyclic Tree Automata**, **egg**, and **Program Synthesis using Abstraction Refinement.** Read these if your enumerator starts exploding; they are the search-engineering backbone. citeturn26academia0turn28academia0turn51academia3
- **LLMs and the Abstraction and Reasoning Corpus: Successes, Failures, and the Importance of Object-based Representations** and **ViTARC**. Very useful for designing the proposal model input representation, even if you do not want an end-to-end neural solver. citeturn39academia1turn30academia3
- **ConceptARC** and **H-ARC**. Good for concept-level validation and human-trace-informed diagnostics. citeturn41academia0turn48academia2

**Promising but use cautiously**

- **ARC-TGI.** Excellent idea source for generator-style evaluation, but potentially risky if used naively for training competition-facing learned models. citeturn38academia2
- **From Reasoning to Generalization: Knowledge-Augmented LLMs for ARC Benchmark** and **Structured Program Synthesis using LLMs: Results and Insights from the IPARC Challenge.** Useful for proposal and reranking ideas, but the evidence is more fragile and leak-sensitive than the symbolic-search literature. citeturn32academia1turn32academia3
- **Vector Symbolic Algebras for ARC.** Promising object-centric neurosymbolic direction, but still early and not yet a settled engineering bet for ARC-AGI-2 notebooks. citeturn10academia2
- **Test-time Adaptation of Tiny Recursive Models.** Worth reading mainly to understand what *not* to make central in this notebook architecture. citeturn31academia1