from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from callrhino.domain.models import StrictModel, TranscriptSegment
from callrhino.evaluation.models import ExtractionCase


class ConsentStatus(StrEnum):
    GRANTED = "granted"
    WITHDRAWN = "withdrawn"


class PiiReviewStatus(StrEnum):
    PENDING = "pending"
    CLEAR = "clear"
    REDACTED = "redacted"


class RedactionStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    COMPLETED = "completed"


class SourceMeeting(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
    title: str = Field(min_length=1, max_length=300)
    meeting_date: date
    meeting_type: str = Field(default="internal_project", min_length=1, max_length=100)
    tags: list[str] = Field(default_factory=list)
    consent_status: ConsentStatus
    consent_reference: str = Field(min_length=1, max_length=500)
    pii_review_status: PiiReviewStatus
    redaction_status: RedactionStatus
    reviewed_segments: list[TranscriptSegment] = Field(min_length=1)
    provenance: Literal["consented"] = "consented"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("title", "meeting_type", "consent_reference")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if len({value.casefold() for value in normalized}) != len(normalized):
            raise ValueError("meeting tags must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_reviewed_segments(self) -> "SourceMeeting":
        ids = [segment.id for segment in self.reviewed_segments]
        sequence_numbers = [segment.sequence_no for segment in self.reviewed_segments]
        if len(set(ids)) != len(ids):
            raise ValueError("reviewed segment IDs must be unique")
        if sequence_numbers != list(range(1, len(self.reviewed_segments) + 1)):
            raise ValueError("reviewed segments must be ordered with contiguous sequence numbers")
        expected_ids = [
            f"seg_{sequence_no:04d}" for sequence_no in range(1, len(self.reviewed_segments) + 1)
        ]
        if ids != expected_ids:
            raise ValueError("reviewed segment IDs must match their canonical sequence IDs")
        if (
            self.pii_review_status == PiiReviewStatus.CLEAR
            and self.redaction_status != RedactionStatus.NOT_REQUIRED
        ):
            raise ValueError("PII-clear meetings must mark redaction as not required")
        if (
            self.pii_review_status == PiiReviewStatus.REDACTED
            and self.redaction_status != RedactionStatus.COMPLETED
        ):
            raise ValueError("redacted meetings must have completed redaction")
        return self


class AnnotatedDecision(StrictModel):
    item_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
    text: str = Field(min_length=1, max_length=1000)
    status: str = Field(min_length=1, max_length=100)
    decision_maker_text: str | None = Field(default=None, max_length=300)
    effective_date: date | None = None
    effective_date_text: str | None = Field(default=None, max_length=300)
    date_precision: str = Field(min_length=1, max_length=100)
    evidence_segment_ids: list[str] = Field(min_length=1)

    @field_validator("evidence_segment_ids")
    @classmethod
    def evidence_ids_are_unique(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("evidence segment IDs must be unique")
        return values


class AnnotatedAction(StrictModel):
    item_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
    task: str = Field(min_length=1, max_length=1000)
    commitment_status: str = Field(min_length=1, max_length=100)
    owner_text: str | None = Field(default=None, max_length=300)
    suggested_owner_text: str | None = Field(default=None, max_length=300)
    due_date: date | None = None
    due_text: str | None = Field(default=None, max_length=300)
    deadline_precision: str = Field(min_length=1, max_length=100)
    evidence_segment_ids: list[str] = Field(min_length=1)

    @field_validator("evidence_segment_ids")
    @classmethod
    def evidence_ids_are_unique(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("evidence segment IDs must be unique")
        return values


class ReviewerSubmission(StrictModel):
    reviewer_id: str = Field(min_length=1, max_length=200)
    decisions: list[AnnotatedDecision] = Field(default_factory=list)
    actions: list[AnnotatedAction] = Field(default_factory=list)
    forbidden_facts: list[str] = Field(default_factory=list)
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("reviewer_id")
    @classmethod
    def normalize_reviewer_id(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def item_ids_are_unique(self) -> "ReviewerSubmission":
        ids = [item.item_id for item in self.decisions]
        ids.extend(item.item_id for item in self.actions)
        if len(set(ids)) != len(ids):
            raise ValueError("item IDs must be unique within a reviewer submission")
        return self


class FieldDisagreement(StrictModel):
    item_id: str
    item_type: Literal["decision", "action", "unknown"]
    field: str
    reviewer_values: dict[str, Any]


class Adjudication(StrictModel):
    adjudicator_id: str = Field(min_length=1, max_length=200)
    extraction_case: ExtractionCase
    adjudicated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("adjudicator_id")
    @classmethod
    def normalize_adjudicator_id(cls, value: str) -> str:
        return value.strip()


class AnnotationRecord(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    source: SourceMeeting
    submissions: list[ReviewerSubmission] = Field(default_factory=list, max_length=2)
    adjudication: Adjudication | None = None

    @model_validator(mode="after")
    def reviewer_identities_are_unique(self) -> "AnnotationRecord":
        normalized = [submission.reviewer_id.casefold() for submission in self.submissions]
        if len(set(normalized)) != len(normalized):
            raise ValueError("reviewer identities must be unique")
        return self
