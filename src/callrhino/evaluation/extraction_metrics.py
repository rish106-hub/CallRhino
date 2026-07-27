from dataclasses import asdict, dataclass
from typing import Any

from callrhino.evaluation.models import ExtractionCase, ExtractionPrediction
from callrhino.evaluation.text_metrics import normalize_text, token_f1

MATCH_THRESHOLD = 0.48


@dataclass(frozen=True)
class ExtractionCaseScore:
    case_id: str
    schema_valid: bool
    decision_precision: float
    decision_recall: float
    action_precision: float
    action_recall: float
    owner_accuracy: float
    classification_accuracy: float
    decision_date_accuracy: float
    deadline_accuracy: float
    evidence_accuracy: float
    forbidden_fact_count: int
    estimated_cost_inr: float
    latency_seconds: float


def score_extraction_case(
    case: ExtractionCase,
    prediction: ExtractionPrediction,
) -> ExtractionCaseScore:
    brief = prediction.brief or {}
    actual_decisions = brief.get("decisions", [])
    actual_actions = brief.get("action_items", [])
    if not prediction.schema_valid:
        return ExtractionCaseScore(
            case_id=case.id,
            schema_valid=False,
            decision_precision=0,
            decision_recall=0,
            action_precision=0,
            action_recall=0,
            owner_accuracy=0,
            classification_accuracy=0,
            decision_date_accuracy=0,
            deadline_accuracy=0,
            evidence_accuracy=0,
            forbidden_fact_count=0,
            estimated_cost_inr=prediction.estimated_cost_inr,
            latency_seconds=prediction.latency_seconds,
        )

    decision_matches = _greedy_matches(
        [item.text for item in case.expected_decisions],
        [str(item.get("text", "")) for item in actual_decisions],
    )
    action_matches = _greedy_matches(
        [item.task for item in case.expected_actions],
        [str(item.get("task", "")) for item in actual_actions],
    )

    decision_match_map = {expected: actual for expected, actual, _ in decision_matches}
    action_match_map = {expected: actual for expected, actual, _ in action_matches}
    owner_checks: list[bool] = []
    classification_checks: list[bool] = []
    decision_date_checks: list[bool] = []
    deadline_checks: list[bool] = []
    evidence_checks: list[bool] = []

    for expected_index, expected in enumerate(case.expected_decisions):
        actual_index = decision_match_map.get(expected_index)
        actual = actual_decisions[actual_index] if actual_index is not None else None
        owner_checks.append(
            bool(actual)
            and _same_optional_text(
                expected.decision_maker_text,
                actual.get("decision_maker_text"),
            )
        )
        classification_checks.append(bool(actual) and expected.status == actual.get("status"))
        decision_date_checks.append(
            bool(actual)
            and _same_optional_text(
                (
                    expected.effective_date.isoformat()
                    if expected.effective_date
                    else expected.effective_date_text
                ),
                actual.get("effective_date") or actual.get("effective_date_text"),
            )
            and expected.date_precision == actual.get("date_precision")
        )
        evidence_checks.append(
            bool(actual)
            and set(expected.evidence_segment_ids)
            == set(actual.get("evidence_segment_ids", []))
        )

    for expected_index, expected in enumerate(case.expected_actions):
        actual_index = action_match_map.get(expected_index)
        actual = actual_actions[actual_index] if actual_index is not None else None
        owner_checks.append(
            bool(actual)
            and _same_optional_text(expected.owner_text, actual.get("owner_text"))
            and _same_optional_text(
                expected.suggested_owner_text,
                actual.get("suggested_owner_text"),
            )
        )
        classification_checks.append(
            bool(actual) and expected.commitment_status == actual.get("commitment_status")
        )
        deadline_checks.append(
            bool(actual)
            and _same_optional_text(
                expected.due_date.isoformat() if expected.due_date else expected.due_text,
                actual.get("due_date") or actual.get("due_text"),
            )
            and expected.deadline_precision == actual.get("deadline_precision")
        )
        evidence_checks.append(
            bool(actual)
            and set(expected.evidence_segment_ids)
            == set(actual.get("evidence_segment_ids", []))
        )

    serialized = normalize_text(str(brief))
    forbidden_count = sum(
        normalize_text(fact) in serialized for fact in case.forbidden_facts
    )
    return ExtractionCaseScore(
        case_id=case.id,
        schema_valid=prediction.schema_valid,
        decision_precision=_ratio(len(decision_matches), len(actual_decisions)),
        decision_recall=_ratio(len(decision_matches), len(case.expected_decisions)),
        action_precision=_ratio(len(action_matches), len(actual_actions)),
        action_recall=_ratio(len(action_matches), len(case.expected_actions)),
        owner_accuracy=_mean_bools(owner_checks),
        classification_accuracy=_mean_bools(classification_checks),
        decision_date_accuracy=_mean_bools(decision_date_checks),
        deadline_accuracy=_mean_bools(deadline_checks),
        evidence_accuracy=_mean_bools(evidence_checks),
        forbidden_fact_count=forbidden_count,
        estimated_cost_inr=prediction.estimated_cost_inr,
        latency_seconds=prediction.latency_seconds,
    )


def summarize_extraction(scores: list[ExtractionCaseScore]) -> dict[str, Any]:
    if not scores:
        return {"case_count": 0}
    numeric_fields = (
        "decision_precision",
        "decision_recall",
        "action_precision",
        "action_recall",
        "owner_accuracy",
        "classification_accuracy",
        "decision_date_accuracy",
        "deadline_accuracy",
        "evidence_accuracy",
        "forbidden_fact_count",
        "estimated_cost_inr",
        "latency_seconds",
    )
    summary: dict[str, Any] = {
        "case_count": len(scores),
        "schema_pass_rate": sum(score.schema_valid for score in scores) / len(scores),
    }
    for field in numeric_fields:
        summary[f"mean_{field}"] = sum(getattr(score, field) for score in scores) / len(scores)
    summary["cases"] = [asdict(score) for score in scores]
    return summary


def _greedy_matches(
    expected: list[str],
    actual: list[str],
) -> list[tuple[int, int, float]]:
    candidates = [
        (expected_index, actual_index, token_f1(expected_text, actual_text))
        for expected_index, expected_text in enumerate(expected)
        for actual_index, actual_text in enumerate(actual)
    ]
    matches: list[tuple[int, int, float]] = []
    used_expected: set[int] = set()
    used_actual: set[int] = set()
    for expected_index, actual_index, score in sorted(
        candidates,
        key=lambda item: item[2],
        reverse=True,
    ):
        if score < MATCH_THRESHOLD:
            break
        if expected_index in used_expected or actual_index in used_actual:
            continue
        matches.append((expected_index, actual_index, score))
        used_expected.add(expected_index)
        used_actual.add(actual_index)
    return matches


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else float(numerator == 0)


def _mean_bools(values: list[bool]) -> float:
    return sum(values) / len(values) if values else 1.0


def _same_optional_text(expected: str | None, actual: object) -> bool:
    if expected is None:
        return actual is None
    return normalize_text(expected) == normalize_text(str(actual or ""))
