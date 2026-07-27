import argparse
import json
from pathlib import Path

from callrhino.evaluation.extraction_metrics import (
    score_extraction_case,
    summarize_extraction,
)
from callrhino.evaluation.io import load_model, write_json
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
    args = parser.parse_args()

    cases = load_model(args.cases, ExtractionCaseManifest)
    raw_predictions = json.loads(args.predictions.read_text(encoding="utf-8"))
    predictions = {
        item.case_id: item
        for item in (
            ExtractionPrediction.model_validate(value)
            for value in raw_predictions["predictions"]
        )
    }
    scores = [
        score_extraction_case(case, predictions[case.id])
        for case in cases.cases
        if case.id in predictions
    ]
    summary = summarize_extraction(scores)
    write_json(args.output, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
