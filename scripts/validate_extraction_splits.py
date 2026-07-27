import argparse
import json
from dataclasses import asdict
from pathlib import Path

from callrhino.evaluation.io import load_model
from callrhino.evaluation.models import ExtractionCaseManifest
from callrhino.evaluation.splits import (
    assert_independent_splits,
    validate_split_independence,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reject development and holdout extraction data leakage.",
    )
    parser.add_argument("--development", type=Path, required=True)
    parser.add_argument("--holdout", type=Path, required=True)
    args = parser.parse_args()

    development = load_model(args.development, ExtractionCaseManifest)
    holdout = load_model(args.holdout, ExtractionCaseManifest)
    report = validate_split_independence(development, holdout)
    assert_independent_splits(report)
    print(json.dumps(asdict(report), indent=2))


if __name__ == "__main__":
    main()
