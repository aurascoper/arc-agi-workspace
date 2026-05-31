# Sample Task Descriptions

## ARC-Style Program Synthesis

Given several train input/output grid pairs, write a small deterministic program
family that proposes transforms for unseen test inputs. Candidate transforms must
be learned from train pairs only. Held-out outputs are not available to the
agent; they are used by the evaluator only as a log-only readout.

Useful program families include object parsing, panel serialization, marker-host
actions, routing, stamping, flood-fill, symmetry completion, and relational
output-shape generation.
