from copy import deepcopy

import pytest

from callrhino.evaluation.holdout import (
    HoldoutPackageError,
    HoldoutPrediction,
    HoldoutPredictionPackage,
    PublicHoldoutCase,
    create_holdout_packages,
    score_holdout_package,
    validate_gold_package,
)
from callrhino.evaluation.models import ExtractionCaseManifest
from callrhino.services.prompts import EXTRACTION_PROMPT_VERSION


def test_packages_are_deterministic_and_public_input_has_no_gold() -> None:
    manifest = _manifest()
    reversed_manifest = manifest.model_copy(update={"cases": list(reversed(manifest.cases))})

    public, gold = create_holdout_packages(manifest)
    reordered_public, reordered_gold = create_holdout_packages(reversed_manifest)

    assert public == reordered_public
    assert gold == reordered_gold
    assert public.package_id.startswith("holdout_")
    assert len(public.cases[0].input_fingerprint) == 64
    assert len(public.cases[0].transcript_fingerprint) == 64

    serialized_public = public.model_dump(mode="json")
    forbidden_keys = {
        "expected_decisions",
        "expected_actions",
        "forbidden_facts",
        "case",
    }
    assert not (_all_keys(serialized_public) & forbidden_keys)

    serialized_gold = gold.model_dump(mode="json")
    assert serialized_gold["cases"][0]["case"]["expected_decisions"]
    assert serialized_gold["cases"][0]["case"]["forbidden_facts"]


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda payload: payload["cases"][1].update(
                {"id": payload["cases"][0]["id"]}
            ),
            "Duplicate case IDs",
        ),
        (
            lambda payload: payload["cases"][1].update(
                {"transcript": "ASHA, WE WILL LAUNCH FRIDAY!!!"}
            ),
            "Duplicate normalized transcripts",
        ),
    ],
)
def test_source_rejects_duplicate_ids_and_transcripts(mutator, message: str) -> None:
    payload = _manifest().model_dump(mode="json")
    mutator(payload)
    manifest = ExtractionCaseManifest.model_validate(payload)

    with pytest.raises(HoldoutPackageError, match=message):
        create_holdout_packages(manifest)


def test_scoring_uses_existing_extraction_metrics() -> None:
    public, gold = create_holdout_packages(_manifest())
    predictions = HoldoutPredictionPackage(
        package_id=public.package_id,
        predictions=[
            _perfect_prediction(case.id, case.input_fingerprint)
            for case in public.cases
        ],
    )

    result = score_holdout_package(gold, predictions)

    summary = result["summary"]
    assert summary["case_count"] == 2
    assert summary["schema_pass_rate"] == 1
    assert summary["mean_decision_precision"] == 1
    assert summary["mean_decision_recall"] == 1
    assert summary["mean_action_precision"] == 1
    assert summary["mean_action_recall"] == 1
    assert summary["mean_forbidden_fact_count"] == 0


def test_scoring_rejects_missing_and_extra_prediction_ids() -> None:
    public, gold = create_holdout_packages(_manifest())
    predictions = HoldoutPredictionPackage(
        package_id=public.package_id,
        predictions=[
            _perfect_prediction("case_alpha", public.cases[0].input_fingerprint),
            _perfect_prediction("unexpected", public.cases[1].input_fingerprint),
        ],
    )

    with pytest.raises(HoldoutPackageError) as error:
        score_holdout_package(gold, predictions)

    assert "missing prediction IDs: case_beta" in str(error.value)
    assert "extra prediction IDs: unexpected" in str(error.value)


def test_scoring_rejects_package_and_input_fingerprint_mismatches() -> None:
    public, gold = create_holdout_packages(_manifest())
    valid_predictions = [
        _perfect_prediction(case.id, case.input_fingerprint)
        for case in public.cases
    ]

    with pytest.raises(HoldoutPackageError, match="Package ID mismatch"):
        score_holdout_package(
            gold,
            HoldoutPredictionPackage(
                package_id="holdout_wrong",
                predictions=valid_predictions,
            ),
        )

    invalid_predictions = deepcopy(valid_predictions)
    invalid_predictions[0] = invalid_predictions[0].model_copy(
        update={"input_fingerprint": "f" * 64}
    )
    with pytest.raises(HoldoutPackageError, match="input fingerprint mismatch"):
        score_holdout_package(
            gold,
            HoldoutPredictionPackage(
                package_id=public.package_id,
                predictions=invalid_predictions,
            ),
        )


def test_scoring_rejects_predictions_from_stale_prompt() -> None:
    public, gold = create_holdout_packages(_manifest())
    predictions = HoldoutPredictionPackage(
        package_id=public.package_id,
        prompt_version=f"{EXTRACTION_PROMPT_VERSION}-stale",
        predictions=[
            _perfect_prediction(case.id, case.input_fingerprint)
            for case in public.cases
        ],
    )

    with pytest.raises(HoldoutPackageError, match="Prompt version mismatch"):
        score_holdout_package(gold, predictions)


def test_scoring_rejects_duplicate_prediction_ids() -> None:
    public, gold = create_holdout_packages(_manifest())
    prediction = _perfect_prediction(
        public.cases[0].id,
        public.cases[0].input_fingerprint,
    )

    with pytest.raises(HoldoutPackageError, match="Duplicate prediction case IDs"):
        score_holdout_package(
            gold,
            HoldoutPredictionPackage(
                package_id=public.package_id,
                predictions=[prediction, prediction],
            ),
        )


def test_private_gold_rejects_tampering() -> None:
    _, gold = create_holdout_packages(_manifest())
    tampered = gold.model_copy(
        update={
            "cases": [
                gold.cases[0].model_copy(update={"input_fingerprint": "a" * 64}),
                gold.cases[1],
            ]
        }
    )

    with pytest.raises(HoldoutPackageError, match="invalid fingerprints"):
        validate_gold_package(tampered)


def test_public_holdout_rejects_blank_transcript() -> None:
    with pytest.raises(ValueError, match="transcript cannot be blank"):
        PublicHoldoutCase(
            id="blank",
            title="Blank",
            meeting_date="2026-07-27",
            meeting_type="internal_project",
            transcript="   ",
            tags=[],
            provenance="synthetic",
            transcript_fingerprint="a" * 64,
            input_fingerprint="b" * 64,
        )


def _manifest() -> ExtractionCaseManifest:
    return ExtractionCaseManifest.model_validate(
        {
            "version": "test-1",
            "cases": [
                {
                    "id": "case_alpha",
                    "title": "Release review",
                    "meeting_date": "2026-07-27",
                    "meeting_type": "internal_project",
                    "transcript": "Asha: We will launch Friday.",
                    "tags": ["decision", "english"],
                    "provenance": "consented",
                    "expected_decisions": [
                        {
                            "text": "Launch Friday.",
                            "status": "confirmed",
                            "decision_maker_text": "Asha",
                            "effective_date": "2026-07-31",
                            "effective_date_text": "Friday",
                            "date_precision": "resolved_relative",
                            "evidence_segment_ids": ["seg_0001"],
                        }
                    ],
                    "expected_actions": [],
                    "forbidden_facts": ["Launch Monday"],
                },
                {
                    "id": "case_beta",
                    "title": "Copy review",
                    "meeting_date": "2026-07-27",
                    "meeting_type": "internal_project",
                    "transcript": "Ravi: I will send the copy tomorrow.",
                    "tags": ["action", "english"],
                    "provenance": "consented",
                    "expected_decisions": [],
                    "expected_actions": [
                        {
                            "task": "Send the copy.",
                            "commitment_status": "committed",
                            "owner_text": "Ravi",
                            "suggested_owner_text": None,
                            "due_date": "2026-07-28",
                            "due_text": "tomorrow",
                            "deadline_precision": "resolved_relative",
                            "evidence_segment_ids": ["seg_0001"],
                        }
                    ],
                    "forbidden_facts": ["Asha owns the copy"],
                },
            ],
        }
    )


def _perfect_prediction(case_id: str, fingerprint: str) -> HoldoutPrediction:
    if case_id == "case_alpha":
        brief = {
            "decisions": [
                {
                    "text": "Launch Friday.",
                    "status": "confirmed",
                    "decision_maker_text": "Asha",
                    "effective_date": "2026-07-31",
                    "effective_date_text": "Friday",
                    "date_precision": "resolved_relative",
                    "evidence_segment_ids": ["seg_0001"],
                }
            ],
            "action_items": [],
        }
    else:
        brief = {
            "decisions": [],
            "action_items": [
                {
                    "task": "Send the copy.",
                    "commitment_status": "committed",
                    "owner_text": "Ravi",
                    "suggested_owner_text": None,
                    "due_date": "2026-07-28",
                    "due_text": "tomorrow",
                    "deadline_precision": "resolved_relative",
                    "evidence_segment_ids": ["seg_0001"],
                }
            ],
        }
    return HoldoutPrediction(
        case_id=case_id,
        input_fingerprint=fingerprint,
        provider="test",
        model="test",
        latency_seconds=0,
        schema_valid=True,
        brief=brief,
    )


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            nested_key
            for nested in value.values()
            for nested_key in _all_keys(nested)
        }
    if isinstance(value, list):
        return {
            nested_key
            for nested in value
            for nested_key in _all_keys(nested)
        }
    return set()
