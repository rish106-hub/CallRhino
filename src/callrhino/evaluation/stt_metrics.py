from dataclasses import asdict, dataclass
from statistics import median

from callrhino.evaluation.models import SttCase, SttPrediction
from callrhino.evaluation.text_metrics import (
    character_error_rate,
    phrase_recall,
    token_precision_recall,
    word_error_rate,
)


@dataclass(frozen=True)
class SttCaseScore:
    case_id: str
    wer: float
    cer: float
    reference_token_precision: float
    reference_token_recall: float
    english_term_recall: float | None
    entity_recall: float | None
    real_time_factor: float
    degenerate_repetition: bool
    estimated_cost_inr: float


def score_stt_case(case: SttCase, prediction: SttPrediction) -> SttCaseScore:
    token_precision, token_recall = token_precision_recall(
        case.reference,
        prediction.transcript,
    )
    return SttCaseScore(
        case_id=case.id,
        wer=word_error_rate(case.reference, prediction.transcript),
        cer=character_error_rate(case.reference, prediction.transcript),
        reference_token_precision=token_precision,
        reference_token_recall=token_recall,
        english_term_recall=(
            phrase_recall(case.english_terms, prediction.transcript)
            if case.english_terms
            else None
        ),
        entity_recall=(
            phrase_recall(case.entities, prediction.transcript)
            if case.entities
            else None
        ),
        real_time_factor=prediction.latency_seconds / prediction.audio_duration_seconds,
        degenerate_repetition=_has_degenerate_repetition(prediction.transcript),
        estimated_cost_inr=prediction.estimated_cost_inr,
    )


def summarize_stt(scores: list[SttCaseScore]) -> dict:
    if not scores:
        return {"case_count": 0}
    fields = (
        "wer",
        "cer",
        "reference_token_precision",
        "reference_token_recall",
        "english_term_recall",
        "entity_recall",
        "real_time_factor",
        "estimated_cost_inr",
    )
    summary = {"case_count": len(scores)}
    for field in fields:
        values = [
            value
            for score in scores
            if (value := getattr(score, field)) is not None
        ]
        summary[f"mean_{field}"] = sum(values) / len(values) if values else None
        summary[f"{field}_case_count"] = len(values)
    summary["median_wer"] = median(score.wer for score in scores)
    summary["median_real_time_factor"] = median(score.real_time_factor for score in scores)
    summary["warm_mean_real_time_factor"] = (
        sum(score.real_time_factor for score in scores[1:]) / len(scores[1:])
        if len(scores) > 1
        else scores[0].real_time_factor
    )
    summary["degenerate_repetition_rate"] = (
        sum(score.degenerate_repetition for score in scores) / len(scores)
    )
    summary["cases"] = [asdict(score) for score in scores]
    return summary


def _has_degenerate_repetition(text: str) -> bool:
    tokens = text.casefold().split()
    if len(tokens) < 10:
        return False
    return max(tokens.count(token) for token in set(tokens)) / len(tokens) >= 0.25
