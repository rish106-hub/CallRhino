from pathlib import Path

import pytest

from callrhino.evaluation.extraction_metrics import (
    score_extraction_case,
    summarize_extraction,
)
from callrhino.evaluation.io import load_model
from callrhino.evaluation.models import (
    BenchmarkManifest,
    ExtractionCase,
    ExtractionCaseManifest,
    ExtractionPrediction,
)
from callrhino.evaluation.text_metrics import (
    character_error_rate,
    phrase_recall,
    token_f1,
    token_precision_recall,
    word_error_rate,
)


def test_multilingual_text_metrics_are_unicode_safe() -> None:
    reference = "मैं revised copy Wednesday तक भेज दूंगा"
    hypothesis = "मैं revised copy Wednesday तक भेज दूंगा"

    assert word_error_rate(reference, hypothesis) == 0
    assert character_error_rate(reference, hypothesis) == 0
    assert phrase_recall(["revised copy", "Wednesday"], hypothesis) == 1
    assert token_f1("revised landing page copy", "send revised copy") > 0.5
    assert token_precision_recall(
        "send revised copy",
        "please send revised copy today",
    ) == (0.6, 1.0)


def test_dataset_manifest_marks_synthetic_and_blocked_sources() -> None:
    manifest = load_model(Path("evals/datasets.json"), BenchmarkManifest)

    synthetic = next(
        source for source in manifest.sources if source.id == "callrhino_indian_stress_v1"
    )
    kathbath = next(source for source in manifest.sources if source.id == "kathbath")

    assert not synthetic.real_world_data
    assert kathbath.status == "blocked"


def test_indian_extraction_cases_have_unique_ids_and_provenance() -> None:
    manifest = load_model(
        Path("evals/cases/indian_meetings.json"),
        ExtractionCaseManifest,
    )

    assert len(manifest.cases) >= 8
    assert len({case.id for case in manifest.cases}) == len(manifest.cases)
    assert all(case.provenance == "synthetic" for case in manifest.cases)


def test_extraction_score_penalizes_hallucinated_action() -> None:
    cases = load_model(
        Path("evals/cases/indian_meetings.json"),
        ExtractionCaseManifest,
    )
    case = next(item for item in cases.cases if item.id == "proposal_not_decision")
    prediction = ExtractionPrediction(
        case_id=case.id,
        provider="test",
        model="test",
        latency_seconds=0,
        schema_valid=True,
        brief={
            "decisions": [],
            "action_items": [
                {
                    "task": "Add WhatsApp export this sprint.",
                    "owner_text": None,
                    "due_date": None,
                    "due_text": None,
                    "evidence_segment_ids": ["seg_0001"],
                }
            ],
        },
    )

    score = score_extraction_case(case, prediction)

    assert score.action_precision == 0
    assert score.action_recall == 1
    assert score.forbidden_fact_count == 1
    assert score.expected_action_count == 0
    assert score.predicted_action_count == 1
    assert score.matched_action_count == 0

    summary = summarize_extraction([score])
    action_precision = summary["micro_metrics"]["action_precision"]
    assert action_precision == {"correct": 0, "total": 1, "value": 0.0}
    action_recall = summary["micro_metrics"]["action_recall"]
    assert action_recall == {"correct": 0, "total": 0, "value": None}


def test_extraction_score_uses_evidence_to_match_valid_paraphrases() -> None:
    cases = load_model(
        Path("evals/cases/indian_meetings.json"),
        ExtractionCaseManifest,
    )
    case = next(item for item in cases.cases if item.id == "tamil_english_code_mix")
    prediction = ExtractionPrediction(
        case_id=case.id,
        provider="test",
        model="test",
        latency_seconds=0,
        schema_valid=True,
        brief={
            "decisions": [
                {
                    "text": "Launch decision deferred pending crash logs",
                    "status": "deferred",
                    "decision_maker_text": "Karthik",
                    "effective_date": None,
                    "effective_date_text": None,
                    "date_precision": "absent",
                    "evidence_segment_ids": ["seg_0003"],
                }
            ],
            "action_items": [],
        },
    )

    score = score_extraction_case(case, prediction)

    assert score.decision_precision == 1
    assert score.decision_recall == 1
    assert score.evidence_accuracy == 0


def test_extraction_score_does_not_match_unrelated_text_from_same_segment() -> None:
    cases = load_model(
        Path("evals/cases/indian_meetings.json"),
        ExtractionCaseManifest,
    )
    case = next(item for item in cases.cases if item.id == "tamil_english_code_mix")
    prediction = ExtractionPrediction(
        case_id=case.id,
        provider="test",
        model="test",
        latency_seconds=0,
        schema_valid=True,
        brief={
            "decisions": [
                {
                    "text": "Order lunch for the office",
                    "evidence_segment_ids": ["seg_0003"],
                }
            ],
            "action_items": [],
        },
    )

    score = score_extraction_case(case, prediction)

    assert score.decision_precision == 0
    assert score.decision_recall == 0


def test_extraction_score_rejects_opposite_polarity_with_same_evidence() -> None:
    case = ExtractionCase.model_validate(
        {
            "id": "opposite-polarity",
            "title": "Launch review",
            "meeting_date": "2026-07-27",
            "transcript": "Asha: Cancel the Android launch on Friday.",
            "tags": ["negation"],
            "provenance": "synthetic",
            "expected_decisions": [
                {
                    "text": "Cancel the Android launch on Friday.",
                    "status": "confirmed",
                    "date_precision": "absent",
                    "evidence_segment_ids": ["seg_0001"],
                }
            ],
        }
    )
    prediction = ExtractionPrediction(
        case_id=case.id,
        provider="test",
        model="test",
        latency_seconds=0,
        schema_valid=True,
        brief={
            "decisions": [
                {
                    "text": "Launch Android on Friday.",
                    "status": "confirmed",
                    "date_precision": "absent",
                    "evidence_segment_ids": ["seg_0001"],
                }
            ],
            "action_items": [],
        },
    )

    score = score_extraction_case(case, prediction)

    assert score.decision_precision == 0
    assert score.decision_recall == 0


def test_word_error_rate_handles_empty_reference() -> None:
    assert word_error_rate("", "") == 0
    assert word_error_rate("", "hallucination") == 1


@pytest.mark.parametrize(
    ("reference", "hypothesis", "expected"),
    [
        ("ship Friday", "ship Friday", 0),
        ("ship Friday", "ship Monday", 0.5),
        ("₹2 lakh", "₹2 lakh", 0),
    ],
)
def test_word_error_rate_examples(
    reference: str,
    hypothesis: str,
    expected: float,
) -> None:
    assert word_error_rate(reference, hypothesis) == expected
