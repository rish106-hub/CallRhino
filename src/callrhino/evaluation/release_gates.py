from dataclasses import asdict, dataclass
from typing import Any

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


@dataclass(frozen=True)
class ReleaseGateResult:
    ready: bool
    threshold: float
    minimum_checks_per_metric: int
    failures: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_release_readiness(
    *,
    holdout_summary: dict[str, Any],
    real_meeting_summary: dict[str, Any],
    candidate_gating_enabled: bool = False,
    candidate_report: dict[str, Any] | None = None,
    threshold: float = 0.995,
    minimum_checks_per_metric: int = 200,
    minimum_holdout_cases: int = 50,
    minimum_real_meeting_cases: int = 20,
) -> ReleaseGateResult:
    failures: list[str] = []
    _check_extraction_report(
        holdout_summary,
        name="frozen holdout",
        minimum_cases=minimum_holdout_cases,
        threshold=threshold,
        minimum_checks=minimum_checks_per_metric,
        failures=failures,
    )
    _check_extraction_report(
        real_meeting_summary,
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
        minimum_checks_per_metric=minimum_checks_per_metric,
        failures=tuple(failures),
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
        total = metric.get("total")
        value = metric.get("value")
        if not isinstance(total, int) or total < minimum_checks:
            failures.append(
                f"{name}: {metric_name} requires at least {minimum_checks} checks"
            )
        if not isinstance(value, int | float) or value < threshold:
            failures.append(
                f"{name}: {metric_name} must be at least {threshold:.3%}"
            )


def _check_candidate_report(
    report: dict[str, Any] | None,
    failures: list[str],
) -> None:
    if not isinstance(report, dict):
        failures.append("candidate gating: long-meeting report is required")
        return
    evaluated_cases = report.get("case_count")
    if not isinstance(evaluated_cases, int) or evaluated_cases <= 0:
        failures.append("candidate gating: at least one long meeting is required")
    if report.get("gold_evidence_retention") != 1:
        failures.append("candidate gating: gold evidence retention must be 100%")
    if report.get("case_all_evidence_retention") != 1:
        failures.append("candidate gating: every case must retain all gold evidence")
