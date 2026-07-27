# Release gates

CallRhino does not use one averaged accuracy number.

The release check requires two independently identified reports:

1. A frozen holdout that prompt authors did not inspect during development.
2. A private set of consented, dual-reviewed real meetings.

Each report must include its evidence kind, dataset ID, 64-character dataset
fingerprint, prompt version, provider, and model. Reused datasets, stale prompts,
or incomparable model runs fail.

Every critical metric needs at least `600` labelled checks. Its one-sided 95%
Wilson lower confidence bound must be at least `99.5%`. A point estimate of
`599/600` therefore fails. Schemas must pass at `100%`, and manually specified
forbidden facts must remain at zero.

The default minimum sizes are:

- `50` frozen holdout meetings
- `20` consented real meetings
- `600` checks for every critical field metric

Run:

```bash
uv run python scripts/check_release_gates.py \
  --holdout-report path/to/holdout-report.json \
  --real-meeting-report path/to/real-meeting-report.json
```

When candidate gating is enabled, also pass:

```text
--candidate-gating-enabled
--candidate-report path/to/long-meeting-report.json
```

Candidate gating requires at least 20 long meetings, 200 gold evidence
segments, non-zero decision and action evidence, at least one genuinely
filtered case, and 100% retention. Cost reduction never compensates for a
missed gold fact.

The forbidden-fact metric checks only the forbidden facts written by reviewers.
It is not proof that every possible unsupported statement was detected.
