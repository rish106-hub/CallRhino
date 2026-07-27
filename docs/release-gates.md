# Release gates

CallRhino does not use one averaged accuracy number.

The release check requires two separate extraction reports:

1. A frozen holdout that prompt authors did not inspect during development.
2. A private set of consented, dual-reviewed real meetings.

Every critical metric must be at least `99.5%`. Each metric also needs at least
`200` labelled checks. A perfect score on eight synthetic cases therefore fails.
Schemas must pass at `100%`, and forbidden facts must remain at zero.

The default minimum data sizes are:

- `50` frozen holdout meetings
- `20` consented real meetings
- `200` checks for every critical field metric

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

Candidate gating requires `100%` gold evidence retention overall and in every
evaluated long meeting. Cost reduction never compensates for a missed gold fact.
