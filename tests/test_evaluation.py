from pathlib import Path

import pytest

from callrhino.evaluation.extraction_metrics import score_extraction_case
from callrhino.evaluation.io import load_model
from callrhino.evaluation.models import (
    BenchmarkManifest,
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
