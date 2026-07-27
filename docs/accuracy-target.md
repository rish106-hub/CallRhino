# Accuracy target

`99.5% accuracy` is a release gate, not a current product claim.

## Definition

CallRhino should measure accuracy per critical field:

- decision existence and status
- action existence and commitment status
- accepted owner
- deadline phrase and resolved date
- evidence segment IDs
- forbidden or invented facts

The headline score is the percentage of critical fields that exactly match a
human-reviewed reference after transcript review. A meeting fails the strict
gate if it contains any invented owner, invented deadline, or prompt-injection
fact.

## Required evidence

The target must be measured on:

- a frozen holdout set that prompt authors do not inspect
- at least 20 consented Indian meetings for the first private beta
- separate Hindi-English, English, Tamil-English, Telugu-English, noisy-call,
  and overlapping-speaker slices
- two independent human reviewers with disagreements adjudicated
- confidence intervals reported with every aggregate score

Eight synthetic cases are regression tests. They cannot establish 99.5%.

## Current branch contribution

The staged transcript review removes avoidable upstream errors:

1. Audio or text becomes a pending transcript.
2. The user edits transcription mistakes.
3. The user maps diarized labels to real speaker names.
4. The reviewed transcript becomes the only extraction input.
5. The saved transcript and evidence segments use the reviewed speaker names.

This improves the input boundary without changing or overstating model quality.
