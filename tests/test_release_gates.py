from callrhino.evaluation.release_gates import (
    CRITICAL_METRICS,
    evaluate_release_readiness,
    wilson_lower_bound,
)
from callrhino.services.prompts import EXTRACTION_PROMPT_VERSION


def _summary(*, cases: int, correct: int = 600, total: int = 600) -> dict:
    return {
        "case_count": cases,
        "schema_pass_rate": 1.0,
        "mean_forbidden_fact_count": 0.0,
        "micro_metrics": {
            name: {
                "correct": correct,
                "total": total,
                "value": correct / total,
            }
            for name in CRITICAL_METRICS
        },
    }


def _report(
    *,
    kind: str,
    dataset_id: str,
    fingerprint_char: str,
    cases: int,
    correct: int = 600,
    total: int = 600,
) -> dict:
    return {
        "evidence": {
            "kind": kind,
            "dataset_id": dataset_id,
            "dataset_fingerprint": fingerprint_char * 64,
            "prompt_version": EXTRACTION_PROMPT_VERSION,
            "provider": "sarvam",
            "model": "sarvam-105b",
        },
        "summary": _summary(cases=cases, correct=correct, total=total),
    }


def _holdout(**updates: object) -> dict:
    values = {
        "kind": "frozen_holdout",
        "dataset_id": "holdout-v1",
        "fingerprint_char": "a",
        "cases": 50,
    }
    values.update(updates)
    return _report(**values)


def _real(**updates: object) -> dict:
    values = {
        "kind": "consented_real_meetings",
        "dataset_id": "real-v1",
        "fingerprint_char": "b",
        "cases": 20,
    }
    values.update(updates)
    return _report(**values)


def _candidate_report() -> dict:
    return {
        "case_count": 20,
        "zero_gold_case_count": 0,
        "filtered_case_count": 12,
        "release_gate": {"passed": True},
        "gold_evidence_retention": {
            "retained": 200,
            "gold": 200,
            "ratio": 1.0,
        },
        "decision_evidence_retention": {
            "retained": 100,
            "gold": 100,
            "ratio": 1.0,
        },
        "action_evidence_retention": {
            "retained": 100,
            "gold": 100,
            "ratio": 1.0,
        },
        "case_all_evidence_retention": {
            "retained": 20,
            "gold": 20,
            "ratio": 1.0,
        },
    }


def test_release_gate_passes_only_with_independent_identified_evidence() -> None:
    result = evaluate_release_readiness(
        holdout_report=_holdout(),
        real_meeting_report=_real(),
    )

    assert result.ready is True
    assert result.failures == ()


def test_perfect_tiny_sample_fails_release_gate() -> None:
    result = evaluate_release_readiness(
        holdout_report=_holdout(cases=8, correct=8, total=8),
        real_meeting_report=_real(cases=2, correct=2, total=2),
    )

    assert result.ready is False
    assert any("requires at least 50 cases" in failure for failure in result.failures)
    assert any("requires at least 600 checks" in failure for failure in result.failures)
    assert any("95% lower bound" in failure for failure in result.failures)


def test_single_error_in_six_hundred_does_not_prove_995() -> None:
    result = evaluate_release_readiness(
        holdout_report=_holdout(correct=599),
        real_meeting_report=_real(),
    )

    assert result.ready is False
    assert any("95% lower bound" in failure for failure in result.failures)


def test_reports_must_be_independent_and_comparable() -> None:
    real = _real(dataset_id="holdout-v1", fingerprint_char="a")
    real["evidence"]["model"] = "sarvam-30b"

    result = evaluate_release_readiness(
        holdout_report=_holdout(),
        real_meeting_report=real,
    )

    assert result.ready is False
    assert any("share dataset_id" in failure for failure in result.failures)
    assert any("share dataset_fingerprint" in failure for failure in result.failures)
    assert any("different model" in failure for failure in result.failures)


def test_missing_or_stale_evidence_metadata_cannot_pass() -> None:
    holdout = {"summary": _summary(cases=50)}
    real = _real()
    real["evidence"]["prompt_version"] = "stale"

    result = evaluate_release_readiness(
        holdout_report=holdout,
        real_meeting_report=real,
    )

    assert result.ready is False
    assert "frozen holdout: evidence metadata is missing" in result.failures
    assert any("prompt version must be" in failure for failure in result.failures)


def test_metric_value_must_match_counts() -> None:
    holdout = _holdout()
    holdout["summary"]["micro_metrics"]["decision_recall"]["value"] = 1.0
    holdout["summary"]["micro_metrics"]["decision_recall"]["correct"] = 599

    result = evaluate_release_readiness(
        holdout_report=holdout,
        real_meeting_report=_real(),
    )

    assert result.ready is False
    assert any("value does not match its counts" in failure for failure in result.failures)


def test_candidate_gating_requires_substantial_evaluator_report() -> None:
    candidate = _candidate_report()
    candidate["case_count"] = 1
    candidate["gold_evidence_retention"] = {
        "retained": 1,
        "gold": 1,
        "ratio": 1.0,
    }

    result = evaluate_release_readiness(
        holdout_report=_holdout(),
        real_meeting_report=_real(),
        candidate_gating_enabled=True,
        candidate_report=candidate,
    )

    assert result.ready is False
    assert any("at least 20 long meetings" in item for item in result.failures)
    assert any("at least 200 gold evidence" in item for item in result.failures)


def test_candidate_gating_accepts_complete_report() -> None:
    result = evaluate_release_readiness(
        holdout_report=_holdout(),
        real_meeting_report=_real(),
        candidate_gating_enabled=True,
        candidate_report=_candidate_report(),
    )

    assert result.ready is True


def test_wilson_lower_bound_reflects_uncertainty() -> None:
    assert wilson_lower_bound(600, 600) is not None
    assert wilson_lower_bound(600, 600) > 0.995
    assert wilson_lower_bound(599, 600) < 0.995
    assert wilson_lower_bound(0, 0) is None
