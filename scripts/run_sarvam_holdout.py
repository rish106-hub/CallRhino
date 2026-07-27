import argparse
import json
import time
from math import isfinite
from pathlib import Path

from callrhino.config import Settings
from callrhino.domain.transcript import segment_transcript
from callrhino.evaluation.holdout import (
    HoldoutPrediction,
    HoldoutPredictionPackage,
    PublicHoldoutPackage,
    validate_public_package,
)
from callrhino.evaluation.io import load_model, require_distinct_paths, write_json
from callrhino.evaluation.provider_costs import (
    HOLDOUT_MAX_OUTPUT_TOKENS,
    SARVAM_MODEL_CONTEXT_TOKENS,
    SARVAM_MODEL_PRICING_INR_PER_MILLION,
    sarvam_actual_cost,
    sarvam_holdout_cost_ceiling,
)
from callrhino.services.extraction import BriefValidationError, MeetingExtractor
from callrhino.services.prompts import EXTRACTION_PROMPT_VERSION
from callrhino.services.sarvam import (
    SarvamChatClient,
    SarvamError,
    SarvamResponseError,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run canonical Sarvam extraction on a public blind holdout package.",
    )
    parser.add_argument("--public-package", type=Path, required=True)
    parser.add_argument("--max-cost-inr", type=float, required=True)
    parser.add_argument(
        "--model",
        choices=sorted(SARVAM_MODEL_PRICING_INR_PER_MILLION),
        default="sarvam-105b",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not isfinite(args.max_cost_inr) or args.max_cost_inr < 0:
        parser.error("--max-cost-inr must be a finite, non-negative number.")
    try:
        require_distinct_paths(
            inputs={"--public-package": args.public_package},
            outputs={"--output": args.output},
        )
    except ValueError as exc:
        parser.error(str(exc))

    package = load_model(args.public_package, PublicHoldoutPackage)
    validate_public_package(package)
    pricing = SARVAM_MODEL_PRICING_INR_PER_MILLION[args.model]
    cost_ceiling = sum(
        sarvam_holdout_cost_ceiling(
            case,
            pricing,
            retry_input_token_ceiling=SARVAM_MODEL_CONTEXT_TOKENS[args.model],
        )
        for case in package.cases
    )
    if cost_ceiling > args.max_cost_inr:
        raise SystemExit(
            f"Refusing provider calls: conservative ceiling ₹{cost_ceiling:.4f} "
            f"exceeds ₹{args.max_cost_inr:.4f} cap."
        )

    settings = Settings(
        SARVAM_CHAT_MODEL=args.model,
        SARVAM_MAX_OUTPUT_TOKENS=HOLDOUT_MAX_OUTPUT_TOKENS,
    )
    predictions: list[HoldoutPrediction] = []
    total_cost = 0.0
    _write_progress(args.output, package.package_id, predictions, total_cost)
    try:
        with SarvamChatClient(settings) as client:
            extractor = MeetingExtractor(client, max_repairs=1)
            for case in package.cases:
                started = time.perf_counter()
                try:
                    result = extractor.extract(
                        meeting_date=case.meeting_date,
                        series_name="Blind holdout",
                        meeting_title=case.title,
                        meeting_type=case.meeting_type,
                        segments=segment_transcript(case.transcript),
                    )
                    latency = time.perf_counter() - started
                    cost = sarvam_actual_cost(
                        result.usage.prompt_tokens,
                        result.usage.completion_tokens,
                        pricing,
                    )
                    prediction = HoldoutPrediction(
                        case_id=case.id,
                        input_fingerprint=case.input_fingerprint,
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
                        sarvam_actual_cost(
                            usage.prompt_tokens,
                            usage.completion_tokens,
                            pricing,
                        )
                        if usage
                        else 0
                    )
                    prediction = HoldoutPrediction(
                        case_id=case.id,
                        input_fingerprint=case.input_fingerprint,
                        provider="sarvam",
                        model=args.model,
                        latency_seconds=latency,
                        schema_valid=False,
                        prompt_tokens=usage.prompt_tokens if usage else 0,
                        completion_tokens=usage.completion_tokens if usage else 0,
                        estimated_cost_inr=cost,
                        error=str(exc),
                    )
                total_cost += cost
                predictions.append(prediction)
                _write_progress(
                    args.output,
                    package.package_id,
                    predictions,
                    total_cost,
                )
    finally:
        _write_progress(args.output, package.package_id, predictions, total_cost)
    print(
        json.dumps(
            {
                "package_id": package.package_id,
                "case_count": len(predictions),
                "schema_valid_count": sum(item.schema_valid for item in predictions),
                "actual_total_cost_inr": total_cost,
            },
            indent=2,
        )
    )


def _write_progress(
    path: Path,
    package_id: str,
    predictions: list[HoldoutPrediction],
    total_cost: float,
) -> None:
    write_json(
        path,
        HoldoutPredictionPackage(
            package_id=package_id,
            prompt_version=EXTRACTION_PROMPT_VERSION,
            actual_total_cost_inr=total_cost,
            predictions=predictions,
        ),
    )


if __name__ == "__main__":
    main()
