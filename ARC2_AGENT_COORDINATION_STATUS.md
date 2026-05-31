# ARC-AGI-2 Agent Coordination Status

Generated: 2026-05-30 19:06 CDT

## Active Collaboration Split

Claude lane:

- Solver/eval mechanics:
  - strict synthetic gate fix (`unavailable` is not `failed`)
  - cross-task firing registry
  - corrected strict design/calibration runs
  - commit/push lane if/when ready

Codex lane:

- Read-only evidence analysis:
  - operator reliability harness
  - provenance split
  - corrected strict before/after summary
  - next research prompt / bottleneck queue

This avoids both agents editing the same hot files at the same time.

## Current Score Matrix

| mode | split | tasks | score | pairs | pair score |
| --- | --- | ---: | ---: | ---: | ---: |
| non-strict | design | 56/80 | 0.7000 | 73/108 | 0.6759 |
| non-strict | calibration | 28/40 | 0.7000 | 38/59 | 0.6441 |
| old strict | design | 38/80 | 0.4750 | 50/108 | 0.4630 |
| old strict | calibration | 23/40 | 0.5750 | 32/59 | 0.5424 |
| corrected strict | design | 49/80 | 0.6125 | 66/108 | 0.6111 |
| corrected strict | calibration | 24/40 | 0.6000 | 33/59 | 0.5593 |
| strict + general-only fixed gate | design | 31/80 | 0.3875 | 42/108 | 0.3889 |
| strict + general-only fixed gate | calibration | 24/40 | 0.6000 | 33/59 | 0.5593 |

## What Changed

The corrected strict gate recovered:

- Design: +11 tasks, +16 pairs.
- Calibration: +1 task, +1 pair.

The remaining strict/non-strict gap is now mostly a deliberate audit-mode loss, not a public regression.

The optional general-only fixed gate shows the single-task fixed layer is design-heavy:

- Design drops from corrected strict `49/80` to general-only `31/80`.
- Calibration stays at `24/40`.

Interpretation: hard-requiring cross-task fixed-operator firing is too expensive for the design score, but it does not hurt the frozen calibration score in this run. Use it as a research/control mode, not as Kaggle-facing policy.

## Reliability/Provenance Artifacts

- `analyze_arc2_operator_reliability.py`
- `ARC2_OPERATOR_RELIABILITY_REPORT.md`
- `ARC2_OPERATOR_RELIABILITY_FIXED_REPORT.md`
- `mine_arc2_coverage_bottlenecks.py`
- `ARC2_COVERAGE_BOTTLENECKS.md`
- `audit_arc2_scrubbed_solvers.py`
- `ARC2_SCRUBBED_SOLVER_AUDIT.md`
- `tmp/arc2_reliability/operator_reliability.png`
- `tmp/arc2_reliability_fixed/operator_reliability.png`
- `tmp/arc2_reliability/operator_reliability_summary.json`
- `tmp/arc2_reliability_fixed/operator_reliability_summary.json`
- `tmp/arc2_coverage_bottlenecks.json`
- `tmp/arc2_scrubbed_solver_audit.json`

Corrected strict provenance:

- Strict design solved pairs:
  - General pipeline: 40/66, `60.6%`
  - Operator library: 26/66, `39.4%`
  - TTA-wrapped: 51/66, `77.3%`
- Strict calibration solved pairs:
  - General pipeline: 26/33, `78.8%`
  - Operator library: 7/33, `21.2%`
  - TTA-wrapped: 22/33, `66.7%`

H1 evidence reliability recheck:

- `fixed / failed`: design `8/8`, calibration `8/8`
- `fixed / passed`: design `8/8`, calibration `3/3`
- `fixed / unavailable`: design `17/17`, calibration `1/1`
- `learned / loo+ syn+`: design `1/1`, calibration `3/3`
- Weighted design-to-frozen calibration error over observed train-exact operator hits: `0.000`

Caveat: H1 is all-positive after filtering to train-exact operator occurrences with shadow totals, so it validates the evidence table format but is not yet a hard negative-control test.

Corrected strict bottlenecks:

- Design misses: 31 tasks.
- Calibration misses: 16 tasks.
- Exact-in-top-k-not-chosen: 1 design, 0 calibration.
- Better finite top-k candidate exists but was not selected: 19 design, 9 calibration.
- Wrong-shape selected while a finite top-k candidate exists: 2 design, 1 calibration.
- No finite candidate found: 5 design, 1 calibration.

Conclusion: plain ranking is not the next primary bottleneck; candidate coverage, shape-correct proposal generation, and residual repair layers around already-close top-k candidates are.

Coverage bottleneck clusters from `ARC2_COVERAGE_BOTTLENECKS.md`:

- `crop_largest_object_with_border_cleanup`: 8 tasks.
- `color_role_symmetry_recovery`: 6 tasks.
- `sparse_line_endpoint_bridge`: 6 tasks.
- `border_or_frame_residual_repair`: 6 tasks.
- `ttt_sparse_patch_repair`: 5 tasks.
- `hub_tail_contact_color_role_repair`: 5 tasks.
- `new_output_shape_operator_pack`: 5 tasks.

Scrubbed solver audit:

- Audited 71 `solve_<taskid>` functions in `dsl.py`.
- `generic_candidate`: 36.
- `public_exact_not_train_exact`: 31.
- `train_exact_but_suspicious`: 4.
- Important caution: `b6f77b65`, `4c7dc4dd`, `5dbc8537`, and `edb79dae` all solve public tests without being train-exact without replay, so they should be mined for abstract rules but not promoted directly.
- `dd6b8c4b` is train/test exact without replay, but the implementation is dimension/coordinate-heavy; treat it as an abstraction target, not a certified hidden operator as-is.

Exact-train attempt filter patch:

- Change: in hidden-facing mode, when exact-train candidates exist, `arc2_candidate_solver.solve_task` now spends attempts only on exact-train candidates (`ARC_EXACT_TRAIN_ATTEMPTS_ONLY=1` by default in hidden mode).
- Motivation: `0934a4d8` had an exact `recover_point_symmetric_region` candidate in top-k, but both live attempts were consumed by non-exact/wrong-shape candidates.
- Frozen design after patch: `50/80`, pair `67/108`.
- Frozen calibration after patch: `24/40`, pair `33/59`.
- Public regression guard after patch: `120/120`, pair `167/167`, guard `10/10`.
- Packaged Kaggle modules compile after patch.

Supply-gap relocation operator patch:

- Change: added learned operator `object_motion:supply_color_to_lowest_row_gaps`.
- Evidence on target family: train-exact, leave-one-out stable, synthetic recolor self-consistent.
- Frozen design after patch: `50/80`, pair `67/108`.
- Frozen calibration after patch: `25/40`, pair `34/59`.
- Public regression guard after patch: `120/120`, pair `167/167`, guard `10/10`.
- Interpretation: this is the first clean post-audit frozen calibration gain from a generalized learned operator, not a task-id/public-signature replay.

Strict synthetic-gate refinement:

- Change: narrowed synthetic invariance applicability instead of weakening strict admission.
- Boundary/seed-frame operators no longer receive padding-translation tests, because added padding changes the reference frame rather than translating the same task.
- `sparse_panel_noise:shape_tip_beams` is marked color-role-sensitive, so color permutation is not treated as an applicable invariant.
- Newly unblocked strict operators:
  - `object_contact_alignment:slide_marked_components_to_boundary_axes`
  - `seed_ray_chain:repaint_reached_objects`
  - `sparse_panel_noise:shape_tip_beams`
- Frozen design after refinement: `51/80`, pair `68/108`.
- Frozen calibration after refinement: `28/40`, pair `38/59`.
- Public regression guard after refinement: `120/120`, pair `167/167`, guard `10/10`.
- Packaged Kaggle modules compile after refinement.

Route-glyph ladder transfer operator patch:

- Change: added learned operator `route_glyph_transfer:ladder_switch_glyphs`.
- Target abstraction: visible colored 3x3 labels/glyphs sit on endpoints of a scaffold/ladder network; non-full scaffold bars induce lane swaps, visible endpoint glyphs constrain the permutation, then sources render as plus glyphs and destinations render as X glyphs.
- Safety properties:
  - No task ID usage.
  - Learns background, scaffold colors, and token colors from train diffs.
  - Certified only after exact train, leave-one-train-out, jackknife stability, and synthetic ladder self-consistency.
- Direct evidence on `a47bf94d`: train-exact, LOO true, jackknife true, synthetic self-consistency true, local public shadow exact.
- Frozen design after patch: `51/80`, pair `68/108` (unchanged).
- Frozen calibration after patch: `29/40`, pair `39/59`.
- Public regression guard after patch: `120/120`, pair `167/167`, guard `10/10`.
- Packaged Kaggle modules compile after patch.

Claude standalone lane update:

- Claude added design-only CEGIS/coverage audit artifacts in commits `52df07b9` and `34282fe1`.
- Their main result matches the current Codex lane: per-cell residual repair does not flip the genuine misses under LOO; remaining gains are mostly representation/role/operator parameterization, plus shape prediction as a filter.
- Codex should avoid duplicating pixel-local repair wrappers for now and focus on structured object/role operators plus output-shape proposal filters.

Hidden shape-profile ranking filter:

- Change: added hidden-facing `ARC_ENABLE_SHAPE_PROFILE_FILTER` ranking signal.
- It predicts test output shape from train-only I/O shape relations: same shape, constant output shape, integer scale, or foreground-bbox crop.
- It is ranking-only, not a solver, and is enabled by default only in hidden-facing mode.
- Frozen design after filter: `51/80`, pair `68/108` (unchanged).
- Frozen calibration after filter: `29/40`, pair `39/59` (unchanged).
- Public regression guard after filter: `120/120`, pair `167/167`, guard `10/10`.
- Packaged Kaggle modules compile after filter.

Strict synthetic applicability refinement, round 2:

- Change: narrowed the strict synthetic invariance checks for operators whose semantics are color-role-sensitive or tied to an absolute scaffold/reference frame.
- This does not bypass exact train, LOO, jackknife, or synthetic self-consistency; it prevents non-applicable synthetic perturbations from quarantining otherwise-general fixed operators.
- Operators unblocked in strict hidden-facing eval:
  - `symmetry_context:diagonal_zero_run_completion`
  - `marker_triplet_antennas:row_end_stencils`
  - `line_network:diagonal_marker_crossings`
  - `marker_scaffold_rays:two_cell_strip_propagation`
  - `mask_scale:fill_expanded_holes_with_objects`
  - `cross_spiral:expand_plus_to_rectangular_spiral`
- This reconciles Claude's live-factory coverage audit: the seven "already solved" design tasks now re-enter strict hidden-facing mode.
- Frozen design after refinement: `57/80`, pair `74/108`.
- Frozen calibration after refinement: `29/40`, pair `39/59` (unchanged).
- Public regression guard after refinement: `120/120`, pair `167/167`, guard `10/10`.
- Packaged Kaggle modules compile after refinement.

Claude latest standalone lane update:

- Claude's object-role and symmetry/periodic prototypes flipped `0/23` genuine design misses under LOO.
- Negative result: the remaining misses are not well explained by pixel-neighborhood repair, simple keep/remove object role selection, pure recolor, subgrid crop, or generic periodic/symmetry completion.
- Their recommended next prototype is `relational_route_between_markers` for structure-generation families around `142ca369`, `195c6913`, `35ab12c3`, and `4a21e3da`.
- Codex should avoid duplicating that lane and keep focusing on verified admission/ranking/package safety unless Claude hands off a promising route prototype.

Claude close-out update:

- Claude also tested a shape-change summarization angle and did not find a generic flip.
- They added `arc2_nearmiss_frontier.py` and `tmp/claude_nearmiss_frontier.json`.
- Tightest normalized training-residual frontier:
  - `3dc255db`: `ttt:pixel_perceptron`, rho `0.031`
  - `dd6b8c4b`: `ttt:pixel_perceptron`, rho `0.041`
  - `16b78196`: `object_remove:interior_objects`, rho `0.048`
  - `88bcf3b4`: `dsl:isolate_unique_color_object`, rho `0.048`
- Claude's residual-localization warning: these are numerically close but structurally heterogeneous, so they are not obvious one-parameter tweaks.
- Codex rich strict diagnostics (`tmp/pp_design_strict_gate_refined_rich.json`) agree: the remaining `23` design misses have no exact-train candidate and no quarantined operator that is close to promotion.

## Current Verification

- `python3 -m py_compile arc2_candidate_solver.py run_pseudo_private_eval.py mine_arc2_nearmiss_clusters.py test_speculative_admission.py analyze_arc2_operator_reliability.py`
- `python3 run_submission_eval.py`
  - `120/120`
  - `167/167`
  - guard `10/10`
- `python3 prepare_arc2_kaggle_modules.py --out kaggle_modules`
- `python3 -m py_compile kaggle_modules/*.py`
- `python3 run_pseudo_private_eval.py --split calibration --strict-admission --diagnostics tmp/pp_cal_strict_ladder_patch.json --no-candidate-report`
- `python3 run_pseudo_private_eval.py --split design --strict-admission --diagnostics tmp/pp_design_strict_ladder_patch.json --no-candidate-report`
- `python3 run_pseudo_private_eval.py --split calibration --strict-admission --diagnostics tmp/pp_cal_strict_shape_filter.json --no-candidate-report`
- `python3 run_pseudo_private_eval.py --split design --strict-admission --diagnostics tmp/pp_design_strict_shape_filter.json --no-candidate-report`
- `python3 run_pseudo_private_eval.py --split calibration --strict-admission --diagnostics tmp/pp_cal_strict_gate_refined.json --no-candidate-report`
- `python3 run_pseudo_private_eval.py --split design --strict-admission --diagnostics tmp/pp_design_strict_gate_refined.json --no-candidate-report`
- `python3 run_pseudo_private_eval.py --split design --strict-admission --diagnostics tmp/pp_design_strict_gate_refined_rich.json`
- `python3 -m py_compile arc2_candidate_solver.py run_pseudo_private_eval.py run_submission_eval.py`

## Next Bottlenecks

Top corrected strict calibration near misses:

- `28a6681f`: top-k diff 6 from `dsl:frame_minority_cells`
- `b6f77b65`: top-k diff 8 / 35 from `dsl:connect_cells_via_key_sequence` or `alignment:connect_same_color`
- `4c7dc4dd`: wrong-shape actual, top-k finite 20 / 32
- `62593bfd`: top-k diff 25 / 43 from `dsl:gravity_objects_up`
- `581f7754`: top-k diff 39 / 49 from `mirror_h`
- `8b7bacbf`: top-k diff 39 / 48 from `dsl:connect_cells_via_key_sequence`

Recommended next implementation lane:

1. Treat the current `23` design misses as representation-limited until a prototype proves otherwise.
2. Prefer per-task relational program synthesis / abstraction-growth experiments over broad repair wrappers.
3. Use Claude's frontier only as triage; do not promote `ttt` or object-removal residual patches without LOO/synthetic invariance.
4. Calibration-side near misses (`28a6681f`, `b6f77b65`, `4c7dc4dd`, `62593bfd`, `581f7754`, `8b7bacbf`) remain better candidates for honest next score movement because they are outside the design-mined wall.
5. If any new prototype gets train-exact/LOO flips, run strict admission, frozen calibration, public guard, and package compile before merging into live attempts.

Scratch finding on `dd6b8c4b`:

- There is a real sub-rule: central 3x3 cells are filled with marker color in row-major order, and the number of filled cells equals the number of consumed outer markers.
- The missing abstraction is input-only selection of consumed markers.
- Simple structural features did not explain the train set consistently: 4-neighbor adjacency to path color, marker components, component sizes, and coarse 3x3 position bins all fail at least one train example.
- Do not promote a `dd6b8c4b` wrapper unless the consumed-marker selector becomes LOO-stable without coordinate signatures.

Scratch finding on `3dc255db`:

- Diff structure is consistent at the high level: embedded marker fragments are removed and a cleaner exterior marker segment is redrawn.
- The target anchor changes by object/color role: some markers move to the opposite side of the same structure, some collapse a long noisy internal path to a short exterior ray, and the test case pairs multiple marker/base structures.
- This should be treated as a relational pairing/search problem over marker fragments and host structures, not as a fixed endpoint bridge or local denoise rule.

Scratch finding on `35ab12c3`:

- The closest live family (`alignment:connect_diagonal_same_color`) is directionally right but incomplete.
- Outputs are multi-rule: one structure stretches/stamps a multi-color local motif between anchors, while another color family draws a separate routed/diagonal structure.
- A useful synthesis representation needs "copy motif along a path/axis" plus ordinary line routing; a pure same-color connector will remain a near miss.

Scratch finding on `4a21e3da`:

- The task has a compact role vocabulary: background `1`, object color `7`, and marker color `2`.
- The output removes or thins the original `7` object, threads a marker-colored column through the scene, and recreates a transformed/relocated `7` object relative to the marker.
- This is a promising relational-synthesis target: learn object orientation and marker-relative placement, then render the object with a marker spine. It should not be approximated as a color swap.

Standalone prompt for next agent:

Build a design-only relational program synthesis prototype, not another fixed wrapper. Inputs are the 23 current design misses, with first focus on `4a21e3da`, `3dc255db`, `dd6b8c4b`, `35ab12c3`, `142ca369`, and `195c6913`. Do not touch `arc2_candidate_solver.py` until a prototype flips at least one task under train exactness plus leave-one-train-out. Represent grids as host objects, marker fragments, paths/rays, frames, central panels, and marker-relative object relocation. Search small programs made of: select host, select marker fragment, pair marker to host by relation, erase fragment, render segment/ray/motif/row-major fill, relocate object relative to marker, and optionally thread a marker spine through the rendered object. Report exact train, LOO, synthetic invariance, and design-test readout separately. Do not use task IDs, coordinate signatures, public templates, or frozen calibration for synthesis.

Codex note to Claude on `arc2_relational_micro_synth.py`:

- The first oracle-selector ablation is useful, but `dd6b8c4b` is currently likely misclassified as `RENDER`.
- Reason: `render_fill_panel_by_count` erases all marker-colored cells outside the panel, while the true task preserves non-consumed outer `9` markers. Giving the renderer only the oracle count is not enough to test render expressibility.
- Better oracle ablation: derive the oracle consumed-marker set from train output (`input==marker` and `output==background` outside the panel), erase only those cells, then fill the panel row-major with `len(consumed)`.
- If that oracle renderer becomes train-exact, the failure locus is `SELECTOR`, as suspected: the open problem is learning the consumed-marker selector from input-only features.
- Then test selector vocabularies against the oracle-consumed labels: marker component size, border/side bins, proximity to `6` path cells, visibility/ray to panel, symmetry partner, inside/outside path loops, and component endpoints. Keep this standalone until train-exact + LOO.

Codex sentinel verification, 2026-05-30 21:29 CDT:

- Added standalone verifier `arc2_codex_relational_verifier.py`; it does not edit live solver files.
- Verification commands:
  - `python3 -m py_compile arc2_relational_micro_synth.py`
  - `python3 arc2_relational_micro_synth.py`
  - `python3 -m py_compile arc2_codex_relational_verifier.py`
  - `python3 arc2_codex_relational_verifier.py`
- Current Claude flips: `[]`; integration-ready operators: none.
- Static leakage scan of `arc2_relational_micro_synth.py`: no actionable calibration/frozen/public/template/solver replay hits; target task IDs appear only as the explicit design-lane target list.
- Codex oracle classes from `tmp/codex_relational_verifier.json`:
  - `dd6b8c4b`: `selector_oracle_panel_fill`; oracle render works, consumed-marker selector remains open.
  - `3dc255db`: `path_endpoint_or_parameter`; segment/ray rendering looks expressible with oracle endpoints, but endpoint/host pairing is unknown.
  - `35ab12c3`: `path_endpoint_or_parameter`; needs routed line plus motif/path parameterization.
  - `142ca369`: `path_endpoint_or_parameter`; drawing is mostly endpoint/path parameterization.
  - `195c6913`: `path_endpoint_or_parameter` from generic diff geometry, but Claude's panel render family is wrong for it.
  - `4a21e3da`: `renderer_or_decomposition_for_generated_structure`; still needs the dedicated marker-relative relocate/spine renderer.
- HANDOFF TO CODEX: none yet. Do not integrate until Claude or the verifier produces a train-exact + LOO transform with a concrete transform handoff.
- QUESTION FOR CLAUDE: for `dd6b8c4b`, can the consumed-marker selector be expressed at the component/graph level rather than the cell-feature level? The next useful ablation is to label whole marker components consumed iff all/any cells are oracle-consumed, then search graph features involving the `6` path/host components: side of panel, connected side, path-region membership, line-of-sight through path gaps, and symmetry partner.

Codex sentinel update, 2026-05-30 21:32 CDT:

- Extended `arc2_codex_relational_verifier.py` with a component-graph selector ablation for panel-fill tasks.
- `dd6b8c4b` marker-component oracle labels: `12` all-consumed components, `5` non-consumed components, `1` partially consumed component.
- Interpretation: whole-component keep/remove is not expressive enough; at least one train pair requires splitting a marker component and selecting an endpoint/sub-cell subset.
- Single component features still conflict: size, distance to panel/path, side of panel, and clear ray all have values shared by consumed and non-consumed components.
- Updated question for Claude: for `dd6b8c4b`, search a two-stage selector: first choose candidate marker components by graph relation to the `6` path/host, then choose consumed cells inside partial components by endpoint, exposure, or nearest path/panel relation.

Codex sentinel update, 2026-05-30 21:34 CDT:

- Claude added segment/motif oracle ablations to `arc2_relational_micro_synth.py`; Codex reran the verifier.
- Current Claude flips remain `[]`; no live integration.
- Claude's segment oracle says only `3dc255db` has a fully expressible draw-segment renderer with unknown endpoints/anchors.
- Codex corrected its verifier to ignore single-cell additions when classifying line-render expressibility.
- Updated Codex classes:
  - `3dc255db`: `path_endpoint_or_parameter`
  - `dd6b8c4b`: `selector_oracle_panel_fill`
  - `35ab12c3`: `motif_placement_or_anchor` in Codex's loose diagnostic, but Claude's stricter single-motif oracle is still false; treat as not promotable.
  - `4a21e3da`, `142ca369`, `195c6913`: `renderer_or_decomposition_for_generated_structure`
- QUESTION FOR CLAUDE: `3dc255db` is now the best narrow next target. Since all multi-cell added components are straight segments, try endpoint/anchor selector search over marker fragments and host objects, with LOO refit. A train-exact + LOO segment endpoint rule would be the first candidate worth handing to Codex for integration.

Codex sentinel update, 2026-05-30 21:37 CDT:

- Extended `arc2_codex_relational_verifier.py` with segment-endpoint oracle diagnostics.
- For `3dc255db`, every multi-cell added component is a straight segment and every added segment color has same-color removed fragments in the input.
- Segment details:
  - pair0: color `6` horizontal segment has aligned removed fragments; color `7` horizontal segment has same-color removed fragments but not aligned by row/col/diag.
  - pair1: color `9` vertical segment has aligned removed fragments.
  - pair2: color `7` vertical segment has aligned removed fragments.
- Interpretation: `3dc255db` is not renderer-limited. It needs endpoint/anchor parameters over removed same-color marker fragments plus host-structure context. A simple "same line as removed fragment" rule is insufficient because of the pair0 color `7` exception.

Codex answer to Claude questions, 2026-05-30 21:41 CDT:

- Live `arc2_candidate_solver.py` has generic connected components, bboxes, frame rectangles, contact/alignment pairs, and several task-family-specific direction heuristics.
- It does not appear to expose a reusable "6-rectangle decoration membership" primitive for `dd6b8c4b`.
- It does not appear to expose a reusable object "pointing direction" / apex primitive for `3dc255db`.
- Closest existing pieces:
  - `connected_components`, `framed_content_rectangles`, `contact_pairs`, `alignment_pairs`
  - one-off frame/corner/rail/direction logic inside fixed operators such as `project_singleton_frame_markers_to_corners` and `slide_marked_components_to_boundary_axes`
- Integration implication: if Claude can make either host-decoration membership or pointing/apex detection train-exact + LOO in the standalone lane, Codex can port that primitive into `arc2_candidate_solver.py`; there is no obvious existing live helper to reuse directly.

Codex sentinel update, 2026-05-30 21:47 CDT:

- Reran `python3 -m py_compile arc2_relational_micro_synth.py arc2_codex_relational_verifier.py` and `python3 arc2_codex_relational_verifier.py` after Claude's latest report attachment.
- Current Claude flips remain `[]`; `integration_ready=false`; no live solver integration.
- Tightened `arc2_codex_relational_verifier.py` so loose rigid-copy geometry no longer labels `35ab12c3` as motif/anchor when Claude's strict segment/copy/stamp oracle rejects that explanation.
- Verified six-task locus:
  - `dd6b8c4b`: selector. Oracle renderer works, but consumed-marker selection is still unsolved.
  - `3dc255db`: parameter. Segment renderer is expressible; endpoint/anchor direction remains unsolved. Claude reports length is clean/LOO-consistent, but direction/anchor needs a host pointing/apex parser.
  - `4a21e3da`, `35ab12c3`, `142ca369`, `195c6913`: renderer/generative-structure limited.
- Verified all-23 locus distribution from `tmp/claude_relational_locus_all23.json`: `renderer=14`, `decomposition=7`, `selector=1`, `parameter=1`.
- Handoff status: none. Continue sentinel polling; integrate only if a concrete train-exact + LOO transform handoff appears.

Codex sentinel update, 2026-05-30 21:50 CDT:

- Added `host_apex_parameter_ablation` to the standalone verifier for `3dc255db`-like segment tasks.
- Result on `3dc255db`: every oracle segment has at least one adjacent host color whose color-group sparse bbox side matches the output segment side.
  - pair0 marker `6`: host color `4` sparse side `right`, segment side `right`, unique candidate.
  - pair0 marker `7`: host color `3` sparse sides `left/right`, segment side `left`, unique candidate but side ambiguous.
  - pair1 marker `9`: sparse-side match exists, but host candidate is ambiguous between colors `3` and `6`.
  - pair2 marker `7`: host color `6` sparse side `above`, segment side `above`, unique candidate.
- Interpretation: `3dc255db` may be host-apex/parameter limited rather than renderer limited, but the current ablation is not a transform because it uses oracle added segments and still leaves ambiguous host/side choices. Useful next Claude-side search: choose marker-host pair by adjacency to erased marker fragments, choose sparse side by color-group bbox edge count, then LOO-test segment placement and length. Do not integrate yet.

Codex sentinel update, 2026-05-30 21:53 CDT:

- Verified Claude commit `3beaadab` / object-extension wrap.
- Ran `python3 -m py_compile arc2_object_extension_synth.py` and `python3 arc2_object_extension_synth.py`.
- Result: `object_extension_line_growth` over the 23 genuine design misses found `0` train-exact variants and `0` flips; `tmp/claude_object_extension_results.json` agrees with Claude's report.
- Static scan of `arc2_object_extension_synth.py`: no `arc_agi_2_data/test`, pseudo-private split, public-signature, template, or `solve_` references; no embedded task-ID string constants found by the quick AST scan.
- Reran `python3 arc2_codex_relational_verifier.py`; Claude relational flips remain `[]`, `integration_ready=false`.
- Handoff status remains none. Do not alter `arc2_candidate_solver.py` from this lane.

Codex note to Claude on next build, 2026-05-30 22:43 CDT:

- Recommendation: start option (a), the object-graph IR + parser bank scaffold.
- Scope: standalone reusable infrastructure only. Do not edit `arc2_candidate_solver.py`, `submission_helper.py`, or Kaggle packaging yet.
- First deliverable should be a stable contract, not a new per-task solver:
  - parser bank for color components, monochrome components, frames/rectangles, holes, line segments, panels, and foreground/background regions;
  - object graph nodes for `Grid`, `Region`, `Obj`, `ObjSet`, `Point`, `Route`, `Overlay`, `Color`, `Dir`, `Int`, `Bool`;
  - relation edges for containment, contact, alignment, ordering, bbox inclusion, same-shape, same-color, marker-host adjacency, and candidate apex/pointing directions;
  - pure overlay executor API, so drawing is separate from selection and can be composed/verified.
- Acceptance tests:
  - no task IDs in core parser logic;
  - parser outputs deterministic JSON summaries for the 23 current design misses;
  - `3dc255db` apex/pointing candidates are exposed in the graph, but no test-only frame-host rule is synthesized;
  - `dd6b8c4b` marker/6-host structural relations are exposed even though the selector remains falsified;
  - compile + leakage scan + result JSON.
- Handoff back to Codex only when there is either:
  - a concrete transform with train exact + informative LOO or cross-task firing >=2, or
  - a stable IR contract ready to port into the live solver behind a disabled feature flag.

Codex verification of object-graph scaffold, 2026-05-30 22:48 CDT:

- Claude added `arc2_object_graph.py` in commit `b884604b`.
- Verified commands:
  - `python3 -m py_compile arc2_object_graph.py`
  - `python3 arc2_object_graph.py`
- Result: parser bank validates on `23/23` current design misses; all 8 views are emitted and object graphs build.
- Static scan: no task-ID string constants and no `arc_agi_2_data/test`, pseudo-private, public-signature, template, or solver-replay references.
- Codex patched two scaffold correctness issues before handoff:
  - object IDs were call-history-dependent because `_mk` used a mutable default counter; IDs are now deterministic and compact per parser call;
  - `line_segments` advertised diagonal runs but emitted only horizontal/vertical runs; diagonal and anti-diagonal runs are now included.
- Remaining integration caveat: dense tasks can produce relation explosions (`89565ca0` first train pair: `60` color objects, `5080` relations), so downstream search should index/filter relations by sketch instead of iterating every edge.
- Handoff status: reusable standalone IR scaffold, not a live solver candidate. Port only behind a disabled feature flag after API contracts stabilize.

Codex probe result, 2026-05-30 21:58 CDT:

- Added standalone `arc2_host_apex_router_probe.py` for the narrow `3dc255db` host-apex hypothesis. This is design-only and not a Kaggle candidate.
- The probe searches simple input-feature marker predicates plus sparse-host-side ray rendering.
- It finds `2` train-exact variants on all three train pairs:
  - marker predicate `adj_cell_count <= 3`
  - side modes `farthest_lex` and `top_left`
- Admission result: rejected/quarantined. Leave-one-train-out fails for heldout pair `1`; local test readout remains diff `14`, selecting marker color `4` instead of the intended role.
- Static scan of the probe: no test-directory, pseudo-private, public-signature, template, or solver-replay references. The only task-ID string is the explicit design-probe target `3dc255db`.
- Interpretation: the train-exact host-apex rule is selection-inflated. Do not promote; keep `3dc255db` classified as parameter/selector hard until a marker-role predicate passes LOO and invariance.

Codex research-lane hygiene checkpoint, 2026-05-30 22:00 CDT:

- Compile batch passed for:
  - `arc2_shapefirst_cegis.py`
  - `arc2_current_coverage_audit.py`
  - `arc2_object_role_ops.py`
  - `arc2_symmetry_completion.py`
  - `arc2_nearmiss_frontier.py`
  - `arc2_relational_micro_synth.py`
  - `arc2_object_extension_synth.py`
  - `arc2_codex_relational_verifier.py`
  - `arc2_host_apex_router_probe.py`
- Quick text scan findings are documentation/audit self-references only: the Claude audit scripts mention `run_pseudo_private_eval` because they intentionally import the hidden-faithful evaluator read-only; `arc2_shapefirst_cegis.py` prints the count of scrubbed `solve_` functions; `arc2_codex_relational_verifier.py` contains the forbidden tokens inside its own static-scan pattern list.
- No new live-solver handoff.

Deep research prompt checkpoint, 2026-05-30 22:04 CDT:

- Added `ARC2_DEEP_RESEARCH_PROMPT.md`.
- Purpose: send a browser Deep Research track after the now-falsified generic-operator lane.
- Scope: per-task / learned program synthesis over object-graph DSLs, routing/redraw, abstraction growth, neural-guided search, synthetic task generation, ranker/verifier design, and Kaggle-safe admission.
- Companion Claude prompt included: use research output for standalone probes only; hand off to Codex only after train-exact + LOO + synthetic invariance + leakage scan.

Claude apex-ray checkpoint, 2026-05-30 22:08 CDT:

- Found `arc2_apex_ray_router.py`, a standalone Claude prototype for `3dc255db`.
- Verification command: `python3 -m py_compile arc2_apex_ray_router.py && python3 arc2_apex_ray_router.py`.
- Result: train-exact `true`, LOO `true`, params `[2, "away_from_frag", "min_frag_border"]`, but local design/public readout `0/1`; no flip.
- Static scan: no test-directory, pseudo-private, public-signature, template, or solver-replay references.
- Interpretation: useful research evidence for host-apex DSL design, but not promotable to live attempts.

Claude shape/decomposition handoff, 2026-05-30 ~23:15 CDT:
- arc2_shape_decomposition_synth.py (standalone, on arc2_object_graph). 5 families, train-exact + informative-LOO
  gate, leakage scan CLEAN. 0 flips on the 7 shape-change targets.
- Failure loci: 5dbc8537 = renderer (panel canvas correct, content is serialization); other 6 = shape/decomposition
  (output dims are data-dependent, not derivable by frame/panel/filler/summary/downscale).
- Implication for Codex: the shape GENERATOR for these 7 needs output_dims = relational fn of object-graph features
  (object counts, color-role counts, hole counts, bar lengths) — a learned/relational predictor, not a fixed crop
  family. Not promotable; no train-exact candidate. Results: tmp/claude_shape_decomposition_results.json.

Codex verifier update, 2026-05-30 22:57 CDT:

- Added `arc2_codex_research_artifact_verifier.py` as a repeatable sentinel for the newer standalone artifacts:
  `arc2_object_graph.py`, `arc2_shape_decomposition_synth.py`, and `arc2_typed_sketch_enumerator.py`.
- Verified command: `python3 -m py_compile arc2_codex_research_artifact_verifier.py && python3 arc2_codex_research_artifact_verifier.py`.
- Result:
  - object_graph: compile/run/static-scan clean; reusable infra only; not integration-ready.
  - shape_decomposition: compile/run/static-scan clean; `flips=[]`, `rows=7`, `train_exact_rows=0`, `loo_rows=0`; not integration-ready.
  - typed_sketch_enumerator: compile/run/static-scan clean; sketches emitted for `23/23` tasks, average bounded search space; no renderer/solver; not integration-ready.
- Output: `tmp/codex_research_artifact_verifier.json`.
- Live-solver status unchanged: do not edit/promote into `arc2_candidate_solver.py` unless a future artifact exposes a concrete transform with train-exact + informative LOO or cross-task firing, plus leakage/invariance checks.

Codex portability update, 2026-05-30 23:00 CDT:

- Added `ARC2_EVAL_DIR` support to `arc2_object_graph.py`, `arc2_shape_decomposition_synth.py`, and
  `arc2_typed_sketch_enumerator.py`.
- Reason: lightweight handoff/SIA worktrees intentionally do not carry the full ARC data tree. Claude's SIA wrapper
  can now mount/copy the allowed public/design evaluation files and run these standalone probes with
  `ARC2_EVAL_DIR=/path/to/evaluation`.
- Reverified `python3 -m py_compile arc2_object_graph.py arc2_shape_decomposition_synth.py arc2_typed_sketch_enumerator.py arc2_codex_research_artifact_verifier.py`
  and `python3 arc2_codex_research_artifact_verifier.py`; results unchanged, `integration_ready=[]`.

Claude SIA-quarantine handoff, 2026-05-30 ~23:25 CDT:
- Built sia_arc_shape_task/ — a tight, quarantined SIA custom task for the 7 shape-change misses. SIA runs ONLY
  in that dir, mutating target_agent.py; it must NOT edit arc2_candidate_solver.py / submission_helper.py /
  kaggle_modules / notebooks (documented in README).
- evaluator.py is the sandbox: fitness from hidden-safe signals only (train-exact + informative-LOO +
  cross-task-firing>=2 - leakage - compile-fail); the PRIVATE design-test match is LOGGED, never in fitness.
  Validated: baseline 0, adversarial cheat (task-id/private-read) -> -10 with leakage hits.
- Codex action when ready: if SIA finds a train-exact + informative-LOO (or cross-task-firing>=2) family,
  re-run evaluator.py, confirm leakage CLEAN + logged private readout, then port the family into
  arc2_candidate_solver.py behind a feature flag (manual, evidence-gated).

Codex SIA verifier update, 2026-05-30 23:03 CDT:

- Independently recompiled and ran `sia_arc_shape_task/evaluator.py`.
- Confirmed public split files contain train pairs plus test inputs only; no public test outputs.
- Baseline `reference_agent.py` result: `fitness=-0.0`, no leakage hits, zero train-exact candidates on all 7 tasks.
- Tightened evaluator leakage scan to flag broader private/test-output/raw-evaluation access patterns:
  `private`, `test_outputs`, `arc_agi_2_data`, and `evaluation`, in addition to task IDs/templates/signatures.
- Re-ran an adversarial `/tmp/cheat_agent_codex.py`: fitness `-20.0`, four leakage hits
  (private split, held-out outputs, hardcoded task ID twice). Quarantine still holds.

Codex SIA evaluator hardening, 2026-05-30 23:06 CDT:

- Tightened `informative_loo` so a full-train candidate only gets LOO credit when the same candidate name/family
  is re-derived on every leave-one-out fold. A different fallback candidate can no longer donate LOO credit.
- Reverified reference and adversarial agents:
  - reference: `fitness=-0.0`, `leaks=0`, `train_exact_total=0`, `loo_total=0`
  - adversarial: `fitness=-20.0`, `leaks=4`, `train_exact_total=0`, `loo_total=0`
