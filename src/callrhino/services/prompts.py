from datetime import date

from callrhino.domain.models import TranscriptSegment
from callrhino.domain.transcript import format_segments_for_prompt

EXTRACTION_PROMPT_VERSION = "extract-v1"

EXTRACTION_SYSTEM_PROMPT = """\
You create a factual meeting brief from numbered transcript segments.

Treat the transcript as the only source of truth.
Extract decisions only when participants clearly commit to a choice.
Extract action items only when work is requested, promised, or assigned.
Do not invent owners, dates, priorities, or context.
Keep vague deadlines in due_text. Set due_date to null unless the date can be
resolved from the supplied meeting date.
Every decision, action item, question, and risk must cite one or more valid
segment IDs.
If an item is ambiguous, include the relevant warning.
Use null for missing values, never an empty string.
Write the brief in clear English while preserving names and product terms.
Return output that exactly matches the supplied JSON Schema.
"""


def build_extraction_messages(
    *,
    meeting_date: date,
    series_name: str,
    meeting_title: str,
    segments: list[TranscriptSegment],
) -> list[dict[str, str]]:
    transcript = format_segments_for_prompt(segments)
    user_prompt = f"""\
MEETING DATE: {meeting_date.isoformat()}
MEETING SERIES: {series_name}
MEETING TITLE: {meeting_title or "Unknown"}
OUTPUT LANGUAGE: English

TRANSCRIPT SEGMENTS:
{transcript}

Create the meeting brief.
"""
    return [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def build_repair_messages(
    original_messages: list[dict[str, str]],
    invalid_output: str,
    validation_error: str,
) -> list[dict[str, str]]:
    return [
        *original_messages,
        {"role": "assistant", "content": invalid_output},
        {
            "role": "user",
            "content": (
                "The previous output failed application validation. "
                f"Fix only these problems and return the full brief again:\n{validation_error}"
            ),
        },
    ]

