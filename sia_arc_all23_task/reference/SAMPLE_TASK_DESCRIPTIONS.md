# Sample Task Descriptions

## ARC-Style Program Synthesis

Given several train input/output grid pairs, write a small deterministic program
family that proposes transforms for unseen test inputs. Candidate transforms must
be learned from train pairs only. Held-out outputs are not available to the
agent; they are used by the evaluator only as a log-only readout.

Useful program families include object parsing, panel serialization, marker-host
actions, routing, stamping, flood-fill, symmetry completion, and relational
output-shape generation.

Prefer reusable abstractions that can be re-derived from different train folds:
choose object roles, anchors, colors, shapes, and output dimensions from the
training pairs. Fixed transforms can still be useful seed material, but they
need cross-task train-exact firing before they count as evidence.

Strong directions for this ARC lane:

- Renderer programs that draw missing structure after the right objects are
  identified: bridge endpoints, route brackets, stamp motifs, fill enclosed
  regions, complete simple symmetries, or scale/blit a learned shape.
- Shape/decomposition programs: remove separator/filler rows or columns, serialize
  panels, crop meaningful frame interiors, compact glyphs, or render object/color
  summaries.
- Relational programs: learn marker-to-host actions from train pairs rather than
  hard-coding dimensions, coordinates, task IDs, or output templates.
