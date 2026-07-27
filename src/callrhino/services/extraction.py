from dataclasses import dataclass
from datetime import date
from typing import Protocol

from pydantic import ValidationError

from callrhino.domain.models import MeetingBrief, TranscriptSegment
from callrhino.services.prompts import build_extraction_messages, build_repair_messages
from callrhino.services.sarvam import StructuredChatResult, TokenUsage


class StructuredGenerator(Protocol):
    def generate_structured(
        self,
        *,
        messages: list[dict[str, str]],
        schema_name: str,
        schema: dict,
    ) -> StructuredChatResult: ...


class BriefValidationError(ValueError):
    """Raised when structured output fails application validation."""


@dataclass(frozen=True)
class ExtractionResult:
    brief: MeetingBrief
    usage: TokenUsage
    model: str
    request_id: str | None
    repaired: bool


class MeetingExtractor:
    def __init__(self, generator: StructuredGenerator, max_repairs: int = 1) -> None:
        self._generator = generator
        self._max_repairs = max_repairs

    def extract(
        self,
        *,
        meeting_date: date,
        series_name: str,
        meeting_title: str,
        segments: list[TranscriptSegment],
    ) -> ExtractionResult:
        messages = build_extraction_messages(
            meeting_date=meeting_date,
            series_name=series_name,
            meeting_title=meeting_title,
            segments=segments,
        )
        schema = MeetingBrief.model_json_schema()
        valid_ids = {segment.id for segment in segments}

        result = self._generator.generate_structured(
            messages=messages,
            schema_name="meeting_brief",
            schema=schema,
        )

        for attempt in range(self._max_repairs + 1):
            try:
                brief = MeetingBrief.model_validate(result.data)
                _validate_evidence(brief, valid_ids)
                return ExtractionResult(
                    brief=brief,
                    usage=result.usage,
                    model=result.model,
                    request_id=result.request_id,
                    repaired=attempt > 0,
                )
            except (ValidationError, BriefValidationError) as exc:
                if attempt >= self._max_repairs:
                    raise BriefValidationError(
                        f"Meeting brief failed validation after {attempt + 1} attempts: {exc}"
                    ) from exc
                messages = build_repair_messages(messages, result.content, str(exc))
                result = self._generator.generate_structured(
                    messages=messages,
                    schema_name="meeting_brief",
                    schema=schema,
                )

        raise AssertionError("unreachable")


def _validate_evidence(brief: MeetingBrief, valid_ids: set[str]) -> None:
    unknown = brief.all_evidence_ids() - valid_ids
    if unknown:
        invalid = ", ".join(sorted(unknown))
        raise BriefValidationError(f"Unknown evidence segment IDs: {invalid}")

