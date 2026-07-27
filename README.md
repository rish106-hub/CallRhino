# CallRhino

CallRhino turns meeting transcripts into a reviewed record of decisions, action
items, owners, deadlines, open questions, and risks.

The product does not silently treat model output as fact. Every brief must be
reviewed before it enters the meeting-series register. Transcripts are also
reviewed before extraction starts.

## Current scope

The first vertical slice includes:

- pasted, text-file, and long-form audio inputs
- Sarvam Saaras v3 code-mix transcription with speaker diarization
- an editable transcript review stage before extraction
- deterministic speaker renaming and mapping on parsed transcript segments
- Sarvam Chat Completions with strict JSON Schema output
- evidence validation against stable transcript segment IDs
- explicit decision, commitment, ownership, and deadline provenance
- one repair attempt for invalid model output
- an editable approval workflow
- Markdown and JSON exports
- a local SQLite meeting register
- a prepared Supabase schema with Row Level Security

Raw audio is held only in a local temporary folder while Sarvam processes it.
The application persists the transcript, not the audio file. Cross-meeting
reconciliation remains a later increment.

## Staged review flow

1. Paste a transcript, upload a text file, or upload meeting audio.
2. CallRhino creates a pending transcript. It does not start brief extraction.
3. Edit the transcript and review the detected speaker labels.
4. Rename speakers or map several labels to the same person.
5. Confirm the transcript to start `MeetingExtractor`.
6. Review the extracted brief before saving it to the register.

Speaker mapping changes only the parsed speaker label. It preserves segment IDs,
order, timestamps, and spoken text. For audio uploads, the raw file is still
deleted with the local temporary folder immediately after transcription.

## Run locally

Requirements:

- Python 3.12
- `uv`
- a Sarvam API key
- an OpenAI API key only if the controlled fallback is enabled

```bash
cp .env.example .env
```

Add the key to `.env`:

```text
SARVAM_API_KEY=your_key_here
OPENAI_API_KEY=your_optional_key_here
```

`OPENAI_FALLBACK_ENABLED` remains `false` by default. Saving a key does not make
paid calls. The planned router must enforce the `$1.50` project hard limit
before this flag is enabled.

Install and start:

```bash
uv sync
uv run streamlit run app.py
```

The local application stores approved meetings in `data/callrhino.db`.

The accuracy target and required validation set are defined in
[`docs/accuracy-target.md`](docs/accuracy-target.md). The current synthetic
benchmark is not evidence of 99.5% production accuracy.

## Verify

```bash
uv run ruff check .
uv run pytest
```

## Project structure

```text
src/callrhino/
├── config.py
├── domain/
│   ├── models.py
│   └── transcript.py
├── repositories/
│   ├── base.py
│   └── sqlite.py
├── services/
│   ├── candidates.py
│   ├── compact_prompts.py
│   ├── compiler.py
│   ├── deduplication.py
│   ├── evidence.py
│   ├── exports.py
│   ├── extraction.py
│   ├── prompts.py
│   ├── sarvam.py
│   └── transcript_review.py
└── ui/
    ├── components.py
    └── styles.py
```

The domain package has no Streamlit, Sarvam, or database dependency. Provider
and persistence adapters can be changed without rewriting the extraction rules.

## Extraction strategies

The application uses the full canonical extractor by default. An experimental
deterministic candidate gate can submit relevant segments plus surrounding
context for long transcripts. The gate uses no model call and falls back to the
full transcript when it cannot reduce the input safely. It remains disabled by
default until it passes an independent long-meeting holdout. Enable it only for
testing with `CALLRHINO_CANDIDATE_GATING_ENABLED=true`.

The compact extractor remains available for controlled benchmarks. It asks the
model for a smaller fact list and compiles the canonical record locally. It
reduced the combined prompt and schema payload by 71.3% and lowered observed
cost, but it did not meet the accuracy gates. It is not used by the application.
See [`docs/compact-extraction-experiment.md`](docs/compact-extraction-experiment.md).

## Sarvam integration

CallRhino uses the documented Chat Completions endpoint:

```text
POST https://api.sarvam.ai/v1/chat/completions
```

The request sets:

- model: `sarvam-105b`
- temperature: `0`
- reasoning effort: disabled
- one completion
- explicit maximum output tokens
- `response_format.type`: `json_schema`
- `strict`: `true`

The canonical extraction contract is documented in
[`docs/extraction-contract-v2.md`](docs/extraction-contract-v2.md). Audience
views are rendered from the approved canonical record and do not run separate
fact extraction prompts.

The returned `message.content` is parsed as JSON and then validated again with
Pydantic. Evidence IDs are checked against the submitted transcript segments.
Evidence context, duplicate state items, mechanical warning fields, and supported
date phrases are normalized locally before validation. This avoids paying for
repairs that do not need model judgment and prevents unsupported dates or
duplicated commitments from entering the review draft.

Long-form audio uses Sarvam's Batch Speech-to-Text API with `saaras:v3`,
`codemix`, timestamps, and speaker diarization. The batch path supports meetings
up to two hours according to Sarvam's documentation.

The 105B model is intentional. In the July 2026 benchmark, Sarvam 30B exhausted
the 4,096-token output limit on tiny meetings and returned truncated JSON.
Sarvam 105B passed all eight schemas in one run, then passed seven of eight in a
repeat because one response hit the same output limit. Observed extraction cost
was roughly ₹0.013 to ₹0.021 per short test meeting. The variance is why every
brief remains a reviewable draft.

References:

- [Chat Completions API](https://docs.sarvam.ai/api-reference/chat/chat-completions)
- [Structured output guide](https://docs.sarvam.ai/api/api-guides-tutorials/chat-completion/overview#structured-outputs-json)
- [Speech-to-text API selection](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/which-api-to-use)
- [Batch Speech-to-Text API](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/batch-api)

## Evaluation

The benchmark is separate from the product runtime. It includes:

- public MUCS-Hinglish speech samples from Hugging Face
- a secondary synthetic Kaggle action/decision classifier set
- eight Indian meeting edge cases for deterministic extraction regression
- local MLX Whisper baselines
- capped Sarvam STT and extraction runs
- a public-audio end-to-end negative control

Run the free checks:

```bash
uv sync --group eval
uv run ruff check .
uv run pytest
uv run python scripts/prepare_hf_stt_eval.py
uv run python scripts/prepare_kaggle_eval.py
```

Provider benchmark scripts require an explicit `--max-cost-inr` argument and
refuse calls above that ceiling. See [`evals/README.md`](evals/README.md) and the
current [benchmark report](docs/benchmark-results-2026-07-27.md). The data split,
review, and 99.5% claim rules are defined in
[`docs/evaluation-protocol.md`](docs/evaluation-protocol.md).

## Supabase

The migration in `supabase/migrations` creates the production-oriented schema,
explicit Data API grants, and workspace-scoped RLS policies.

Supabase is not required for local testing. SQLite is the active backend.

When team accounts and cloud persistence are added, create a dedicated
CallRhino project in the [Supabase dashboard](https://supabase.com/dashboard/new).
Open the project's Connect panel or API settings and copy:

```text
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_your_key
```

Apply it only after linking a Supabase project:

```bash
supabase link --project-ref your_project_ref
supabase db push
```

Do not put a Supabase secret or service-role key in browser code. The public app
will use a publishable key plus an authenticated user session.

## Product rules

- Never invent an owner or deadline.
- Keep vague dates as the original phrase.
- Cite evidence for every extracted item.
- Treat model output as a draft.
- Compare meetings only inside one recurring series by default.
- Delete raw audio immediately after transcription.
