# CallRhino evaluation

This benchmark separates transcription, extraction, and end-to-end failures.
It is not a single headline score.

## Test matrix

| Layer | Primary data | Secondary data | Main metrics |
|---|---|---|---|
| STT | MUCS-Hinglish public audio | Gated Kathbath and LAHAJA when access is available | WER, CER, token precision/recall, English-term retention, repetition, real-time factor, cost |
| Candidate detection | CallRhino Indian stress cases | Kaggle synthetic snippets | Schema pass, per-label precision/recall/F1, ID completeness, cost |
| Canonical extraction | CallRhino Indian stress cases | QMSum and AMI in a later long-context suite | Decision/action precision and recall, owner, status, dates, evidence, forbidden facts, schema pass, repair rate, cost |
| End to end | MUCS-Hinglish negative control | Consented Indian meetings required | Gold-transcript versus STT-transcript extraction delta |

No public dataset in this suite contains all of these at once:

- real Indian multi-speaker meetings
- Hindi-English and regional code switching
- speaker diarization
- decisions and action items
- owners and deadlines
- evidence spans

The local Indian cases are synthetic regression tests. They do not establish
production accuracy. A consented real-meeting set is required before release.

## Prepare data

The Hugging Face preparation script uses the dataset viewer row API. It downloads
11 deterministic files instead of the full 10 GB MUCS-Hinglish dataset.

```bash
uv run python scripts/prepare_hf_stt_eval.py
uv run python scripts/prepare_kaggle_eval.py
```

The Kaggle script downloads the public ZIP directly and creates a balanced
90-row sample from its synthetic English subset.

## Free local STT baselines

```bash
uv sync --group eval

uv run python scripts/evaluate_stt.py \
  --model mlx-community/whisper-small-mlx-4bit \
  --language auto \
  --output evals/results/stt_mlx_whisper_small_4bit_auto.json

uv run python scripts/evaluate_stt.py \
  --model mlx-community/whisper-large-v3-turbo-q4 \
  --language hi \
  --output evals/results/stt_mlx_whisper_large_v3_turbo_q4_hi.json
```

The runner uses an embedded FFmpeg binary when Homebrew FFmpeg is unavailable.
Model files are downloaded once and reused from the Hugging Face cache.

## Capped Sarvam runs

Every provider runner requires a declared rupee cap.

```bash
uv run python scripts/evaluate_sarvam_stt.py \
  --mode codemix \
  --max-cost-inr 1 \
  --output evals/results/stt_sarvam_saaras_v3_codemix.json

uv run python scripts/evaluate_sarvam_extraction.py \
  --model sarvam-105b \
  --max-cost-inr 1.5 \
  --output evals/results/extraction_sarvam_105b.json

uv run python scripts/evaluate_candidate_classifier.py \
  --batch-size 10 \
  --max-cost-inr 0.5 \
  --output evals/results/candidate_classifier_sarvam_30b.json

uv run python scripts/evaluate_end_to_end_negative.py \
  --max-cost-inr 0.5
```

Audio cost uses Sarvam's per-second billing with each request rounded up to one
second. Extraction cost includes every repair attempt.

## Release gates

The MVP should not be described as validated until all gates pass:

| Gate | Required |
|---|---:|
| Schema pass rate | 100% |
| Decision precision and recall | at least 90% each |
| Action precision and recall | at least 90% each |
| Owner, status, deadline, and evidence accuracy | at least 95% each |
| Prompt-injection forbidden facts | 0 |
| STT degenerate repetition | 0% |
| Hinglish English-term retention | at least 90% |
| Positive end-to-end real meeting cases | required |
| Human review | at least 20 consented Indian meetings |

The current benchmark does not pass these release gates.
