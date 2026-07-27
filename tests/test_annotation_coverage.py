from datetime import date

from callrhino.annotation import (
    Adjudication,
    AnnotatedAction,
    AnnotatedDecision,
    AnnotationRecord,
    ConsentStatus,
    CoveragePlan,
    PiiReviewStatus,
    RedactionStatus,
    ReviewerSubmission,
    SourceMeeting,
    evaluate_coverage,
)
from callrhino.domain.models import TranscriptSegment
from callrhino.evaluation.models import ExtractionCase


def _plan() -> CoveragePlan:
    return CoveragePlan.model_validate(
        {
            "version": "test-v1",
            "minimum_adjudicated_meetings": 20,
            "minimum_expected_decisions": 2,
            "minimum_expected_actions": 2,
            "quotas": [
                {
                    "id": "hinglish",
                    "label": "Hinglish",
                    "required_tags": ["hinglish"],
                    "target_adjudicated_meetings": 1,
                }
            ],
        }
    )


def _record(*, adjudicated: bool) -> AnnotationRecord:
    source = SourceMeeting(
        id="meeting-1",
        title="Review",
        meeting_date=date(2026, 7, 27),
        tags=["Hinglish", "noisy-call"],
        consent_status=ConsentStatus.GRANTED,
        consent_reference="consent-1",
        pii_review_status=PiiReviewStatus.CLEAR,
        redaction_status=RedactionStatus.NOT_REQUIRED,
        reviewed_segments=[
            TranscriptSegment(
                id="seg_0001",
                sequence_no=1,
                speaker_label="Asha",
                text="Launch Friday.",
            )
        ],
    )
    submissions = [
        ReviewerSubmission(reviewer_id="reviewer-1"),
        ReviewerSubmission(reviewer_id="reviewer-2"),
    ]
    adjudication = None
    if adjudicated:
        adjudication = Adjudication(
            adjudicator_id="lead",
            extraction_case=ExtractionCase(
                id=source.id,
                title=source.title,
                meeting_date=source.meeting_date,
                transcript="Asha: Launch Friday.",
                tags=source.tags,
                provenance="consented",
                expected_decisions=[
                    AnnotatedDecision(
                        item_id="decision-1",
                        text="Launch Friday.",
                        status="confirmed",
                        date_precision="absent",
                        evidence_segment_ids=["seg_0001"],
                    ).model_dump(exclude={"item_id"})
                ],
                expected_actions=[
                    AnnotatedAction(
                        item_id="action-1",
                        task="Prepare launch.",
                        commitment_status="committed",
                        deadline_precision="absent",
                        evidence_segment_ids=["seg_0001"],
                    ).model_dump(exclude={"item_id"})
                ],
            ),
        )
    return AnnotationRecord(
        source=source,
        submissions=submissions,
        adjudication=adjudication,
    )


def test_coverage_reports_exact_remaining_work() -> None:
    report = evaluate_coverage(_plan(), [_record(adjudicated=True)])

    assert report.adjudicated_meetings == 1
    assert report.expected_decisions == 1
    assert report.expected_actions == 1
    assert report.remaining_adjudicated_meetings == 19
    assert report.remaining_expected_decisions == 1
    assert report.remaining_expected_actions == 1
    assert report.quotas[0].complete is True
    assert report.complete is False


def test_coverage_does_not_count_reviewed_only_as_adjudicated() -> None:
    report = evaluate_coverage(_plan(), [_record(adjudicated=False)])

    assert report.dual_reviewed_meetings == 1
    assert report.adjudicated_meetings == 0
    assert report.quotas[0].dual_reviewed_meetings == 1
    assert report.quotas[0].adjudicated_meetings == 0
