from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WarningCode(StrEnum):
    MISSING_OWNER = "MISSING_OWNER"
    MISSING_DEADLINE = "MISSING_DEADLINE"
    VAGUE_DEADLINE = "VAGUE_DEADLINE"
    INFERRED_OWNER = "INFERRED_OWNER"
    POSSIBLE_SUGGESTION = "POSSIBLE_SUGGESTION"
    CONFLICTING_STATEMENTS = "CONFLICTING_STATEMENTS"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class MeetingContext(StrictModel):
    suggested_title: str | None
    date_mentioned: date | None
    languages_detected: list[str]


class MeetingSummary(StrictModel):
    short: str = Field(min_length=1, max_length=1200)
    topics: list[str]


class Decision(StrictModel):
    text: str = Field(min_length=1, max_length=1000)
    owner_text: str | None
    confidence: float = Field(ge=0, le=1)
    evidence_segment_ids: list[str] = Field(min_length=1)
    warnings: list[WarningCode]


class ActionItem(StrictModel):
    task: str = Field(min_length=1, max_length=1000)
    owner_text: str | None
    due_date: date | None
    due_text: str | None
    priority: Priority
    confidence: float = Field(ge=0, le=1)
    evidence_segment_ids: list[str] = Field(min_length=1)
    warnings: list[WarningCode]


class OpenQuestion(StrictModel):
    text: str = Field(min_length=1, max_length=1000)
    confidence: float = Field(ge=0, le=1)
    evidence_segment_ids: list[str] = Field(min_length=1)


class Risk(StrictModel):
    text: str = Field(min_length=1, max_length=1000)
    evidence_segment_ids: list[str] = Field(min_length=1)


class ExtractionWarning(StrictModel):
    code: WarningCode
    message: str = Field(min_length=1, max_length=500)
    related_item_type: str | None
    related_item_index: int | None


class MeetingBrief(StrictModel):
    meeting: MeetingContext
    summary: MeetingSummary
    decisions: list[Decision]
    action_items: list[ActionItem]
    open_questions: list[OpenQuestion]
    risks: list[Risk]
    warnings: list[ExtractionWarning]

    @field_validator("warnings")
    @classmethod
    def warning_indexes_are_non_negative(
        cls,
        warnings: list[ExtractionWarning],
    ) -> list[ExtractionWarning]:
        for warning in warnings:
            if warning.related_item_index is not None and warning.related_item_index < 0:
                raise ValueError("warning indexes cannot be negative")
        return warnings

    def all_evidence_ids(self) -> set[str]:
        groups = [
            *(item.evidence_segment_ids for item in self.decisions),
            *(item.evidence_segment_ids for item in self.action_items),
            *(item.evidence_segment_ids for item in self.open_questions),
            *(item.evidence_segment_ids for item in self.risks),
        ]
        return {segment_id for group in groups for segment_id in group}

    def to_json_schema(self) -> dict[str, Any]:
        return self.model_json_schema()


class TranscriptSegment(StrictModel):
    id: str
    sequence_no: int = Field(ge=1)
    speaker_label: str | None
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    text: str = Field(min_length=1)


class ApprovedMeeting(StrictModel):
    id: str
    series_name: str
    title: str
    meeting_date: date
    source_type: str
    transcript_text: str
    segments: list[TranscriptSegment]
    brief: MeetingBrief
    approved_at: datetime


class RegisterSnapshot(StrictModel):
    meetings: list[ApprovedMeeting]

