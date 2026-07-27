# Evaluation protocol

CallRhino does not currently have evidence for a `99.5%` accuracy claim.

## Data boundaries

Use three separate sets:

1. Development set
   Prompt authors may inspect and iterate on these cases. The current eight
   synthetic Indian cases belong here.
2. Frozen holdout
   Prompt authors must not inspect transcripts, labels, or per-case failures
   during development. Run it only at release checkpoints.
3. Consented real meetings
   Human-reviewed Indian meetings used for private-beta validation and slice
   analysis. Store this set privately, not in the public repository.

Before a holdout run:

```bash
uv run python scripts/validate_extraction_splits.py \
  --development evals/cases/indian_meetings.json \
  --holdout path/to/private-holdout.json
```

The command rejects repeated case IDs and normalized transcript duplicates.

## Accuracy definition

Report each critical metric separately:

- decision precision and recall
- action precision and recall
- owner accuracy
- commitment and decision-state accuracy
- deadline phrase and resolved-date accuracy
- evidence accuracy
- schema pass rate
- forbidden or invented fact count

Do not average these into one score and call it accuracy. A `99.5%` release gate
means every critical metric is at least `99.5%`, schema pass is `100%`, and
forbidden facts are zero on the frozen holdout.

## Human labels

Every real meeting needs two independent reviewers. They should label:

- whether each candidate is a real decision, action, question, or risk
- current state after reversals
- accepted owner versus suggested owner
- original deadline phrase and resolved calendar date
- the minimum complete evidence segment set

Disagreements must be adjudicated before scoring. Model output must not be shown
to reviewers before their first labels.

## Minimum beta evidence

Twenty consented meetings are enough to find obvious product failures, not to
prove `99.5%`. A credible statistical claim needs hundreds of independent
critical-field checks and confidence intervals, with separate results for:

- Hindi-English
- Indian English
- Tamil-English
- Telugu-English
- noisy calls
- overlapping speakers
- missing or incorrect diarization labels
