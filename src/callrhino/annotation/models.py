from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from callrhino.domain.models import (
    CommitmentStatus,
    DecisionStatus,
    StrictModel,
    TemporalPrecision,
    TranscriptSegment,
)
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

    @field_validator("title", "meeting_type", "consent_reference", mode="before")
    @classmethod
    def strip_required_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

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
    status: DecisionStatus
    decision_maker_text: str | None = Field(default=None, max_length=300)
    effective_date: date | None = None
    effective_date_text: str | None = Field(default=None, max_length=300)
    date_precision: TemporalPrecision
    evidence_segment_ids: list[str] = Field(min_length=1)

    @field_validator("evidence_segment_ids")
    @classmethod
    def evidence_ids_are_unique(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("evidence segment IDs must be unique")
        return values

    @model_validator(mode="after")
    def temporal_fields_are_consistent(self) -> "AnnotatedDecision":
        _validate_temporal_fields(
            value=self.effective_date,
            source_text=self.effective_date_text,
            precision=self.date_precision,
            field_name="effective date",
        )
        return self


class AnnotatedAction(StrictModel):
    item_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
    task: str = Field(min_length=1, max_length=1000)
    commitment_status: CommitmentStatus
    owner_text: str | None = Field(default=None, max_length=300)
    suggested_owner_text: str | None = Field(default=None, max_length=300)
    due_date: date | None = None
    due_text: str | None = Field(default=None, max_length=300)
    deadline_precision: TemporalPrecision
    evidence_segment_ids: list[str] = Field(min_length=1)

    @field_validator("evidence_segment_ids")
    @classmethod
    def evidence_ids_are_unique(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("evidence segment IDs must be unique")
        return values

    @model_validator(mode="after")
    def temporal_fields_are_consistent(self) -> "AnnotatedAction":
        _validate_temporal_fields(
            value=self.due_date,
            source_text=self.due_text,
            precision=self.deadline_precision,
            field_name="deadline",
        )
        return self


class ReviewerSubmission(StrictModel):
    reviewer_id: str = Field(min_length=1, max_length=200)
    decisions: list[AnnotatedDecision] = Field(default_factory=list)
    actions: list[AnnotatedAction] = Field(default_factory=list)
    forbidden_facts: list[str] = Field(default_factory=list)
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("reviewer_id", mode="before")
    @classmethod
    def normalize_reviewer_id(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("forbidden_facts")
    @classmethod
    def normalize_forbidden_fact_list(cls, values: list[str]) -> list[str]:
        return normalize_forbidden_facts(values)

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

    @field_validator("adjudicator_id", mode="before")
    @classmethod
    def normalize_adjudicator_id(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


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


def normalize_forbidden_facts(values: list[str]) -> list[str]:
    normalized = []
    seen = set()
    for value in values:
        cleaned = value.strip()
        key = cleaned.casefold()
        if not cleaned or key in seen:
            continue
        normalized.append(cleaned)
        seen.add(key)
    return normalized


def _validate_temporal_fields(
    *,
    value: date | None,
    source_text: str | None,
    precision: TemporalPrecision,
    field_name: str,
) -> None:
    if precision in {TemporalPrecision.EXACT, TemporalPrecision.RESOLVED_RELATIVE}:
        if value is None:
            raise ValueError(f"{field_name} precision requires a concrete date")
    elif precision == TemporalPrecision.VAGUE:
        if not source_text or value is not None:
            raise ValueError(f"vague {field_name} requires source text and no date")
    elif value is not None or source_text is not None:
        raise ValueError(f"absent {field_name} cannot contain a date or source text")
