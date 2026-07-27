from pydantic import BaseModel, ConfigDict, Field

from callrhino.domain.models import TranscriptSegment
from callrhino.domain.transcript import segment_transcript
from callrhino.evaluation.models import ExtractionCase, ExtractionCaseManifest
from callrhino.services.candidates import (
    CONTEXT_RADIUS,
    MAX_SELECTION_RATIO,
    MIN_SEGMENTS_TO_FILTER,
    select_candidate_segments,
)
from callrhino.services.prompts import build_extraction_messages

REQUIRED_GOLD_EVIDENCE_RETENTION = 1.0


class EvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RetentionMetric(EvaluationModel):
    retained: int = Field(ge=0)
    gold: int = Field(ge=0)
    ratio: float | None = Field(default=None, ge=0, le=1)


class ReductionMetric(EvaluationModel):
    baseline: int = Field(ge=0)
    selected: int = Field(ge=0)
    selected_ratio: float | None = Field(default=None, ge=0, le=1)
    reduction_ratio: float | None = Field(default=None, ge=0, le=1)


class LongMeetingCaseResult(EvaluationModel):
    case_id: str
    segment_count: int = Field(ge=0)
    selected_segment_count: int = Field(ge=0)
    filtered: bool
    gold_evidence_count: int = Field(ge=0)
    retained_evidence_count: int = Field(ge=0)
    all_evidence_retained: bool | None
    decision_evidence: RetentionMetric
    action_evidence: RetentionMetric
    missed_decision_evidence_ids: list[str]
    missed_action_evidence_ids: list[str]
    segment_selection: ReductionMetric
    prompt_characters: ReductionMetric


class ReleaseGate(EvaluationModel):
    passed: bool
    required_gold_evidence_retention: float = REQUIRED_GOLD_EVIDENCE_RETENTION
    reasons: list[str]


class LongMeetingEvaluation(EvaluationModel):
    case_count: int = Field(ge=0)
    cases_with_gold_evidence: int = Field(ge=0)
    zero_gold_case_count: int = Field(ge=0)
    filtered_case_count: int = Field(ge=0)
    baseline_gold_evidence_retention: RetentionMetric
    gold_evidence_retention: RetentionMetric
    decision_evidence_retention: RetentionMetric
    action_evidence_retention: RetentionMetric
    case_all_evidence_retention: RetentionMetric
    segment_selection: ReductionMetric
    prompt_characters: ReductionMetric
    release_gate: ReleaseGate
    warnings: list[str]
    cases: list[LongMeetingCaseResult]


def evaluate_long_meetings(
    manifest: ExtractionCaseManifest,
    *,
    minimum_segments: int = MIN_SEGMENTS_TO_FILTER,
    context_radius: int = CONTEXT_RADIUS,
    max_selection_ratio: float = MAX_SELECTION_RATIO,
) -> LongMeetingEvaluation:
    """Evaluate the local candidate gate without making provider calls."""
    if minimum_segments < 1:
        raise ValueError("minimum_segments must be at least 1")
    if context_radius < 0:
        raise ValueError("context_radius cannot be negative")
    if not 0 < max_selection_ratio <= 1:
        raise ValueError("max_selection_ratio must be greater than 0 and at most 1")

    case_results = [
        _evaluate_case(
            case,
            minimum_segments=minimum_segments,
            context_radius=context_radius,
            max_selection_ratio=max_selection_ratio,
        )
        for case in manifest.cases
    ]
    gold_count = sum(result.gold_evidence_count for result in case_results)
    retained_count = sum(result.retained_evidence_count for result in case_results)
    decision_retained = sum(result.decision_evidence.retained for result in case_results)
    decision_gold = sum(result.decision_evidence.gold for result in case_results)
    action_retained = sum(result.action_evidence.retained for result in case_results)
    action_gold = sum(result.action_evidence.gold for result in case_results)
    cases_with_gold = [result for result in case_results if result.gold_evidence_count]
    all_evidence_cases = sum(
        result.all_evidence_retained is True for result in cases_with_gold
    )
    filtered_case_count = sum(result.filtered for result in case_results)

    warnings: list[str] = []
    if not case_results:
        warnings.append("NO_CASES: no long-meeting cases were evaluated.")
    if case_results and not gold_count:
        warnings.append(
            "NO_GOLD_EVIDENCE: no decision or action evidence was annotated; "
            "retention is unavailable."
        )
    zero_gold_case_count = len(case_results) - len(cases_with_gold)
    if zero_gold_case_count:
        warnings.append(
            f"ZERO_GOLD_CASES: {zero_gold_case_count} case(s) contain no annotated "
            "decision or action evidence and do not count toward retention."
        )
    if case_results and not filtered_case_count:
        warnings.append(
            "NO_FILTERED_CASES: candidate gating did not filter any evaluated case."
        )

    overall_retention = _retention(retained_count, gold_count)
    case_retention = _retention(all_evidence_cases, len(cases_with_gold))
    gate_reasons = _release_gate_reasons(
        case_count=len(case_results),
        gold_count=gold_count,
        filtered_case_count=filtered_case_count,
        overall_retention=overall_retention,
        case_retention=case_retention,
    )

    return LongMeetingEvaluation(
        case_count=len(case_results),
        cases_with_gold_evidence=len(cases_with_gold),
        zero_gold_case_count=zero_gold_case_count,
        filtered_case_count=filtered_case_count,
        baseline_gold_evidence_retention=_retention(gold_count, gold_count),
        gold_evidence_retention=overall_retention,
        decision_evidence_retention=_retention(decision_retained, decision_gold),
        action_evidence_retention=_retention(action_retained, action_gold),
        case_all_evidence_retention=case_retention,
        segment_selection=_aggregate_reduction(
            case_results,
            field_name="segment_selection",
        ),
        prompt_characters=_aggregate_reduction(
            case_results,
            field_name="prompt_characters",
        ),
        release_gate=ReleaseGate(passed=not gate_reasons, reasons=gate_reasons),
        warnings=warnings,
        cases=case_results,
    )


def _evaluate_case(
    case: ExtractionCase,
    *,
    minimum_segments: int,
    context_radius: int,
    max_selection_ratio: float,
) -> LongMeetingCaseResult:
    segments = segment_transcript(case.transcript)
    baseline = select_candidate_segments(
        segments,
        enabled=False,
        minimum_segments=minimum_segments,
        context_radius=context_radius,
        max_selection_ratio=max_selection_ratio,
    )
    gated = select_candidate_segments(
        segments,
        enabled=True,
        minimum_segments=minimum_segments,
        context_radius=context_radius,
        max_selection_ratio=max_selection_ratio,
    )
    segment_ids = {segment.id for segment in segments}
    decision_ids = _gold_ids(
        case.id,
        "decision",
        [item.evidence_segment_ids for item in case.expected_decisions],
        segment_ids,
    )
    action_ids = _gold_ids(
        case.id,
        "action",
        [item.evidence_segment_ids for item in case.expected_actions],
        segment_ids,
    )
    selected_ids = {segment.id for segment in gated.segments}
    retained_decision_ids = decision_ids & selected_ids
    retained_action_ids = action_ids & selected_ids
    gold_ids = decision_ids | action_ids
    retained_ids = gold_ids & selected_ids

    baseline_prompt_chars = _prompt_characters(case, baseline.segments)
    selected_prompt_chars = _prompt_characters(case, gated.segments)

    return LongMeetingCaseResult(
        case_id=case.id,
        segment_count=len(segments),
        selected_segment_count=len(gated.segments),
        filtered=gated.filtered,
        gold_evidence_count=len(gold_ids),
        retained_evidence_count=len(retained_ids),
        all_evidence_retained=(retained_ids == gold_ids) if gold_ids else None,
        decision_evidence=_retention(len(retained_decision_ids), len(decision_ids)),
        action_evidence=_retention(len(retained_action_ids), len(action_ids)),
        missed_decision_evidence_ids=sorted(decision_ids - selected_ids),
        missed_action_evidence_ids=sorted(action_ids - selected_ids),
        segment_selection=_reduction(len(baseline.segments), len(gated.segments)),
        prompt_characters=_reduction(baseline_prompt_chars, selected_prompt_chars),
    )


def _gold_ids(
    case_id: str,
    item_kind: str,
    evidence_groups: list[list[str]],
    valid_segment_ids: set[str],
) -> set[str]:
    evidence_ids = {segment_id for group in evidence_groups for segment_id in group}
    unknown_ids = sorted(evidence_ids - valid_segment_ids)
    if unknown_ids:
        raise ValueError(
            f"Case {case_id!r} has unknown {item_kind} evidence IDs: {unknown_ids}"
        )
    return evidence_ids


def _prompt_characters(case: ExtractionCase, segments: list[TranscriptSegment]) -> int:
    messages = build_extraction_messages(
        meeting_date=case.meeting_date,
        series_name="Long-meeting evaluation",
        meeting_title=case.title,
        meeting_type=case.meeting_type,
        segments=segments,
    )
    return sum(len(message["content"]) for message in messages)


def _retention(retained: int, gold: int) -> RetentionMetric:
    return RetentionMetric(
        retained=retained,
        gold=gold,
        ratio=retained / gold if gold else None,
    )


def _reduction(baseline: int, selected: int) -> ReductionMetric:
    return ReductionMetric(
        baseline=baseline,
        selected=selected,
        selected_ratio=selected / baseline if baseline else None,
        reduction_ratio=1 - (selected / baseline) if baseline else None,
    )


def _aggregate_reduction(
    cases: list[LongMeetingCaseResult],
    *,
    field_name: str,
) -> ReductionMetric:
    metrics = [getattr(case, field_name) for case in cases]
    return _reduction(
        sum(metric.baseline for metric in metrics),
        sum(metric.selected for metric in metrics),
    )


def _release_gate_reasons(
    *,
    case_count: int,
    gold_count: int,
    filtered_case_count: int,
    overall_retention: RetentionMetric,
    case_retention: RetentionMetric,
) -> list[str]:
    reasons: list[str] = []
    if not case_count:
        reasons.append("At least one long-meeting case is required.")
    if not gold_count:
        reasons.append("At least one decision or action evidence segment is required.")
    if case_count and not filtered_case_count:
        reasons.append("At least one case must be filtered to evaluate candidate gating.")
    if (
        overall_retention.ratio is not None
        and overall_retention.ratio < REQUIRED_GOLD_EVIDENCE_RETENTION
    ):
        reasons.append("Gold evidence segment retention must be 100%.")
    if case_retention.ratio is not None and case_retention.ratio < 1:
        reasons.append("Every case with gold evidence must retain all evidence.")
    return reasons
