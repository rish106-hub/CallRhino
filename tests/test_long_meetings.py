from pathlib import Path

import pytest

from callrhino.evaluation.io import load_model
from callrhino.evaluation.long_meetings import evaluate_long_meetings
from callrhino.evaluation.models import ExtractionCaseManifest


def _transcript(overrides: dict[int, str], *, segment_count: int = 30) -> str:
    return "\n".join(
        f"Speaker {index}: {overrides.get(index, f'Routine update number {index}.')}"
        for index in range(1, segment_count + 1)
    )


def _manifest(
    *,
    transcript: str,
    decisions: list[dict] | None = None,
    actions: list[dict] | None = None,
) -> ExtractionCaseManifest:
    return ExtractionCaseManifest.model_validate(
        {
            "version": "1.0",
            "cases": [
                {
                    "id": "long-case",
                    "title": "Long weekly review",
                    "meeting_date": "2026-07-27",
                    "transcript": transcript,
                    "tags": ["long", "synthetic"],
                    "provenance": "synthetic",
                    "expected_decisions": decisions or [],
                    "expected_actions": actions or [],
                    "forbidden_facts": [],
                }
            ],
        }
    )


def _decision(evidence_id: str) -> dict:
    return {
        "text": "Launch on Friday.",
        "status": "confirmed",
        "date_precision": "absent",
        "evidence_segment_ids": [evidence_id],
    }


def _action(evidence_id: str) -> dict:
    return {
        "task": "Send the launch deck.",
        "commitment_status": "committed",
        "deadline_precision": "absent",
        "evidence_segment_ids": [evidence_id],
    }


def test_candidate_gate_retains_all_cued_evidence_and_reduces_prompt() -> None:
    manifest = _manifest(
        transcript=_transcript(
            {
                7: "We decided to launch on Friday.",
                24: "I will send the launch deck.",
            }
        ),
        decisions=[_decision("seg_0007")],
        actions=[_action("seg_0024")],
    )

    report = evaluate_long_meetings(manifest)

    assert report.baseline_gold_evidence_retention.ratio == 1
    assert report.gold_evidence_retention.ratio == 1
    assert report.decision_evidence_retention.ratio == 1
    assert report.action_evidence_retention.ratio == 1
    assert report.case_all_evidence_retention.ratio == 1
    assert report.segment_selection.selected_ratio < 1
    assert report.prompt_characters.reduction_ratio is not None
    assert report.prompt_characters.reduction_ratio > 0
    assert report.release_gate.passed is True


def test_candidate_gate_fails_when_an_uncued_fact_is_missed() -> None:
    manifest = _manifest(
        transcript=_transcript(
            {
                5: "I will circulate the agenda.",
                15: "The palette stays amber.",
            }
        ),
        decisions=[_decision("seg_0015")],
    )

    report = evaluate_long_meetings(manifest)

    assert report.gold_evidence_retention.ratio == 0
    assert report.decision_evidence_retention.ratio == 0
    assert report.action_evidence_retention.ratio is None
    assert report.case_all_evidence_retention.ratio == 0
    assert report.cases[0].missed_decision_evidence_ids == ["seg_0015"]
    assert report.release_gate.passed is False
    assert "Gold evidence segment retention must be 100%." in report.release_gate.reasons


def test_zero_gold_items_cannot_create_false_confidence() -> None:
    manifest = _manifest(
        transcript=_transcript({5: "I will circulate the agenda."}),
    )

    report = evaluate_long_meetings(manifest)

    assert report.gold_evidence_retention.ratio is None
    assert report.decision_evidence_retention.ratio is None
    assert report.action_evidence_retention.ratio is None
    assert report.case_all_evidence_retention.ratio is None
    assert report.release_gate.passed is False
    assert any(warning.startswith("NO_GOLD_EVIDENCE") for warning in report.warnings)


def test_empty_manifest_cannot_create_false_confidence() -> None:
    manifest = ExtractionCaseManifest(version="1.0", cases=[])

    report = evaluate_long_meetings(manifest)

    assert report.case_count == 0
    assert report.gold_evidence_retention.ratio is None
    assert report.segment_selection.selected_ratio is None
    assert report.prompt_characters.reduction_ratio is None
    assert report.release_gate.passed is False
    assert report.warnings == ["NO_CASES: no long-meeting cases were evaluated."]


def test_unknown_gold_evidence_id_is_rejected() -> None:
    manifest = _manifest(
        transcript=_transcript({7: "We decided to launch on Friday."}),
        decisions=[_decision("seg_9999")],
    )

    with pytest.raises(ValueError, match="unknown decision evidence IDs"):
        evaluate_long_meetings(manifest)


def test_empty_template_is_a_valid_extraction_manifest() -> None:
    manifest = load_model(
        Path("evals/cases/long_meetings.template.json"),
        ExtractionCaseManifest,
    )

    assert manifest.cases == []
