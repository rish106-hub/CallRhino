import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from callrhino.evaluation.holdout import (
    HoldoutPackageError,
    HoldoutPredictionPackage,
    PrivateGoldPackage,
    score_holdout_package,
)
from callrhino.evaluation.io import load_model, require_distinct_paths, write_json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score fingerprinted holdout predictions against private gold labels.",
    )
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        require_distinct_paths(
            inputs={
                "--gold": args.gold,
                "--predictions": args.predictions,
            },
            outputs={"--output": args.output},
        )
        gold = load_model(args.gold, PrivateGoldPackage)
        predictions = load_model(args.predictions, HoldoutPredictionPackage)
        result = score_holdout_package(gold, predictions)
        write_json(args.output, result)
    except (OSError, ValidationError, HoldoutPackageError) as exc:
        parser.error(str(exc))

    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
