import re
from typing import Any, Literal

from callrhino.annotation.models import (
    Adjudication,
    AnnotatedAction,
    AnnotatedDecision,
    AnnotationRecord,
    ConsentStatus,
    FieldDisagreement,
    PiiReviewStatus,
    RedactionStatus,
    ReviewerSubmission,
    SourceMeeting,
    normalize_forbidden_facts,
)
from callrhino.annotation.repository import JsonAnnotationRepository
from callrhino.evaluation.models import (
    ExpectedAction,
    ExpectedDecision,
    ExtractionCase,
    ExtractionCaseManifest,
)


class AnnotationService:
    def __init__(self, repository: JsonAnnotationRepository) -> None:
        self._repository = repository

    def register_meeting(self, source: SourceMeeting) -> AnnotationRecord:
        self._ensure_annotation_allowed(source)
        return self._repository.create(source)

    def submit_review(
        self,
        meeting_id: str,
        submission: ReviewerSubmission,
    ) -> AnnotationRecord:
        record = self._repository.get(meeting_id)
        self._ensure_annotation_allowed(record.source)
        self._validate_evidence(
            record.source,
            [*submission.decisions, *submission.actions],
        )
        return self._repository.add_submission(meeting_id, submission)

    def disagreements(self, meeting_id: str) -> list[FieldDisagreement]:
        record = self._repository.get(meeting_id)
        if len(record.submissions) != 2:
            raise ValueError("two reviewer submissions are required")
        return detect_disagreements(*record.submissions)

    def adjudicate(
        self,
        meeting_id: str,
        *,
        adjudicator_id: str,
        decisions: list[AnnotatedDecision],
        actions: list[AnnotatedAction],
        forbidden_facts: list[str] | None = None,
    ) -> AnnotationRecord:
        record = self._repository.get(meeting_id)
        self._ensure_annotation_allowed(record.source)
        if len(record.submissions) != 2:
            raise ValueError("two reviewer submissions are required before adjudication")
        self._validate_unique_item_ids(decisions, actions)
        self._validate_evidence(record.source, [*decisions, *actions])

        source = record.source
        extraction_case = ExtractionCase(
            id=source.id,
            title=source.title,
            meeting_date=source.meeting_date,
            meeting_type=source.meeting_type,
            transcript=_render_reviewed_transcript(source),
            tags=source.tags,
            provenance="consented",
            expected_decisions=[
                ExpectedDecision.model_validate(
                    decision.model_dump(exclude={"item_id"})
                )
                for decision in decisions
            ],
            expected_actions=[
                ExpectedAction.model_validate(action.model_dump(exclude={"item_id"}))
                for action in actions
            ],
            forbidden_facts=normalize_forbidden_facts(forbidden_facts or []),
        )
        return self._repository.set_adjudication(
            meeting_id,
            Adjudication(
                adjudicator_id=adjudicator_id,
                extraction_case=extraction_case,
            ),
        )

    def get(self, meeting_id: str) -> AnnotationRecord:
        return self._repository.get(meeting_id)

    def list_records(self) -> list[AnnotationRecord]:
        return self._repository.list_records()

    def withdraw_consent(self, meeting_id: str) -> None:
        self._repository.delete(meeting_id)

    def export_adjudicated_manifest(self) -> ExtractionCaseManifest:
        records = self._repository.list_records()
        cases = [
            record.adjudication.extraction_case
            for record in records
            if record.source.consent_status == ConsentStatus.GRANTED
            and record.adjudication is not None
        ]
        return ExtractionCaseManifest(version="1.0", cases=cases)

    @staticmethod
    def _ensure_annotation_allowed(source: SourceMeeting) -> None:
        if source.consent_status != ConsentStatus.GRANTED:
            raise ValueError("granted consent is required before annotation")
        if source.pii_review_status not in {
            PiiReviewStatus.CLEAR,
            PiiReviewStatus.REDACTED,
        }:
            raise ValueError("PII review must finish before annotation")
        if source.redaction_status == RedactionStatus.PENDING:
            raise ValueError("redaction is incomplete")

    @staticmethod
    def _validate_evidence(
        source: SourceMeeting,
        items: list[AnnotatedDecision | AnnotatedAction],
    ) -> None:
        known_ids = {segment.id for segment in source.reviewed_segments}
        unknown_ids = sorted(
            {
                evidence_id
                for item in items
                for evidence_id in item.evidence_segment_ids
                if evidence_id not in known_ids
            }
        )
        if unknown_ids:
            raise ValueError(f"unknown evidence segment IDs: {', '.join(unknown_ids)}")

    @staticmethod
    def _validate_unique_item_ids(
        decisions: list[AnnotatedDecision],
        actions: list[AnnotatedAction],
    ) -> None:
        item_ids = [item.item_id for item in decisions]
        item_ids.extend(item.item_id for item in actions)
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("adjudicated item IDs must be unique")


def detect_disagreements(
    first: ReviewerSubmission,
    second: ReviewerSubmission,
) -> list[FieldDisagreement]:
    reviewers = (first.reviewer_id, second.reviewer_id)
    first_items = _index_submission(first)
    second_items = _index_submission(second)
    disagreements: list[FieldDisagreement] = []

    for item_id in sorted(set(first_items) | set(second_items)):
        first_entry = first_items.get(item_id)
        second_entry = second_items.get(item_id)
        if first_entry is None or second_entry is None:
            present_entry = first_entry or second_entry
            disagreements.append(
                FieldDisagreement(
                    item_id=item_id,
                    item_type=present_entry[0] if present_entry else "unknown",
                    field="presence",
                    reviewer_values={
                        reviewers[0]: first_entry is not None,
                        reviewers[1]: second_entry is not None,
                    },
                )
            )
            continue

        first_type, first_value = first_entry
        second_type, second_value = second_entry
        if first_type != second_type:
            disagreements.append(
                FieldDisagreement(
                    item_id=item_id,
                    item_type="unknown",
                    field="item_type",
                    reviewer_values={
                        reviewers[0]: first_type,
                        reviewers[1]: second_type,
                    },
                )
            )
            continue

        all_fields = sorted(set(first_value) | set(second_value))
        for field in all_fields:
            first_field = _comparison_value(field, first_value.get(field))
            second_field = _comparison_value(field, second_value.get(field))
            if first_field == second_field:
                continue
            disagreements.append(
                FieldDisagreement(
                    item_id=item_id,
                    item_type=first_type,
                    field=field,
                    reviewer_values={
                        reviewers[0]: first_value.get(field),
                        reviewers[1]: second_value.get(field),
                    },
                )
            )
    return disagreements


def _index_submission(
    submission: ReviewerSubmission,
) -> dict[str, tuple[Literal["decision", "action"], dict[str, Any]]]:
    indexed: dict[str, tuple[Literal["decision", "action"], dict[str, Any]]] = {}
    for decision in submission.decisions:
        indexed[decision.item_id] = (
            "decision",
            decision.model_dump(mode="json", exclude={"item_id"}),
        )
    for action in submission.actions:
        indexed[action.item_id] = (
            "action",
            action.model_dump(mode="json", exclude={"item_id"}),
        )
    return indexed


def _comparison_value(field: str, value: Any) -> Any:
    if field == "evidence_segment_ids" and isinstance(value, list):
        return sorted(value)
    if isinstance(value, str):
        return value.strip()
    return value


def _render_reviewed_transcript(source: SourceMeeting) -> str:
    lines: list[str] = []
    for segment in source.reviewed_segments:
        speaker_label = (
            re.sub(r"\s+", " ", segment.speaker_label).strip()
            if segment.speaker_label
            else f"Unknown Speaker {segment.sequence_no}"
        )
        text = re.sub(r"\s+", " ", segment.text).strip()
        lines.append(f"{speaker_label}: {text}")
    return "\n".join(lines)
