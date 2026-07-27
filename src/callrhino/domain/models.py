from copy import deepcopy
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WarningCode(StrEnum):
    MISSING_OWNER = "MISSING_OWNER"
    MISSING_DEADLINE = "MISSING_DEADLINE"
    VAGUE_DEADLINE = "VAGUE_DEADLINE"
    INFERRED_OWNER = "INFERRED_OWNER"
    UNACCEPTED_ASSIGNMENT = "UNACCEPTED_ASSIGNMENT"
    POSSIBLE_SUGGESTION = "POSSIBLE_SUGGESTION"
    CONFLICTING_STATEMENTS = "CONFLICTING_STATEMENTS"
    UNCLEAR_SPEAKER = "UNCLEAR_SPEAKER"
    KNOWLEDGE_CONFLICT = "KNOWLEDGE_CONFLICT"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class DecisionStatus(StrEnum):
    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    DEFERRED = "deferred"
    REJECTED = "rejected"
    REVERSED = "reversed"


class CommitmentStatus(StrEnum):
    COMMITTED = "committed"
    CONDITIONAL = "conditional"
    REQUESTED = "requested"
    BLOCKED = "blocked"


class DecisionMakerBasis(StrEnum):
    EXPLICIT = "explicit"
    GROUP = "group"
    REVIEWER_CONFIRMED = "reviewer_confirmed"
    UNASSIGNED = "unassigned"


class OwnerBasis(StrEnum):
    SELF_COMMITMENT = "self_commitment"
    ASSIGNED_AND_ACCEPTED = "assigned_and_accepted"
    GROUP_COMMITMENT = "group_commitment"
    REVIEWER_CONFIRMED = "reviewer_confirmed"
    UNASSIGNED = "unassigned"


class TemporalPrecision(StrEnum):
    EXACT = "exact"
    RESOLVED_RELATIVE = "resolved_relative"
    VAGUE = "vague"
    ABSENT = "absent"


class EvidenceStrength(StrEnum):
    EXPLICIT = "explicit"
    STRONG_CONTEXT = "strong_context"
    AMBIGUOUS = "ambiguous"


class OpenQuestionStatus(StrEnum):
    OPEN = "open"
    DEFERRED = "deferred"


class RiskKind(StrEnum):
    RISK = "risk"
    BLOCKER = "blocker"
    DEPENDENCY = "dependency"


class MeetingContext(StrictModel):
    suggested_title: str | None
    meeting_date: date | None
    languages_detected: list[str]
    timezone: str
    output_language: str


class MeetingSummary(StrictModel):
    short: str = Field(min_length=1, max_length=1200)
    topics: list[str]


class Decision(StrictModel):
    text: str = Field(min_length=1, max_length=1000)
    status: DecisionStatus
    decision_maker_text: str | None
    decision_maker_basis: DecisionMakerBasis
    effective_date: date | None
    effective_date_text: str | None
    date_precision: TemporalPrecision
    evidence_strength: EvidenceStrength
    evidence_segment_ids: list[str] = Field(min_length=1)
    warnings: list[WarningCode]

    @model_validator(mode="after")
    def validate_attribution_and_date(self) -> "Decision":
        if self.decision_maker_basis == DecisionMakerBasis.UNASSIGNED:
            if self.decision_maker_text is not None:
                raise ValueError("unassigned decisions cannot have a decision maker")
        elif not self.decision_maker_text:
            raise ValueError("attributed decisions require a decision maker")
        _validate_temporal_fields(
            value=self.effective_date,
            source_text=self.effective_date_text,
            precision=self.date_precision,
            field_name="effective date",
        )
        return self


class ActionItem(StrictModel):
    task: str = Field(min_length=1, max_length=1000)
    commitment_status: CommitmentStatus
    owner_text: str | None
    owner_basis: OwnerBasis
    suggested_owner_text: str | None
    due_date: date | None
    due_text: str | None
    deadline_precision: TemporalPrecision
    priority: Priority
    evidence_strength: EvidenceStrength
    evidence_segment_ids: list[str] = Field(min_length=1)
    warnings: list[WarningCode]

    @model_validator(mode="after")
    def validate_owner_and_deadline(self) -> "ActionItem":
        warning_set = set(self.warnings)
        if self.owner_basis == OwnerBasis.UNASSIGNED:
            if self.owner_text is not None:
                raise ValueError("unassigned action items cannot have an owner")
            if WarningCode.MISSING_OWNER not in warning_set:
                raise ValueError("unassigned action items require MISSING_OWNER")
        elif not self.owner_text:
            raise ValueError("assigned action items require an owner")
        if self.suggested_owner_text and self.owner_basis != OwnerBasis.UNASSIGNED:
            raise ValueError("suggested owners are only valid when the item is unassigned")
        if (
            self.suggested_owner_text
            and WarningCode.UNACCEPTED_ASSIGNMENT not in warning_set
        ):
            raise ValueError("suggested owners require UNACCEPTED_ASSIGNMENT")
        _validate_temporal_fields(
            value=self.due_date,
            source_text=self.due_text,
            precision=self.deadline_precision,
            field_name="deadline",
        )
        if (
            self.deadline_precision == TemporalPrecision.VAGUE
            and WarningCode.VAGUE_DEADLINE not in warning_set
        ):
            raise ValueError("vague deadlines require VAGUE_DEADLINE")
        if (
            self.deadline_precision == TemporalPrecision.ABSENT
            and WarningCode.MISSING_DEADLINE not in warning_set
        ):
            raise ValueError("absent deadlines require MISSING_DEADLINE")
        if (
            self.evidence_strength == EvidenceStrength.AMBIGUOUS
            and WarningCode.LOW_CONFIDENCE not in warning_set
        ):
            raise ValueError("ambiguous action items require LOW_CONFIDENCE")
        return self


class OpenQuestion(StrictModel):
    text: str = Field(min_length=1, max_length=1000)
    status: OpenQuestionStatus
    evidence_strength: EvidenceStrength
    evidence_segment_ids: list[str] = Field(min_length=1)


class Risk(StrictModel):
    text: str = Field(min_length=1, max_length=1000)
    kind: RiskKind
    evidence_strength: EvidenceStrength
    evidence_segment_ids: list[str] = Field(min_length=1)


class ExtractionWarning(StrictModel):
    code: WarningCode
    message: str = Field(min_length=1, max_length=500)
    related_item_type: str | None
    related_item_index: int | None


class MeetingBrief(StrictModel):
    schema_version: Literal["2.0"]
    meeting: MeetingContext
    summary: MeetingSummary
    decisions: list[Decision]
    action_items: list[ActionItem]
    open_questions: list[OpenQuestion]
    risks: list[Risk]
    warnings: list[ExtractionWarning]

    @model_validator(mode="before")
    @classmethod
    def upgrade_legacy_v1(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "schema_version" in value:
            return value

        upgraded = deepcopy(value)
        upgraded["schema_version"] = "2.0"
        meeting = upgraded.get("meeting", {})
        meeting["meeting_date"] = meeting.pop("date_mentioned", None)
        meeting.setdefault("timezone", "Asia/Kolkata")
        meeting.setdefault("output_language", "English")

        for decision in upgraded.get("decisions", []):
            owner = decision.pop("owner_text", None)
            decision.pop("confidence", None)
            decision.update(
                {
                    "status": "confirmed",
                    "decision_maker_text": owner,
                    "decision_maker_basis": (
                        "reviewer_confirmed" if owner else "unassigned"
                    ),
                    "effective_date": None,
                    "effective_date_text": None,
                    "date_precision": "absent",
                    "evidence_strength": "strong_context",
                }
            )

        for action in upgraded.get("action_items", []):
            owner = action.get("owner_text")
            due_date = action.get("due_date")
            due_text = action.get("due_text")
            warnings = set(action.get("warnings", []))
            action.pop("confidence", None)
            if due_date and due_text:
                deadline_precision = "resolved_relative"
            elif due_date:
                deadline_precision = "exact"
            elif due_text:
                deadline_precision = "vague"
                warnings.add("VAGUE_DEADLINE")
            else:
                deadline_precision = "absent"
                warnings.add("MISSING_DEADLINE")
            if not owner:
                warnings.add("MISSING_OWNER")
            action.update(
                {
                    "commitment_status": "committed" if owner else "requested",
                    "owner_basis": "reviewer_confirmed" if owner else "unassigned",
                    "suggested_owner_text": None,
                    "deadline_precision": deadline_precision,
                    "evidence_strength": "strong_context",
                    "warnings": sorted(warnings),
                }
            )

        for question in upgraded.get("open_questions", []):
            question.pop("confidence", None)
            question.update(
                {
                    "status": "open",
                    "evidence_strength": "strong_context",
                }
            )

        for risk in upgraded.get("risks", []):
            risk.update(
                {
                    "kind": "risk",
                    "evidence_strength": "strong_context",
                }
            )
        return upgraded

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


class TranscriptSegment(StrictModel):
    id: str
    sequence_no: int = Field(ge=1)
    speaker_label: str | None
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    text: str = Field(min_length=1)


class PendingTranscript(StrictModel):
    series_name: str = Field(min_length=1)
    meeting_title: str = Field(min_length=1)
    meeting_date: date
    source_type: str = Field(min_length=1)
    transcript_text: str = Field(min_length=1)
    segments: list[TranscriptSegment] = Field(min_length=1)


class ReviewedTranscript(PendingTranscript):
    pass


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
