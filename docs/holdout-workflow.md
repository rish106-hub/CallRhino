# Blind holdout workflow

This workflow keeps meeting inputs separate from gold labels. It is offline.
It makes no provider calls and contains no secrets.

The separation is an access-control boundary, not encryption. Give the public
input package to the person or process running extraction. Keep the private gold
package with the evaluator.

## 1. Prepare the source manifest

Create a private `ExtractionCaseManifest` using the existing evaluation case
schema. Each case must have:

- a unique case ID
- a unique normalized transcript
- the meeting input and provenance
- reviewed decisions, actions, evidence IDs, and forbidden facts

Do not commit consented meeting data or gold labels to the public repository.

## 2. Split input from labels

```bash
uv run python scripts/create_holdout_package.py \
  --cases /private/callrhino/holdout-source.json \
  --public-output /private/callrhino/run/holdout-input.json \
  --gold-output /private/callrhino/gold/holdout-gold.json
```

The command creates:

- `holdout-input.json`: meeting inputs and fingerprints, with no expected
  decisions, expected actions, forbidden facts, or nested gold case
- `holdout-gold.json`: the original cases and labels, plus the same fingerprints
- one deterministic package ID shared by both files

Cases are sorted by ID. The package ID is stable across source case ordering.
Transcript fingerprints use normalized transcript text. Input fingerprints cover
all model-visible case fields.

## 3. Run extraction

Run the extractor only with `holdout-input.json`. The capped Sarvam runner never
loads the private gold package:

```bash
uv run python scripts/run_sarvam_holdout.py \
  --public-package /private/callrhino/run/holdout-input.json \
  --model sarvam-105b \
  --max-cost-inr 10 \
  --output /private/callrhino/run/predictions.json
```

The prediction package uses this shape:

```json
{
  "format_version": "1.0",
  "package_id": "holdout_...",
  "strategy": "canonical",
  "prompt_version": "extract-v2.3",
  "actual_total_cost_inr": 0.1,
  "predictions": [
    {
      "case_id": "meeting_001",
      "input_fingerprint": "64-character fingerprint copied from the input case",
      "provider": "sarvam",
      "model": "sarvam-30b",
      "latency_seconds": 1.2,
      "schema_valid": true,
      "repaired": false,
      "prompt_tokens": 1200,
      "completion_tokens": 400,
      "estimated_cost_inr": 0.01,
      "brief": {
        "decisions": [],
        "action_items": []
      },
      "error": null
    }
  ]
}
```

Before opening a provider connection, the runner reserves a deliberately high
cost ceiling. It treats every UTF-8 input byte as a possible token and reserves
two complete 4,096-token outputs. If that ceiling exceeds `--max-cost-inr`, it
exits without making a Sarvam request.

There must be exactly one prediction for every public case. Copy the package ID
and input fingerprints. Do not recalculate or omit them.

## 4. Score privately

Move the prediction file to the evaluator. Do not move the gold package to the
extraction environment.

```bash
uv run python scripts/score_holdout_package.py \
  --gold /private/callrhino/gold/holdout-gold.json \
  --predictions /private/callrhino/run/predictions.json \
  --output /private/callrhino/results/holdout-score.json
```

The scorer refuses to run when:

- package IDs differ
- predictions are missing or contain extra case IDs
- prediction IDs are duplicated
- any input fingerprint differs
- private meeting inputs or their stored fingerprints changed after packaging

It uses CallRhino's existing extraction metrics and writes the normal summary
with per-case scores.

## Operating rules

- Freeze the source and private gold before a release evaluation.
- Do not show gold labels or per-case failures to prompt authors.
- Record the package ID with every result.
- Create a new package after any transcript, metadata, tag, or label change.
- Do not treat file naming, hashes, or this split as security. Use normal private
  storage permissions for consented data and labels.
