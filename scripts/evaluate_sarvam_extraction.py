import argparse
import json
import time
from pathlib import Path

from callrhino.config import Settings
from callrhino.domain.models import MeetingBrief
from callrhino.domain.transcript import segment_transcript
from callrhino.evaluation.extraction_metrics import (
    score_extraction_case,
    summarize_extraction,
)
from callrhino.evaluation.io import load_model, write_json
from callrhino.evaluation.models import (
    ExtractionCase,
    ExtractionCaseManifest,
    ExtractionPrediction,
)
from callrhino.services.extraction import BriefValidationError, MeetingExtractor
from callrhino.services.prompts import EXTRACTION_PROMPT_VERSION, build_extraction_messages
from callrhino.services.sarvam import (
    SarvamChatClient,
    SarvamError,
    SarvamResponseError,
)

MODEL_PRICING = {
    "sarvam-30b": (2.5, 10.0),
    "sarvam-105b": (4.0, 16.0),
}
MAX_OUTPUT_TOKENS_PER_ATTEMPT = 4096


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate Sarvam meeting extraction with a hard cost cap.",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("evals/cases/indian_meetings.json"),
    )
    parser.add_argument("--max-cost-inr", type=float, required=True)
    parser.add_argument(
        "--model",
        choices=sorted(MODEL_PRICING),
        default="sarvam-30b",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/results/extraction_sarvam_30b.json"),
    )
    args = parser.parse_args()

    cases = load_model(args.cases, ExtractionCaseManifest)
    pricing = MODEL_PRICING[args.model]
    estimated_ceiling = sum(
        _case_cost_ceiling(case, pricing=pricing) for case in cases.cases
    )
    if estimated_ceiling > args.max_cost_inr:
        raise SystemExit(
            f"Refusing provider calls: conservative ceiling ₹{estimated_ceiling:.4f} "
            f"exceeds ₹{args.max_cost_inr:.4f} cap."
        )

    predictions: list[ExtractionPrediction] = []
    scores = []
    running_cost = 0.0
    settings = Settings(SARVAM_CHAT_MODEL=args.model)
    with SarvamChatClient(settings) as client:
        extractor = MeetingExtractor(client, max_repairs=1)
        for case in cases.cases:
            started = time.perf_counter()
            try:
                result = extractor.extract(
                    meeting_date=case.meeting_date,
                    series_name="CallRhino evaluation",
                    meeting_title=case.title,
                    meeting_type=case.meeting_type,
                    segments=segment_transcript(case.transcript),
                )
                latency = time.perf_counter() - started
                cost = _actual_cost(
                    result.usage.prompt_tokens,
                    result.usage.completion_tokens,
                    pricing=pricing,
                )
                running_cost += cost
                prediction = ExtractionPrediction(
                    case_id=case.id,
                    provider="sarvam",
                    model=result.model,
                    latency_seconds=latency,
                    schema_valid=True,
                    repaired=result.repaired,
                    prompt_tokens=result.usage.prompt_tokens,
                    completion_tokens=result.usage.completion_tokens,
                    estimated_cost_inr=cost,
                    brief=result.brief.model_dump(mode="json"),
                )
            except (BriefValidationError, SarvamError) as exc:
                latency = time.perf_counter() - started
                usage = (
                    exc.usage
                    if isinstance(exc, BriefValidationError | SarvamResponseError)
                    else None
                )
                cost = (
                    _actual_cost(
                        usage.prompt_tokens,
                        usage.completion_tokens,
                        pricing=pricing,
                    )
                    if usage
                    else 0
                )
                running_cost += cost
                prediction = ExtractionPrediction(
                    case_id=case.id,
                    provider="sarvam",
                    model=settings.sarvam_chat_model,
                    latency_seconds=latency,
                    schema_valid=False,
                    prompt_tokens=usage.prompt_tokens if usage else 0,
                    completion_tokens=usage.completion_tokens if usage else 0,
                    estimated_cost_inr=cost,
                    error=str(exc),
                )
            predictions.append(prediction)
            score = score_extraction_case(case, prediction)
            scores.append(score)
            print(
                f"{case.id}: schema={score.schema_valid}, "
                f"decision_recall={score.decision_recall:.3f}, "
                f"action_recall={score.action_recall:.3f}, "
                f"cost=₹{prediction.estimated_cost_inr:.4f}"
            )

    output = {
        "provider": "sarvam",
        "model": settings.sarvam_chat_model,
        "prompt_version": EXTRACTION_PROMPT_VERSION,
        "conservative_cost_ceiling_inr": estimated_ceiling,
        "actual_total_cost_inr": running_cost,
        "summary": summarize_extraction(scores),
        "predictions": [item.model_dump(mode="json") for item in predictions],
    }
    write_json(args.output, output)
    print(json.dumps(output["summary"], ensure_ascii=False, indent=2))


def _case_cost_ceiling(
    case: ExtractionCase,
    *,
    pricing: tuple[float, float],
) -> float:
    segments = segment_transcript(case.transcript)
    messages = build_extraction_messages(
        meeting_date=case.meeting_date,
        series_name="CallRhino evaluation",
        meeting_title=case.title,
        meeting_type=case.meeting_type,
        segments=segments,
    )
    prompt_chars = len(json.dumps(messages, ensure_ascii=False))
    schema_chars = len(json.dumps(MeetingBrief.model_json_schema(), ensure_ascii=False))
    estimated_input_tokens = (prompt_chars + schema_chars) / 4
    attempts = 2
    input_price, output_price = pricing
    return (
        estimated_input_tokens
        * attempts
        * input_price
        / 1_000_000
        + MAX_OUTPUT_TOKENS_PER_ATTEMPT
        * attempts
        * output_price
        / 1_000_000
    )


def _actual_cost(
    prompt_tokens: int,
    completion_tokens: int,
    *,
    pricing: tuple[float, float],
) -> float:
    input_price, output_price = pricing
    return (
        prompt_tokens * input_price
        + completion_tokens * output_price
    ) / 1_000_000


if __name__ == "__main__":
    main()
