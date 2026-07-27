# Long-meeting candidate-gate evaluation

This evaluation checks whether local candidate filtering removes evidence needed by
the canonical extractor. It does not call Sarvam, OpenAI, or any other provider.

## Release rule

Candidate gating stays disabled until an annotated long-meeting evaluation reaches:

- 100% overall gold evidence segment retention
- 100% all-evidence retention for every case that contains gold evidence
- at least one case where candidate filtering actually runs

An empty manifest or a manifest with no decision or action evidence cannot pass.
Metrics with no valid denominator are reported as `null`, not 100%.

## Manifest format

Use the existing `ExtractionCaseManifest` format. Start from
`evals/cases/long_meetings.template.json`.

Each case needs:

- the full transcript
- a stable case ID
- meeting metadata and provenance
- every expected decision
- every expected action
- exact `evidence_segment_ids` for each expected item

Segment IDs are assigned in transcript order as `seg_0001`, `seg_0002`, and so on.
Run the normal transcript segmenter when checking annotations. Do not guess IDs from
visual line numbers when a speaker turn wraps across lines.

Use consented private meetings for release evidence. Synthetic cases are useful for
regression tests but do not prove production recall.

## Run

```bash
uv run python scripts/evaluate_candidate_recall.py \
  --cases evals/cases/long_meetings.json \
  --output evals/results/long_meeting_candidate_recall.json \
  --require-gate
```

Remove `--require-gate` during dataset development if you want a report without a
failing exit status.

## Report

The report includes:

- baseline retention with candidate filtering disabled
- gated evidence retention overall
- separate decision and action evidence retention
- case-level all-evidence retention
- selected segment ratio
- canonical prompt character reduction
- missed evidence IDs for each case
- warnings and release-gate failure reasons

Prompt size uses the full canonical system and user messages. This is deliberately
more conservative than measuring transcript characters alone.

## Annotation checks

Review every case before accepting a release result:

1. Confirm each transcript is complete.
2. Confirm each expected decision and action is present.
3. Confirm each evidence set is the smallest set that proves the item.
4. Include context segments needed for acceptance, ownership, reversal, or conditions.
5. Resolve disagreements with a second reviewer.
6. Freeze the evaluated manifest before changing candidate cues or selector settings.

Do not tune the selector against a private holdout and then report the same holdout as
independent release evidence.
