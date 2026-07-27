from dataclasses import dataclass
from datetime import date
from typing import Protocol

from pydantic import ValidationError

from callrhino.domain.models import (
    DecisionMakerBasis,
    MeetingBrief,
    OwnerBasis,
    TranscriptSegment,
    WarningCode,
)
from callrhino.services.normalization import normalize_brief_payload
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

    def __init__(self, message: str, usage: TokenUsage | None = None) -> None:
        super().__init__(message)
        self.usage = usage or TokenUsage()


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
        meeting_type: str = "internal_project",
        timezone: str = "Asia/Kolkata",
        output_language: str = "English",
        workspace_roster: dict[str, str] | None = None,
        workspace_glossary: dict[str, str] | None = None,
    ) -> ExtractionResult:
        messages = build_extraction_messages(
            meeting_date=meeting_date,
            series_name=series_name,
            meeting_title=meeting_title,
            segments=segments,
            meeting_type=meeting_type,
            timezone=timezone,
            output_language=output_language,
            workspace_roster=workspace_roster,
            workspace_glossary=workspace_glossary,
        )
        schema = MeetingBrief.model_json_schema()
        valid_ids = {segment.id for segment in segments}

        result = self._generator.generate_structured(
            messages=messages,
            schema_name="meeting_brief",
            schema=schema,
        )
        total_usage = result.usage

        for attempt in range(self._max_repairs + 1):
            try:
                normalized_data = normalize_brief_payload(
                    result.data,
                    meeting_date=meeting_date,
                    timezone=timezone,
                    output_language=output_language,
                    segments=segments,
                )
                brief = MeetingBrief.model_validate(normalized_data)
                _validate_evidence(brief, valid_ids)
                _validate_extraction_provenance(brief)
                _validate_meeting_context(
                    brief,
                    meeting_date=meeting_date,
                    timezone=timezone,
                    output_language=output_language,
                )
                return ExtractionResult(
                    brief=brief,
                    usage=total_usage,
                    model=result.model,
                    request_id=result.request_id,
                    repaired=attempt > 0,
                )
            except (ValidationError, BriefValidationError) as exc:
                if attempt >= self._max_repairs:
                    raise BriefValidationError(
                        f"Meeting brief failed validation after {attempt + 1} attempts: {exc}",
                        usage=total_usage,
                    ) from exc
                messages = build_repair_messages(messages, result.content, str(exc))
                result = self._generator.generate_structured(
                    messages=messages,
                    schema_name="meeting_brief",
                    schema=schema,
                )
                total_usage = _add_usage(total_usage, result.usage)

        raise AssertionError("unreachable")


def _add_usage(left: TokenUsage, right: TokenUsage) -> TokenUsage:
    return TokenUsage(
        prompt_tokens=left.prompt_tokens + right.prompt_tokens,
        completion_tokens=left.completion_tokens + right.completion_tokens,
        total_tokens=left.total_tokens + right.total_tokens,
    )


def _validate_evidence(brief: MeetingBrief, valid_ids: set[str]) -> None:
    unknown = brief.all_evidence_ids() - valid_ids
    if unknown:
        invalid = ", ".join(sorted(unknown))
        raise BriefValidationError(f"Unknown evidence segment IDs: {invalid}")


def _validate_extraction_provenance(brief: MeetingBrief) -> None:
    if any(
        item.decision_maker_basis == DecisionMakerBasis.REVIEWER_CONFIRMED
        for item in brief.decisions
    ):
        raise BriefValidationError(
            "reviewer_confirmed decision attribution cannot be generated by a model"
        )
    if any(item.owner_basis == OwnerBasis.REVIEWER_CONFIRMED for item in brief.action_items):
        raise BriefValidationError(
            "reviewer_confirmed action ownership cannot be generated by a model"
        )
    if any(
        WarningCode.INFERRED_OWNER in item.warnings
        for item in (*brief.decisions, *brief.action_items)
    ):
        raise BriefValidationError("INFERRED_OWNER is legacy-only and cannot be generated")
    invalid_attributions = {"i", "we", "us", "our", "team"}
    if any(
        item.decision_maker_text
        and item.decision_maker_text.strip().casefold() in invalid_attributions
        for item in brief.decisions
    ):
        raise BriefValidationError(
            "decision_maker_text must name a speaker or grounded group, not a pronoun"
        )
    if any(
        item.owner_text and item.owner_text.strip().casefold() in invalid_attributions
        for item in brief.action_items
    ):
        raise BriefValidationError(
            "owner_text must name a speaker or grounded group, not a pronoun"
        )


def _validate_meeting_context(
    brief: MeetingBrief,
    *,
    meeting_date: date,
    timezone: str,
    output_language: str,
) -> None:
    if brief.meeting.meeting_date != meeting_date:
        raise BriefValidationError("meeting_date must exactly match the supplied meeting date")
    if brief.meeting.timezone != timezone:
        raise BriefValidationError("timezone must exactly match the supplied workspace timezone")
    if brief.meeting.output_language != output_language:
        raise BriefValidationError(
            "output_language must exactly match the supplied output language"
        )
