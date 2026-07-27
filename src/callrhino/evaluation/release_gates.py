from dataclasses import asdict, dataclass
from math import isfinite, sqrt
from typing import Any

from callrhino.services.prompts import EXTRACTION_PROMPT_VERSION

CRITICAL_METRICS = (
    "decision_precision",
    "decision_recall",
    "action_precision",
    "action_recall",
    "owner_accuracy",
    "classification_accuracy",
    "decision_date_accuracy",
    "deadline_accuracy",
    "evidence_accuracy",
)
DEFAULT_CONFIDENCE = 0.95
DEFAULT_Z_SCORE = 1.6448536269514722


@dataclass(frozen=True)
class ReleaseGateResult:
    ready: bool
    threshold: float
    confidence: float
    minimum_checks_per_metric: int
    failures: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_release_readiness(
    *,
    holdout_report: dict[str, Any],
    real_meeting_report: dict[str, Any],
    candidate_gating_enabled: bool = False,
    candidate_report: dict[str, Any] | None = None,
    threshold: float = 0.995,
    minimum_checks_per_metric: int = 600,
    minimum_holdout_cases: int = 50,
    minimum_real_meeting_cases: int = 20,
) -> ReleaseGateResult:
    if not isfinite(threshold) or not 0 < threshold <= 1:
        raise ValueError("release threshold must be finite and between 0 and 1")
    if minimum_checks_per_metric <= 0:
        raise ValueError("minimum checks per metric must be positive")
    failures: list[str] = []
    _check_report_identity(
        holdout_report,
        name="frozen holdout",
        expected_kind="frozen_holdout",
        failures=failures,
    )
    _check_report_identity(
        real_meeting_report,
        name="consented real meetings",
        expected_kind="consented_real_meetings",
        failures=failures,
    )
    _check_independence(holdout_report, real_meeting_report, failures)
    _check_extraction_report(
        _summary(holdout_report),
        name="frozen holdout",
        minimum_cases=minimum_holdout_cases,
        threshold=threshold,
        minimum_checks=minimum_checks_per_metric,
        failures=failures,
    )
    _check_extraction_report(
        _summary(real_meeting_report),
        name="consented real meetings",
        minimum_cases=minimum_real_meeting_cases,
        threshold=threshold,
        minimum_checks=minimum_checks_per_metric,
        failures=failures,
    )
    if candidate_gating_enabled:
        _check_candidate_report(candidate_report, failures)
    return ReleaseGateResult(
        ready=not failures,
        threshold=threshold,
        confidence=DEFAULT_CONFIDENCE,
        minimum_checks_per_metric=minimum_checks_per_metric,
        failures=tuple(failures),
    )


def wilson_lower_bound(
    correct: int,
    total: int,
    *,
    z_score: float = DEFAULT_Z_SCORE,
) -> float | None:
    if total <= 0 or correct < 0 or correct > total:
        return None
    observed = correct / total
    z_squared = z_score**2
    denominator = 1 + z_squared / total
    center = observed + z_squared / (2 * total)
    margin = z_score * sqrt(
        observed * (1 - observed) / total + z_squared / (4 * total**2)
    )
    return (center - margin) / denominator


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else {}


def _check_report_identity(
    report: dict[str, Any],
    *,
    name: str,
    expected_kind: str,
    failures: list[str],
) -> None:
    evidence = report.get("evidence")
    if not isinstance(evidence, dict):
        failures.append(f"{name}: evidence metadata is missing")
        return
    if evidence.get("kind") != expected_kind:
        failures.append(f"{name}: evidence kind must be {expected_kind}")
    for field in (
        "dataset_id",
        "dataset_fingerprint",
        "prompt_version",
        "provider",
        "model",
    ):
        if not isinstance(evidence.get(field), str) or not evidence[field].strip():
            failures.append(f"{name}: evidence {field} is missing")
    if evidence.get("prompt_version") != EXTRACTION_PROMPT_VERSION:
        failures.append(
            f"{name}: prompt version must be {EXTRACTION_PROMPT_VERSION}"
        )
    fingerprint = evidence.get("dataset_fingerprint")
    if (
        isinstance(fingerprint, str)
        and (len(fingerprint) != 64 or any(char not in "0123456789abcdef" for char in fingerprint))
    ):
        failures.append(f"{name}: dataset fingerprint must be 64 lowercase hex characters")


def _check_independence(
    holdout_report: dict[str, Any],
    real_meeting_report: dict[str, Any],
    failures: list[str],
) -> None:
    holdout = holdout_report.get("evidence")
    real = real_meeting_report.get("evidence")
    if not isinstance(holdout, dict) or not isinstance(real, dict):
        return
    for field in ("dataset_id", "dataset_fingerprint"):
        left = holdout.get(field)
        right = real.get(field)
        if isinstance(left, str) and left and left == right:
            failures.append(
                f"independent evidence: holdout and real meetings share {field}"
            )
    for field in ("prompt_version", "provider", "model"):
        left = holdout.get(field)
        right = real.get(field)
        if isinstance(left, str) and isinstance(right, str) and left != right:
            failures.append(
                f"comparable evidence: holdout and real meetings use different {field}"
            )


def _check_extraction_report(
    summary: dict[str, Any],
    *,
    name: str,
    minimum_cases: int,
    threshold: float,
    minimum_checks: int,
    failures: list[str],
) -> None:
    case_count = summary.get("case_count")
    if not isinstance(case_count, int) or case_count < minimum_cases:
        failures.append(f"{name}: requires at least {minimum_cases} cases")

    if summary.get("schema_pass_rate") != 1:
        failures.append(f"{name}: schema pass rate must be 100%")
    if summary.get("mean_forbidden_fact_count") != 0:
        failures.append(f"{name}: forbidden fact count must be zero")

    micro_metrics = summary.get("micro_metrics")
    if not isinstance(micro_metrics, dict):
        failures.append(f"{name}: micro metrics are missing")
        return

    for metric_name in CRITICAL_METRICS:
        metric = micro_metrics.get(metric_name)
        if not isinstance(metric, dict):
            failures.append(f"{name}: {metric_name} is missing")
            continue
        correct = metric.get("correct")
        total = metric.get("total")
        value = metric.get("value")
        if (
            not isinstance(correct, int)
            or not isinstance(total, int)
            or correct < 0
            or total < 0
            or correct > total
        ):
            failures.append(f"{name}: {metric_name} counts are invalid")
            continue
        if total < minimum_checks:
            failures.append(
                f"{name}: {metric_name} requires at least {minimum_checks} checks"
            )
        observed = correct / total if total else None
        if (
            not isinstance(value, int | float)
            or not isfinite(value)
            or not 0 <= value <= 1
            or observed is None
            or abs(value - observed) > 1e-12
        ):
            failures.append(f"{name}: {metric_name} value does not match its counts")
            continue
        lower_bound = wilson_lower_bound(correct, total)
        if lower_bound is None or lower_bound < threshold:
            failures.append(
                f"{name}: {metric_name} one-sided 95% lower bound "
                f"must be at least {threshold:.3%}"
            )


def _check_candidate_report(
    report: dict[str, Any] | None,
    failures: list[str],
) -> None:
    if not isinstance(report, dict):
        failures.append("candidate gating: long-meeting report is required")
        return
    evaluator_gate = report.get("release_gate")
    if not isinstance(evaluator_gate, dict) or evaluator_gate.get("passed") is not True:
        failures.append("candidate gating: evaluator release gate must pass")
    evaluated_cases = report.get("case_count")
    if not isinstance(evaluated_cases, int) or evaluated_cases < 20:
        failures.append("candidate gating: at least 20 long meetings are required")
    if report.get("zero_gold_case_count") != 0:
        failures.append("candidate gating: every case must contain gold evidence")
    filtered_gold_cases = report.get("filtered_gold_case_count")
    if not isinstance(filtered_gold_cases, int) or filtered_gold_cases <= 0:
        failures.append(
            "candidate gating: at least one gold-labelled case must be filtered"
        )
    overall = _retention_metric(report.get("gold_evidence_retention"))
    if overall is None or overall["gold"] < 200 or overall["ratio"] != 1:
        failures.append(
            "candidate gating: at least 200 gold evidence segments need 100% retention"
        )
    for field, label in (
        ("decision_evidence_retention", "decision"),
        ("action_evidence_retention", "action"),
        ("case_all_evidence_retention", "case"),
    ):
        metric = _retention_metric(report.get(field))
        if metric is None or metric["gold"] <= 0 or metric["ratio"] != 1:
            failures.append(
                f"candidate gating: {label} evidence retention must be 100% "
                "with a non-zero denominator"
            )


def _retention_metric(value: Any) -> dict[str, int | float] | None:
    if not isinstance(value, dict):
        return None
    retained = value.get("retained")
    gold = value.get("gold")
    ratio = value.get("ratio")
    if (
        not isinstance(retained, int)
        or not isinstance(gold, int)
        or not isinstance(ratio, int | float)
        or retained < 0
        or gold < 0
        or retained > gold
        or (gold and abs(ratio - retained / gold) > 1e-12)
    ):
        return None
    return {"retained": retained, "gold": gold, "ratio": ratio}
