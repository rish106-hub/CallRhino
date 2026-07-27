# CallRhino

CallRhino turns meeting transcripts into a reviewed record of decisions, action
items, owners, deadlines, open questions, and risks.

The product does not silently treat model output as fact. Every brief must be
reviewed before it enters the meeting-series register.

## Current scope

The first vertical slice includes:

- pasted and text-file transcripts
- speaker-aware transcript segmentation
- Sarvam Chat Completions with strict JSON Schema output
- evidence validation against stable transcript segment IDs
- one repair attempt for invalid model output
- an editable approval workflow
- Markdown and JSON exports
- a local SQLite meeting register
- a prepared Supabase schema with Row Level Security

Audio transcription and cross-meeting reconciliation are the next product
increments. The application boundaries for both are already separate from the
core extraction flow.

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
uv sync --all-groups
uv run streamlit run app.py
```

The local application stores approved meetings in `data/callrhino.db`.

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
│   ├── exports.py
│   ├── extraction.py
│   ├── prompts.py
│   └── sarvam.py
└── ui/
    ├── components.py
    └── styles.py
```

The domain package has no Streamlit, Sarvam, or database dependency. Provider
and persistence adapters can be changed without rewriting the extraction rules.

## Sarvam integration

CallRhino uses the documented Chat Completions endpoint:

```text
POST https://api.sarvam.ai/v1/chat/completions
```

The request sets:

- model: `sarvam-30b`
- temperature: `0`
- reasoning effort: disabled
- one completion
- explicit maximum output tokens
- `response_format.type`: `json_schema`
- `strict`: `true`

The returned `message.content` is parsed as JSON and then validated again with
Pydantic. Evidence IDs are checked against the submitted transcript segments.

References:

- [Chat Completions API](https://docs.sarvam.ai/api-reference/chat/chat-completions)
- [Structured output guide](https://docs.sarvam.ai/api/api-guides-tutorials/chat-completion/overview#structured-outputs-json)
- [Speech-to-text API selection](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/which-api-to-use)

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
- Delete raw audio after transcription when audio support is added.
