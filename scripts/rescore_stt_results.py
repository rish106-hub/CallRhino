import argparse
import json
from pathlib import Path

from callrhino.evaluation.io import load_model, write_json
from callrhino.evaluation.models import (
    SttCaseManifest,
    SttPrediction,
)
from callrhino.evaluation.stt_metrics import score_stt_case, summarize_stt


def main() -> None:
    parser = argparse.ArgumentParser(description="Recompute STT metrics from saved predictions.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("evals/cache/mucs_hinglish/manifest.json"),
    )
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = load_model(args.manifest, SttCaseManifest)
    raw = json.loads(args.results.read_text(encoding="utf-8"))
    predictions = {
        item.case_id: item
        for item in (
            SttPrediction.model_validate(value) for value in raw["predictions"]
        )
    }
    scores = [
        score_stt_case(case, predictions[case.id])
        for case in manifest.cases
        if case.id in predictions
    ]
    raw["summary"] = summarize_stt(scores)
    write_json(args.output, raw)
    print(json.dumps(raw["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
