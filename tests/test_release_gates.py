from callrhino.evaluation.release_gates import (
    CRITICAL_METRICS,
    evaluate_release_readiness,
)


def _summary(*, cases: int, correct: int = 200, total: int = 200) -> dict:
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


def test_release_gate_passes_only_with_both_independent_data_sources() -> None:
    result = evaluate_release_readiness(
        holdout_summary=_summary(cases=50),
        real_meeting_summary=_summary(cases=20),
    )

    assert result.ready is True
    assert result.failures == ()


def test_perfect_tiny_sample_fails_release_gate() -> None:
    result = evaluate_release_readiness(
        holdout_summary=_summary(cases=8, correct=8, total=8),
        real_meeting_summary=_summary(cases=2, correct=2, total=2),
    )

    assert result.ready is False
    assert any("requires at least 50 cases" in failure for failure in result.failures)
    assert any("requires at least 200 checks" in failure for failure in result.failures)


def test_single_error_in_two_hundred_checks_meets_995_threshold() -> None:
    result = evaluate_release_readiness(
        holdout_summary=_summary(cases=50, correct=199, total=200),
        real_meeting_summary=_summary(cases=20, correct=199, total=200),
    )

    assert result.ready is True


def test_rate_below_threshold_fails_even_with_large_sample() -> None:
    result = evaluate_release_readiness(
        holdout_summary=_summary(cases=50, correct=994, total=1000),
        real_meeting_summary=_summary(cases=20),
    )

    assert result.ready is False
    assert any("must be at least 99.500%" in failure for failure in result.failures)


def test_candidate_gating_requires_perfect_long_meeting_retention() -> None:
    result = evaluate_release_readiness(
        holdout_summary=_summary(cases=50),
        real_meeting_summary=_summary(cases=20),
        candidate_gating_enabled=True,
        candidate_report={
            "case_count": 20,
            "gold_evidence_retention": 0.999,
            "case_all_evidence_retention": 0.95,
        },
    )

    assert result.ready is False
    assert any("gold evidence retention must be 100%" in item for item in result.failures)


def test_candidate_gating_accepts_long_meeting_report_shape() -> None:
    result = evaluate_release_readiness(
        holdout_summary=_summary(cases=50),
        real_meeting_summary=_summary(cases=20),
        candidate_gating_enabled=True,
        candidate_report={
            "case_count": 20,
            "gold_evidence_retention": {
                "retained": 200,
                "gold": 200,
                "ratio": 1.0,
            },
            "case_all_evidence_retention": {
                "retained": 20,
                "gold": 20,
                "ratio": 1.0,
            },
        },
    )

    assert result.ready is True


def test_missing_micro_metrics_cannot_pass() -> None:
    result = evaluate_release_readiness(
        holdout_summary={
            "case_count": 50,
            "schema_pass_rate": 1,
            "mean_forbidden_fact_count": 0,
        },
        real_meeting_summary=_summary(cases=20),
    )

    assert result.ready is False
    assert "frozen holdout: micro metrics are missing" in result.failures
