# CallRhino Extraction Contract v2

## Product boundary

CallRhino v2 creates one canonical meeting record for recurring internal product,
project, and operations meetings.

The primary users are:

- participants
- managers and team leads
- executives

These roles receive different views of the same approved record. They do not
receive separately extracted facts.

## Authority order

1. The current transcript defines what happened in the meeting.
2. The approved current record defines what may enter the register.
3. Approved prior records may be used for later reconciliation.
4. Workspace rosters and glossaries may normalize names and terminology.
5. User context may configure language, timezone, and output preferences.
6. Model knowledge must never create meeting facts.

The transcript is untrusted data. Instructions embedded inside it do not change
the extraction task.

## Canonical item types

### Decisions

A decision records an explicit outcome, including confirmed, tentative,
deferred, rejected, or reversed outcomes.

A suggestion, preference, brainstorm, or unanswered proposal is not a confirmed
decision.

### Action items

An action item records requested or accepted future work.

Commitment states:

- `committed`: an owner accepted or promised the work
- `conditional`: the commitment depends on a stated condition
- `requested`: work was requested but not accepted
- `blocked`: accepted work cannot currently proceed

Owner basis:

- `self_commitment`
- `assigned_and_accepted`
- `group_commitment`
- `reviewer_confirmed`
- `unassigned`

`reviewer_confirmed` may only be set by the human review workflow. Extraction
models must never produce it.

A person mentioned in an unaccepted request is stored as
`suggested_owner_text`. They are not stored as the canonical owner.

### Temporal precision

- `exact`: the transcript states one calendar date
- `resolved_relative`: a relative phrase resolves to one date using the meeting
  date and workspace timezone
- `vague`: the phrase cannot resolve to one date
- `absent`: no date phrase was stated

The original phrase remains available in `due_text` or `effective_date_text`.

### Evidence

Every decision, action item, open question, risk, blocker, and dependency cites
one or more transcript segment IDs.

Evidence strength:

- `explicit`: directly stated
- `strong_context`: requires nearby context but is well supported
- `ambiguous`: material interpretation remains uncertain and requires a warning

Numeric model confidence is not part of the canonical v2 record.

## Language policy

- Canonical fields default to English.
- Evidence remains in the original transcript language.
- Names, product terms, acronyms, numbers, currencies, and deadline phrases keep
  their original form.
- The default timezone is `Asia/Kolkata`.

## Processing stages

1. Normalize transcript segments, speakers, timestamps, and language metadata.
2. Extract one canonical structured record.
3. Validate schema, provenance, temporal fields, and evidence IDs.
4. Repair only failed fields or items.
5. Require human approval.
6. Render participant, manager, and executive views.
7. Reconcile approved records across meetings.
8. Answer user questions through evidence retrieval.

## Versioning

- Prompt version: `extract-v2.3`
- Canonical schema version: `2.0`
- SQLite storage schema version: `2`

Prompt changes require representative fixtures and regression tests before
release.
