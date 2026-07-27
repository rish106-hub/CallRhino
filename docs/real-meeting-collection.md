# Real meeting collection

Public ASR datasets cannot prove CallRhino extraction accuracy. They usually
contain audio and transcripts, not reviewed decisions, accepted owners,
deadlines, or evidence spans.

## Collection boundary

Collect a meeting only when:

- every participant has agreed to evaluation use before recording or upload
- the consent record has a stable internal reference
- the transcript has completed PII review
- names, phone numbers, credentials, customer data, and other unnecessary PII
  have been redacted
- the meeting receives accurate language, noise, and speaker-quality tags

The annotation store does not keep raw audio.

## Required workflow

1. Register the reviewed transcript in the private annotation app.
2. Assign tags from the coverage plan.
3. Obtain two independent reviews without showing model output.
4. Adjudicate every disagreement.
5. Check coverage:

```bash
uv run python scripts/check_annotation_coverage.py \
  --plan evals/annotation-plan.template.json \
  --root data/annotations \
  --require-complete
```

6. Export gold only after coverage completes.
7. Keep holdout labels away from prompt authors and the extraction environment.

## Standard tags

- `indian-english`
- `hinglish`
- `tamil-english`
- `telugu-english`
- `noisy-call`
- `overlapping-speakers`
- `speaker-label-failure`

Meetings may satisfy multiple slices. Coverage counts unique adjudicated
meetings for the overall target and matching meetings for each slice.

## Consent record

The consent system itself remains external. CallRhino stores only its reference.
The record should identify the meeting, date, participants, permitted use,
retention period, withdrawal route, and the person who captured consent.
