# ARC2 Program-Synthesis Target Queue

Generated from the quarantined SIA-lite runs and Claude/Codex design-miss taxonomy.
This is a coordination artifact only. Do not promote anything to the live solver from this file without the
normal gates: train-exact, informative LOO or cross-task firing, leakage scan, and guard eval.

## Current Verdict

The SIA-lite mutator lane is safe and useful as instrumentation, but it has not produced an admission-grade
operator.

- No generated candidate has `loo_tasks >= 1`.
- No generated candidate has cross-task firing `>= 2`.
- No generated candidate is target train-exact on the conditioned hard tasks.
- The only positive residual reduction so far is `cb2d8a2c`, `rowcol_cross_fill:row=2:col=2`, diff `131 -> 127`.

So the next work should not be more blind family mutation. It should be richer, typed program synthesis over
object graphs, relations, and renderers.

## Highest-Value Targets

### 1. `cb2d8a2c` — bracket-route and recolor around bars

Evidence:

- Same shape.
- Regular train transitions: mostly `8->3` plus `1->2`.
- SIA-lite found a slight near-miss: `rowcol_cross_fill:row=2:col=2`, train diff `127`.
- Full and residual-aware hill-climbs failed to improve it.

Likely sketch:

- Detect `1/2` bars or line objects.
- Recolor all `1` cells in those bars to `2`.
- Use each `3` marker as a routing source.
- Draw bracket/orthogonal routes that wrap or connect around bar structures.
- Route parameters must be learned from geometry, not absolute coordinates.

Needed primitives:

- `Bar` / `LineObject` extraction with orientation and extent.
- `Marker -> host bar` assignment.
- `orthogonal_bracket_route(marker, bar, side_policy, span_policy)`.
- Overlay renderer with collision policy.

### 2. `faa9f03d` — lowest residual line/structure renderer

Evidence:

- Same shape, four train pairs.
- Current best train diff: `50`, from `apex_ray:2:any_single:min_frag_border`.
- Full-model conditioned search preserved but did not improve the residual.

Likely sketch:

- Identify scaffold colors and path colors by train diffs.
- Extend or clean line structures through marker/anchor relations.
- Recolor consumed markers or broken segments by role.

Needed primitives:

- Endpoint and junction graph.
- Same-color and cross-color path completion.
- Role-dependent erase/recolor of marker fragments.

### 3. `88bcf3b4` — rail/anchor relocation

Evidence:

- Same shape, five train pairs.
- Current best train diff: `51`.
- Claude notes: object relocates toward a same-column anchor along a rail.

Likely sketch:

- Parse movable object, anchor, and rail.
- Determine displacement from anchor relation.
- Move or copy object along rail; clean source/target by background policy.

Needed primitives:

- `object_on_rail`, `same_row_or_col_anchor`, `translate_until_anchor`.
- Collision-aware erase/stamp.

### 4. `7b0280bc` / `d8e07eb2` — global/relational recolor/flood

Evidence:

- Same-shape recolor/flood tasks.
- `7b0280bc`: transitions introduce role colors `3` and `5`; current diff `71`.
- `d8e07eb2`: large `8->3` and sometimes `8->2` floods; current diff `745`.
- Per-object local features did not separate changed vs unchanged cells.

Likely sketch:

- Infer global trigger per pair, then select regions by position/template relation.
- Apply role-color mapping to selected regions.

Needed primitives:

- Region template matching across train pairs.
- Band/panel relation parser.
- Global condition variables: count, marker presence, symmetry, panel index.

### 5. `142ca369` / `195c6913` — draw-from-background renderer

Evidence:

- Same shape.
- Train diffs are `0 -> colored cells`.
- Current best for `142ca369`: diff `110`; diagonal/draw-from-seed variants did not improve.

Likely sketch:

- Use existing colored objects as seeds/templates.
- Draw missing motif/route/diagonal structure into background.
- Parameters are offsets, directions, and color-role assignments.

Needed primitives:

- Seed object to route/motif expansion.
- Directional/diagonal draw.
- Motif copy with learned offsets.

## Next Build Recommendation

Build a standalone object-graph program-synthesis scaffold rather than another SIA mutation run:

1. Parse objects, bars, endpoints, anchors, rails, panels, and changed-region residuals.
2. Enumerate typed sketches for route/bracket/move/flood/draw.
3. Score sketches on train exactness and informative LOO.
4. Emit a report plus candidate factories only when the sketch is train-exact.
5. Keep live solver untouched until independent Codex verification.
