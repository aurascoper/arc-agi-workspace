# Relational micro-synthesis — design-only report (Claude lane)

*Standalone (`arc2_relational_micro_synth.py`); never edits Codex hot files. Design-only: synthesis uses
train pairs only; design test output is a READOUT; no task ids / coordinate signatures / public templates /
frozen calibration / replay. Generated 2026-05-30 ~21:50 CDT.*

## Objective & method
Test whether the 23 strict design misses are SELECTOR-limited (tractable search/relational-feature problem)
or RENDERER-limited (a missing generative primitive). Represent grids as bg / host objects / marker
fragments / paths / panels and search small generative relational programs (erase, fill-panel-by-count,
draw-segment, stamp-motif, relocate). The instrument is a set of **oracle ablations**: compute a render
family's parameters from the train OUTPUT (readout) and test whether the render then reproduces train. This
isolates the failure locus into a 4-way taxonomy: **decomposition | selector | parameter | renderer**.

Gate for any real (non-oracle) operator: train-exact + leave-one-train-out (LOO) + synthetic invariance.

## Result: 0 flips; precise 4-way locus for the 6 priority targets

| task | oracle render exact? | 4-way locus | evidence |
|---|---|---|---|
| **dd6b8c4b** | **yes** | **selector** | fill-panel-by-marker-count render reproduces train with the oracle consumed set (counts 2/9/4). NO single- or two-feature selector over {comp_size, degree, endpoint, on_border, dist_panel, dist_path, near_path, attached, enclosed_by_path, clear_ray_to_panel, halves, quadrant} separates consumed vs non-consumed (every feature has a conflict value). Relational signal: pair2 (no 6-structures) → all 4 consumed; pair0 (with 6-structures) → 2/12. The selector is a relational function of the 6-path host structures. |
| **3dc255db** | seg-draw yes | **parameter** | every multi-cell added component is a straight segment (frac 1.0/1.0/1.0). The render is "erase embedded marker fragment + draw clean exterior ray". The wall is the endpoint/anchor PARAMETERS (anchor point, outward direction, length) — a relational function of host geometry + fragment, not the renderer. |
| 4a21e3da | no | **renderer** | additions are generated, non-rigid (0% rigid copies; only 33–50% straight segments). Needs orientation-changing object redraw + marker spine — a generative primitive not in the vocabulary. |
| 35ab12c3 | no | **renderer** | added multi-cell components are large irregular diagonal multi-color routes (62–80% "rigid" was the single-cell artifact; corrected = generated). Needs parametric routing + motif generation. |
| 142ca369 | no | **renderer** | additions are scattered generated cells (0% segments/copies). |
| 195c6913 | no | **renderer** | recolor (20–69 cells) + generated fill; 0% segments/copies. |

**Summary: 1 selector-limited, 1 parameter-limited, 4 renderer-limited. No flip.**

## What this means (which representation failed, and why)
- The **relational-selection** representation (decompose → select host → select marker → erase → render)
  is the RIGHT shape for `dd6b8c4b` (render expressible) — but the consumed-marker selector is genuinely
  relational (depends on 6-path host structure membership), beyond any 1/2-feature predicate. This is a
  *search/relational-feature* gap, not a representation gap.
- `3dc255db` is **parameter-limited**: the segment-draw renderer exists; the open problem is a relational
  rule for the ray's anchor/direction/length (collapse internal fragment → exterior ray).
- The remaining 4 are **renderer-limited**: their added structure is generated (non-rigid, non-segment,
  non-stamp). The relational-program vocabulary's renders (erase/fill/segment/stamp/copy) cannot express
  them. They need richer generative primitives (orientation-changing redraw + spine; parametric routing;
  multi-color motif generation; fill patterns).

## Recommended next representation level
1. For `dd6b8c4b` (selector): a relational selector that reasons about **host-structure membership** — e.g.
   "marker cells not part of any 6-bounded glyph / not on a 6-rectangle's decoration set." Needs a
   structure-parse of the host frames, then set-difference. Candidate for an LOO-stable relational rule.
2. For `3dc255db` (parameter): a **ray-from-host-anchor** primitive whose (anchor, direction, length) are
   learned as functions of host apex/border distance; test LOO on the held pair's drawn ray.
3. For the renderer-limited 4: a **generative drawing DSL** (parametric line/ray with learned direction;
   object-redraw under D4+scale; motif-along-axis) — i.e. DreamCoder-style primitive growth, not selection.

## Honest caveats
- Single-cell added components are trivially D4-invariant; the rigid-copy and segment classifiers ignore
  size-1 components (fixed). `35ab12c3`'s earlier "62–80% rigid" was that artifact.
- Oracle ablations are READOUT-only (parameters from train output) and never ship; they only localize the
  wall. No operator here is train-exact, so nothing is promotable.

## Agent Mailbox

### HANDOFF TO CODEX
- None yet (no train-exact + LOO operator). The two tractable leads above (`dd6b8c4b` selector,
  `3dc255db` ray parameters) are *not yet flipped*; do not integrate.

### ANSWER TO CODEX (re `3dc255db` endpoint/anchor search, 21:40 CDT)
Ran the endpoint/anchor selector search you requested over marker fragments + host objects, with LOO:
- **LENGTH rule is clean and LOO-consistent:** `len(segment) = min(fragment_cell_count, distance_to_border
  in the draw direction)` (pair0 not-border → len=frag=2/2; pair2 frag=7 but border-limited → 3).
- **DIRECTION/ANCHOR is NOT a clean geometric function** — falsified across the 6 structures:
  - "opposite side of host from fragment" fails (dot(seg−host, frag−host) > 0 for 3 of 4 clean structures).
  - host-object identification is ambiguous (hosts are multi-part shapes; nearest-component picks fragments).
  - direction is host-shape-specific (funnel→up, L→right, L→left) — i.e. it depends on a host *arrow/apex*
    parse, not a centroid/border relation. No single direction rule is train-exact across the 3 diverse pairs.
- **Verdict:** `3dc255db` is parameter-limited but the direction parameter needs a host-pointing-direction
  parser (arrow/funnel apex per host shape). Not a clean LOO-stable endpoint rule → **not promotable** as-is.
  If your live decomposition exposes a host "pointing direction" / apex per object, that is the missing piece.

### QUESTION FOR CODEX
- For `dd6b8c4b`: does your live decomposition expose "6-rectangle decoration" membership per cell? If you
  have a host-frame parse, the consumed-marker selector may be "markers not in the host decoration set".
- For `3dc255db`: do you have a per-object "pointing direction"/apex primitive? That + the clean length rule
  above could complete the segment-draw operator.

### DO NOT DUPLICATE
- fill-panel-by-marker-count oracle + single/two-feature consumed-marker selector search (done, no flip).
- rigid-copy / segment / single-motif-stamp oracle ablations (done).

## Strategic map: 4-way locus across ALL 23 genuine design misses (`tmp/claude_relational_locus_all23.json`)

*(recolor-aware; `faa9f03d` moved selector→renderer once recolors are counted — see note below)*

| locus | count | meaning | tasks |
|---|---:|---|---|
| **renderer** | 14 | additions are generated structure (or mixed add+recolor multi-op); no segment/copy/stamp render reproduces them → needs a generative drawing DSL / abstraction growth | 88bcf3b4, cb2d8a2c, 142ca369, 195c6913, 36a08778, 4a21e3da, 16b78196, 446ef5d2, 7b0280bc, abc82100, d8e07eb2, 271d71e2, faa9f03d, 35ab12c3 |
| **decomposition** | 7 | shape-change; cannot parse to the right output canvas without an output-shape op (then content render) | 5dbc8537, edb79dae, 20a9e565, 2d0172a1, 6ffbe589, e87109e9, 89565ca0 |
| **parameter** | 1 | segment-draw renderer expressible; ray endpoints/anchor unknown (relational, structure-dependent) | 3dc255db |
| **selector** | 1 | fill-panel render expressible (oracle); consumed-marker selector relational, not 1/2-feature-separable | dd6b8c4b |

**Strategic reading for Codex:** only **2/23 are "close"** (1 selector `dd6b8c4b` + 1 parameter `3dc255db` —
render expressible, selection/endpoint unknown), and both are genuinely hard relational problems that
resist clean LOO-stable rules (investigated: `dd6b8c4b` no 1/2-feature consumed-selector; `3dc255db` ray
length/direction is structure-dependent — pair0 length=fragment-count=2, pair2 length=border-distance=3).
**7/23 are decomposition-limited** (need an output-shape *generator*, not just the shape-profile ranker).
**14/23 are renderer-limited** — genuinely new generative primitives (parametric routing, orientation-
changing object redraw, multi-color motif generation, multi-structure extend+recolor), i.e. abstraction
growth, not selection. **Classifier caveat:** the oracle ablations test ADDITIONS; tasks with significant
recolors (`faa9f03d`: 7/3/6 recolored cells/pair; `195c6913`: 20–69) are mixed-op and were re-bucketed to
renderer (recolor-aware). This quantifies the representation wall: the relational-selection vocabulary
reaches ~2/23; the majority need new renderers or shape generators. (Oracle-readout only; nothing promotable.)

## Renderer-limited (14) — generative-primitive sub-classification (build priority for Codex)
`tmp/claude_renderer_subclass.json`. Which single new primitive covers the most renderer tasks:

| needed primitive | #tasks | tasks |
|---|---:|---|
| **object extension** (grow line/object from an existing object along an axis) | 4 | cb2d8a2c, 36a08778, 446ef5d2, 35ab12c3 |
| irregular generated structure (varied; hardest) | 5 | 4a21e3da, 16b78196, 7b0280bc*, d8e07eb2, 271d71e2 |
| line/ray routing (thin segments) | 2 | 88bcf3b4, abc82100 |
| extend + recolor (multi-op) | 2 | 195c6913, faa9f03d |
| scattered-cell fill/draw | 1 | 142ca369 |

*`7b0280bc` is actually pure recolor (add=0, recol=71) — a relational recolor my role-recolor lane couldn't
fit; flagged for a relational-recolor primitive, not generation.

**Highest-coverage single build:** an **object-extension primitive** (grow an object/line from an existing
object's edge along a learned axis, length to border or by count) covers **4/14** renderer tasks and is the
most tractable generative primitive — recommend Codex build/LOO-gate that first. Routing (2) and
extend+recolor (2) are next. The 5 "irregular" are the genuine compositional core (multi-rule), best left to
abstraction-growth. (All sub-classification is design-only readout; nothing promotable here.)

## Object-extension primitive (user-requested build #1) — FALSIFIED 0/23 (`arc2_object_extension_synth.py`)
Built a real generative extension primitive (6 variants: extend-maximal-segments-to-border both/forward,
stop-at-nonbg/through; rays-from-singletons h/v/hv), gated train-exact + LOO + colour-perm invariance,
run across all 23 genuine design misses. **0/23 train-exact, 0 flips.** The "object extension" renderer
sub-class is mislabeled by adjacency: examined directly, `cb2d8a2c` traces an L-path of 3s from a single
marker (anchor → down → left → down), `36a08778` routes 6-paths *between* 2-segments. These are
**conditional, anchored PATH-ROUTING** (learned turn-points / pairing), not naive line-extension-to-border.
→ refines the renderer recommendation: the needed primitive is **anchored path-routing with turn-points**
(connect/trace), a harder generative op than extension. Confirms the renderer-limited verdict; the 23 misses
resist every disciplined (LOO-stable, generic) operator tested across this lane (selection, fill, segment,
stamp, copy, symmetry, recolor, extension). `tmp/claude_object_extension_results.json`.

## BREAKTHROUGH (partial) — apex-ray router for 3dc255db (`arc2_apex_ray_router.py`)
Cracked the **apex-ray abstraction** via search-based host/tip/length enumeration with LOO:

> **Rule:** group cells by colour. For each (host colour H, marker colour M) with |H|≥|M| and M-cells inside
> H's bounding box: erase those M-cells (the embedded fragment); draw a ray of colour M from H's
> **single-cell tip** (the direction where H narrows to one extreme cell), outward, length =
> min(|fragment|, distance-to-border).

**Evidence:** train-exact **3/3** (residual 0 on all train pairs); synthetic colour-permutation invariance **True**.
**BUT — not a genuine flip, NOT promotable:**
- **LOO is VACUOUS.** The router is *parameter-free* (min_host/tip/length are fixed hypotheses; the rule
  derives everything from the grid), so refit-on-subset returns the identical transform — "LOO" collapses to
  per-pair train-exactness (no genuine out-of-sample refit). This is the same fixed-operator LOO-vacuity
  documented earlier this project for finite-miss promotions.
- **Design-test readout = 0/1** (the real out-of-sample signal): residual 8 on the test, on a **frame-host**
  structure (a `2`-frame opening sideways with a `4`-marker) and an `8`-marker structure whose host shapes
  are NOT in the 3 train pairs (which only had funnel/arrow hosts). The `away_from_frag` tip rule is
  underdetermined for frame-hosts → wrong direction. A train-justified fix is impossible (the frame-host is
  test-only; fitting it would be leakage).

### HANDOFF TO CODEX — apex-ray operator (validated abstraction, NOT a solve)
- **operator:** `apex_ray_from_host_tip`
- **abstraction:** erase bbox-contained marker fragment; draw marker-colour ray from host single-cell apex,
  length min(|frag|, border).
- **learned params:** none promotable (parameter-free; tip-direction rule is the open piece).
- **preconditions:** host colour-group with ≥1 single-cell tip; marker colour-group with cells inside host bbox.
- **synthetic invariance:** colour-permutation equivariant = True.
- **train / LOO / design readout:** train-exact 3/3; LOO vacuous (parameter-free); **design-test 0/1**.
- **failure mode:** host-apex/direction is underdetermined for **frame-hosts** (sideways-opening brackets) —
  works for funnel/arrow hosts only. Needs a robust per-object **pointing-direction** primitive (which your
  live decomposition may have — see my earlier QUESTION).
- **suggested integration:** do NOT integrate as-is (test 0/1). If you have a host pointing-direction/apex
  primitive that handles frames, the rest of this rule (bbox-fragment erase + min(frag,border) ray) is correct
  and would complete `3dc255db`. This is the first design-miss where the *abstraction* is pinned down.
