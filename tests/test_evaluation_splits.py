from callrhino.evaluation.models import ExtractionCaseManifest
from callrhino.evaluation.splits import (
    assert_independent_splits,
    validate_split_independence,
)


def _manifest(case_id: str, transcript: str) -> ExtractionCaseManifest:
    return ExtractionCaseManifest.model_validate(
        {
            "version": "1.0",
            "cases": [
                {
                    "id": case_id,
                    "title": "Test meeting",
                    "meeting_date": "2026-07-27",
                    "transcript": transcript,
                    "tags": ["test"],
                    "provenance": "synthetic",
                    "expected_decisions": [],
                    "expected_actions": [],
                    "forbidden_facts": [],
                }
            ],
        }
    )


def test_independent_splits_pass() -> None:
    report = validate_split_independence(
        _manifest("development-1", "Aditi: General development discussion."),
        _manifest("holdout-1", "Rohan: Separate holdout discussion."),
    )

    assert report.independent is True
    assert_independent_splits(report)


def test_duplicate_transcript_is_detected_after_normalization() -> None:
    report = validate_split_independence(
        _manifest("development-1", "Aditi: Ship this Friday!"),
        _manifest("holdout-1", "aditi ship this friday"),
    )

    assert report.independent is False
    try:
        assert_independent_splits(report)
    except ValueError as exc:
        assert "shared transcript fingerprints" in str(exc)
    else:
        raise AssertionError("duplicate transcript should fail")


def test_duplicate_case_id_is_detected() -> None:
    report = validate_split_independence(
        _manifest("same-id", "Development transcript."),
        _manifest("same-id", "Different holdout transcript."),
    )

    assert report.shared_ids == ("same-id",)
