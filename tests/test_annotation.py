import json
import os
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from callrhino.annotation.models import (
    AnnotatedAction,
    AnnotatedDecision,
    ConsentStatus,
    PiiReviewStatus,
    RedactionStatus,
    ReviewerSubmission,
    SourceMeeting,
)
from callrhino.annotation.repository import (
    DuplicateAdjudicationError,
    DuplicateReviewerError,
    JsonAnnotationRepository,
    ReviewerLimitError,
)
from callrhino.annotation.service import AnnotationService
from callrhino.domain.models import TranscriptSegment


def _source(**updates: object) -> SourceMeeting:
    values = {
        "id": "consented_meeting_001",
        "title": "Release review",
        "meeting_date": date(2026, 7, 27),
        "meeting_type": "internal_project",
        "tags": ["hinglish", "release"],
        "consent_status": ConsentStatus.GRANTED,
        "consent_reference": "consent-form-001",
        "pii_review_status": PiiReviewStatus.CLEAR,
        "redaction_status": RedactionStatus.NOT_REQUIRED,
        "reviewed_segments": [
            TranscriptSegment(
                id="seg_0001",
                sequence_no=1,
                speaker_label="Neha",
                text="Payment callback abhi fail ho raha hai.",
            ),
            TranscriptSegment(
                id="seg_0002",
                sequence_no=2,
                speaker_label="Arjun",
                text="Launch ko Friday tak defer karte hain.",
            ),
        ],
    }
    values.update(updates)
    return SourceMeeting.model_validate(values)


def _decision(
    *,
    text: str = "Defer the launch until Friday.",
    evidence: list[str] | None = None,
) -> AnnotatedDecision:
    return AnnotatedDecision(
        item_id="decision_launch",
        text=text,
        status="deferred",
        decision_maker_text="Arjun",
        effective_date=None,
        effective_date_text="Friday",
        date_precision="vague",
        evidence_segment_ids=evidence or ["seg_0001", "seg_0002"],
    )


def _action(*, owner: str | None = "Neha") -> AnnotatedAction:
    return AnnotatedAction(
        item_id="action_callback",
        task="Fix the payment callback.",
        commitment_status="committed",
        owner_text=owner,
        suggested_owner_text=None,
        due_date=date(2026, 7, 31),
        due_text="Friday",
        deadline_precision="resolved_relative",
        evidence_segment_ids=["seg_0001"],
    )


def _submission(
    reviewer_id: str,
    *,
    decision: AnnotatedDecision | None = None,
    action: AnnotatedAction | None = None,
) -> ReviewerSubmission:
    return ReviewerSubmission(
        reviewer_id=reviewer_id,
        decisions=[decision or _decision()],
        actions=[action or _action()],
    )


@pytest.fixture
def service(tmp_path: Path) -> AnnotationService:
    return AnnotationService(JsonAnnotationRepository(tmp_path / "annotations"))


def test_registers_only_consented_pii_reviewed_transcript(
    service: AnnotationService,
) -> None:
    record = service.register_meeting(_source())

    assert record.source.provenance == "consented"
    assert record.source.reviewed_segments[0].text.startswith("Payment")
    assert "audio" not in record.model_dump_json().casefold()

    with pytest.raises(ValueError, match="granted consent"):
        service.register_meeting(
            _source(id="withdrawn", consent_status=ConsentStatus.WITHDRAWN)
        )
    with pytest.raises(ValueError, match="PII review"):
        service.register_meeting(
            _source(
                id="pii_pending",
                pii_review_status=PiiReviewStatus.PENDING,
                redaction_status=RedactionStatus.PENDING,
            )
        )
    with pytest.raises(ValidationError, match="raw_audio_path"):
        SourceMeeting.model_validate(
            {
                **_source(id="no_audio").model_dump(),
                "raw_audio_path": "/private/meeting.wav",
            }
        )


def test_source_rejects_noncanonical_segments_and_invalid_redaction_state() -> None:
    with pytest.raises(ValidationError, match="canonical sequence IDs"):
        _source(
            reviewed_segments=[
                TranscriptSegment(
                    id="speaker-turn-1",
                    sequence_no=1,
                    speaker_label=None,
                    text="Hello",
                )
            ]
        )
    with pytest.raises(ValidationError, match="completed redaction"):
        _source(
            pii_review_status=PiiReviewStatus.REDACTED,
            redaction_status=RedactionStatus.PENDING,
        )


def test_reviewer_submission_is_append_only_and_identity_is_case_insensitive(
    service: AnnotationService,
) -> None:
    service.register_meeting(_source())
    first = service.submit_review("consented_meeting_001", _submission("Reviewer@One.test"))

    with pytest.raises(DuplicateReviewerError):
        service.submit_review("consented_meeting_001", _submission("reviewer@one.test"))

    stored = service.get("consented_meeting_001")
    assert stored.submissions == first.submissions
    assert len(stored.submissions) == 1


def test_exactly_two_distinct_reviewers_are_allowed(service: AnnotationService) -> None:
    service.register_meeting(_source())
    service.submit_review("consented_meeting_001", _submission("reviewer-1"))
    service.submit_review("consented_meeting_001", _submission("reviewer-2"))

    with pytest.raises(ReviewerLimitError, match="exactly two"):
        service.submit_review("consented_meeting_001", _submission("reviewer-3"))


def test_unknown_evidence_ids_are_rejected_for_review_and_adjudication(
    service: AnnotationService,
) -> None:
    service.register_meeting(_source())
    with pytest.raises(ValueError, match="seg_9999"):
        service.submit_review(
            "consented_meeting_001",
            _submission("reviewer-1", decision=_decision(evidence=["seg_9999"])),
        )

    service.submit_review("consented_meeting_001", _submission("reviewer-1"))
    service.submit_review("consented_meeting_001", _submission("reviewer-2"))
    with pytest.raises(ValueError, match="seg_9999"):
        service.adjudicate(
            "consented_meeting_001",
            adjudicator_id="lead-reviewer",
            decisions=[_decision(evidence=["seg_9999"])],
            actions=[_action()],
        )


def test_disagreements_are_reported_by_item_and_field(
    service: AnnotationService,
) -> None:
    service.register_meeting(_source())
    service.submit_review("consented_meeting_001", _submission("reviewer-1"))
    service.submit_review(
        "consented_meeting_001",
        _submission(
            "reviewer-2",
            decision=_decision(text="Delay launch until the callback works."),
            action=_action(owner=None),
        ),
    )

    disagreements = service.disagreements("consented_meeting_001")
    fields = {(item.item_id, item.field) for item in disagreements}

    assert ("decision_launch", "text") in fields
    assert ("action_callback", "owner_text") in fields
    assert ("decision_launch", "evidence_segment_ids") not in fields


def test_disagreements_detect_presence_and_item_type(
    service: AnnotationService,
) -> None:
    service.register_meeting(_source())
    service.submit_review(
        "consented_meeting_001",
        ReviewerSubmission(reviewer_id="reviewer-1", decisions=[_decision()]),
    )
    service.submit_review(
        "consented_meeting_001",
        ReviewerSubmission(
            reviewer_id="reviewer-2",
            actions=[
                _action().model_copy(update={"item_id": "decision_launch"}),
                _action().model_copy(update={"item_id": "reviewer_two_only"}),
            ],
        ),
    )

    disagreements = service.disagreements("consented_meeting_001")

    assert any(
        item.item_id == "decision_launch" and item.field == "item_type"
        for item in disagreements
    )
    assert any(
        item.item_id == "reviewer_two_only" and item.field == "presence"
        for item in disagreements
    )


def test_adjudication_requires_two_reviews_and_builds_gold_extraction_case(
    service: AnnotationService,
) -> None:
    service.register_meeting(_source())
    service.submit_review("consented_meeting_001", _submission("reviewer-1"))
    with pytest.raises(ValueError, match="two reviewer"):
        service.adjudicate(
            "consented_meeting_001",
            adjudicator_id="lead-reviewer",
            decisions=[_decision()],
            actions=[_action()],
        )

    service.submit_review("consented_meeting_001", _submission("reviewer-2"))
    record = service.adjudicate(
        "consented_meeting_001",
        adjudicator_id="lead-reviewer",
        decisions=[_decision()],
        actions=[_action()],
        forbidden_facts=["Launch is confirmed."],
    )

    assert record.adjudication is not None
    gold = record.adjudication.extraction_case
    assert gold.provenance == "consented"
    assert gold.expected_decisions[0].evidence_segment_ids == ["seg_0001", "seg_0002"]
    assert gold.expected_actions[0].owner_text == "Neha"
    assert "Neha: Payment callback" in gold.transcript

    with pytest.raises(DuplicateAdjudicationError):
        service.adjudicate(
            "consented_meeting_001",
            adjudicator_id="another-lead",
            decisions=[_decision()],
            actions=[_action()],
        )


def test_json_write_is_valid_and_leaves_no_temporary_files(
    service: AnnotationService,
    tmp_path: Path,
) -> None:
    service.register_meeting(_source())
    service.submit_review("consented_meeting_001", _submission("reviewer-1"))
    record_path = tmp_path / "annotations" / "consented_meeting_001.json"

    payload = json.loads(record_path.read_text(encoding="utf-8"))

    assert payload["submissions"][0]["reviewer_id"] == "reviewer-1"
    assert record_path.stat().st_mode & 0o777 == 0o600
    assert not list((tmp_path / "annotations").glob("*.tmp"))


def test_failed_atomic_replace_preserves_previous_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = JsonAnnotationRepository(tmp_path / "annotations")
    service = AnnotationService(repository)
    service.register_meeting(_source())
    record_path = tmp_path / "annotations" / "consented_meeting_001.json"
    original = record_path.read_text(encoding="utf-8")

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        service.submit_review("consented_meeting_001", _submission("reviewer-1"))

    assert record_path.read_text(encoding="utf-8") == original
    assert not list((tmp_path / "annotations").glob("*.tmp"))


def test_withdrawing_consent_deletes_stored_transcript(
    service: AnnotationService,
    tmp_path: Path,
) -> None:
    service.register_meeting(_source())
    record_path = tmp_path / "annotations" / "consented_meeting_001.json"

    service.withdraw_consent("consented_meeting_001")

    assert not record_path.exists()
    assert service.list_records() == []


def test_exports_only_adjudicated_consented_gold(
    service: AnnotationService,
) -> None:
    service.register_meeting(_source())
    service.register_meeting(_source(id="not_adjudicated"))
    service.submit_review("consented_meeting_001", _submission("reviewer-1"))
    service.submit_review("consented_meeting_001", _submission("reviewer-2"))
    service.adjudicate(
        "consented_meeting_001",
        adjudicator_id="lead-reviewer",
        decisions=[_decision()],
        actions=[_action()],
    )

    manifest = service.export_adjudicated_manifest()

    assert [case.id for case in manifest.cases] == ["consented_meeting_001"]
