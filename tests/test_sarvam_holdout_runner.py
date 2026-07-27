import json

import pytest

from callrhino.domain.models import MeetingBrief
from callrhino.domain.transcript import segment_transcript
from callrhino.evaluation.holdout import PublicHoldoutCase
from callrhino.evaluation.provider_costs import (
    HOLDOUT_MAX_ATTEMPTS,
    HOLDOUT_MAX_OUTPUT_TOKENS,
    sarvam_holdout_cost_ceiling,
)
from callrhino.services.prompts import build_extraction_messages


def _case(transcript: str) -> PublicHoldoutCase:
    return PublicHoldoutCase(
        id="cost_case",
        title="Cost ceiling",
        meeting_date="2026-07-27",
        meeting_type="internal_project",
        transcript=transcript,
        tags=["hinglish"],
        provenance="consented",
        transcript_fingerprint="a" * 64,
        input_fingerprint="b" * 64,
    )


def test_cost_ceiling_counts_utf8_bytes_and_two_full_outputs() -> None:
    case = _case("Aditi: हाँ, launch Friday ko karenge.")
    pricing = (4.0, 16.0)
    retry_input_ceiling = 64_000
    messages = build_extraction_messages(
        meeting_date=case.meeting_date,
        series_name="Blind holdout",
        meeting_title=case.title,
        meeting_type=case.meeting_type,
        segments=segment_transcript(case.transcript),
    )
    request_bytes = len(
        json.dumps(
            {
                "messages": messages,
                "response_schema": MeetingBrief.model_json_schema(),
            },
            ensure_ascii=False,
        ).encode("utf-8")
    )

    expected = (
        (request_bytes + retry_input_ceiling) * pricing[0]
        + HOLDOUT_MAX_OUTPUT_TOKENS * HOLDOUT_MAX_ATTEMPTS * pricing[1]
    ) / 1_000_000

    assert sarvam_holdout_cost_ceiling(
        case,
        pricing,
        retry_input_token_ceiling=retry_input_ceiling,
    ) == pytest.approx(expected)


def test_indic_text_costs_more_than_same_character_count_ascii() -> None:
    ascii_case = _case("Aditi: yes yes yes yes")
    indic_case = _case("Aditi: हाँ हाँ हाँ हाँ")

    assert sarvam_holdout_cost_ceiling(
        indic_case,
        (4.0, 16.0),
    ) > sarvam_holdout_cost_ceiling(
        ascii_case,
        (4.0, 16.0),
    )
