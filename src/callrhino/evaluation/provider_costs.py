import json

from callrhino.domain.models import MeetingBrief
from callrhino.domain.transcript import segment_transcript
from callrhino.evaluation.holdout import PublicHoldoutCase
from callrhino.services.prompts import build_extraction_messages

SARVAM_MODEL_PRICING_INR_PER_MILLION = {
    "sarvam-30b": (2.5, 10.0),
    "sarvam-105b": (4.0, 16.0),
}
HOLDOUT_MAX_OUTPUT_TOKENS = 4096
HOLDOUT_MAX_ATTEMPTS = 2
SARVAM_MODEL_CONTEXT_TOKENS = {
    "sarvam-30b": 64_000,
    "sarvam-105b": 128_000,
}


def sarvam_holdout_cost_ceiling(
    case: PublicHoldoutCase,
    pricing: tuple[float, float],
    *,
    retry_input_token_ceiling: int = 128_000,
) -> float:
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
    # Byte fallback tokenizers cannot emit more tokens than input bytes. This is
    # intentionally much stricter than the unsafe four-characters-per-token rule.
    input_token_ceiling = request_bytes
    input_price, output_price = pricing
    return (
        (input_token_ceiling + retry_input_token_ceiling)
        * input_price
        / 1_000_000
        + HOLDOUT_MAX_OUTPUT_TOKENS
        * HOLDOUT_MAX_ATTEMPTS
        * output_price
        / 1_000_000
    )


def sarvam_actual_cost(
    prompt_tokens: int,
    completion_tokens: int,
    pricing: tuple[float, float],
) -> float:
    input_price, output_price = pricing
    return (
        prompt_tokens * input_price + completion_tokens * output_price
    ) / 1_000_000
