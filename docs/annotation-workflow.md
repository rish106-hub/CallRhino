# Human annotation workflow

This layer creates private gold extraction cases from consented meetings. It is
local and JSON-backed. It does not store raw audio, audio paths, or provider
payloads.

## Data boundary

Store annotation files outside the public repository. Each meeting record
contains:

- meeting metadata and a consent reference
- consent, PII-review, and redaction status
- the final reviewed transcript segments
- up to two immutable reviewer submissions
- one immutable adjudication containing the gold `ExtractionCase`

Registration requires active consent. PII review must be complete. If PII was
found, the stored transcript must already be redacted and redaction must be
marked complete. Withdrawing consent through the annotation app deletes the
private JSON record and its stored transcript before any later benchmark run.

Start the private local interface with:

```bash
uv run streamlit run annotation_app.py
```

Do not deploy this interface publicly.

Use the Coverage tab or
[`check_annotation_coverage.py`](../scripts/check_annotation_coverage.py) to
track the remaining language, noise, meeting, decision, and action quotas. See
[`real-meeting-collection.md`](real-meeting-collection.md) for the collection
boundary.

## Segment preparation

Review and redact the transcript before registration. Segment IDs must be
canonical and contiguous:

```text
seg_0001
seg_0002
seg_0003
```

Reviewers cite the minimum complete set of these IDs for every decision and
action. Unknown evidence IDs are rejected.

## Independent review

Two people submit labels without seeing model output or the other person's
submission. Each reviewer uses stable item IDs within the meeting, such as
`decision_launch` or `action_vendor_po`.

A reviewer submission is append-only. The same identity cannot submit twice,
including with different capitalization. A third submission is rejected.

The comparison service reports disagreements for:

- item presence
- decision versus action classification
- every structured field
- exact evidence segment sets

Evidence order alone is not a disagreement.

## Adjudication

Adjudication is blocked until two distinct reviews exist. The adjudicator checks
every disagreement against the reviewed transcript and submits final decisions,
actions, evidence IDs, and forbidden facts.

The result is one `ExtractionCase` with `provenance="consented"`. It can be
placed into the private holdout manifest after split-leakage validation. The
adjudication is immutable. Corrections require a new meeting-record version
rather than silently changing benchmark truth.

## Storage guarantees

The repository writes to a temporary file, flushes it, and atomically replaces
the meeting JSON. New record files use owner-only read/write permissions.
Per-meeting file locks prevent two local processes from overwriting each
other's submissions.

Atomic replacement protects against partial JSON. It does not provide encrypted
storage, user authentication, or backups. The private annotation directory still
needs restricted filesystem permissions and an explicit retention policy.
