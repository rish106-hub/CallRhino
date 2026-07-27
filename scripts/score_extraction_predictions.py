import argparse
import json
from pathlib import Path

from callrhino.evaluation.evidence import evidence_metadata, manifest_fingerprint
from callrhino.evaluation.extraction_metrics import (
    score_extraction_case,
    summarize_extraction,
)
from callrhino.evaluation.io import (
    load_model,
    require_distinct_paths,
    write_json,
)
from callrhino.evaluation.models import (
    ExtractionCaseManifest,
    ExtractionPrediction,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Score saved extraction predictions.")
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("evals/cases/indian_meetings.json"),
    )
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--evidence-kind",
        choices=["development", "consented_real_meetings"],
        default="development",
    )
    parser.add_argument("--dataset-id")
    args = parser.parse_args()

    require_distinct_paths(
        inputs={"--cases": args.cases, "--predictions": args.predictions},
        outputs={"--output": args.output},
    )
    cases = load_model(args.cases, ExtractionCaseManifest)
    raw_predictions = json.loads(args.predictions.read_text(encoding="utf-8"))
    prediction_items = [
        ExtractionPrediction.model_validate(value)
        for value in raw_predictions["predictions"]
    ]
    prediction_ids = [item.case_id for item in prediction_items]
    duplicate_ids = sorted(
        case_id for case_id in set(prediction_ids) if prediction_ids.count(case_id) > 1
    )
    expected_ids = {case.id for case in cases.cases}
    actual_ids = set(prediction_ids)
    if duplicate_ids:
        raise ValueError(f"Duplicate prediction IDs: {', '.join(duplicate_ids)}")
    if expected_ids != actual_ids:
        missing = sorted(expected_ids - actual_ids)
        extra = sorted(actual_ids - expected_ids)
        problems = []
        if missing:
            problems.append(f"missing: {', '.join(missing)}")
        if extra:
            problems.append(f"extra: {', '.join(extra)}")
        raise ValueError("Prediction case set mismatch: " + "; ".join(problems))
    predictions = {item.case_id: item for item in prediction_items}
    scores = [
        score_extraction_case(case, predictions[case.id])
        for case in cases.cases
    ]
    summary = summarize_extraction(scores)
    output = {
        "evidence": evidence_metadata(
            kind=args.evidence_kind,
            dataset_id=args.dataset_id or args.cases.stem,
            dataset_fingerprint=manifest_fingerprint(cases),
            prompt_version=raw_predictions.get("prompt_version"),
            provider=raw_predictions.get("provider"),
            model=raw_predictions.get("model"),
        ),
        "summary": summary,
    }
    write_json(args.output, output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
