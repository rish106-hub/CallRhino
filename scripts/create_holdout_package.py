import argparse
from pathlib import Path

from pydantic import ValidationError

from callrhino.evaluation.holdout import (
    HoldoutPackageError,
    create_holdout_packages,
)
from callrhino.evaluation.io import load_model, write_json
from callrhino.evaluation.models import ExtractionCaseManifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create separate public-input and private-gold holdout packages.",
    )
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument("--gold-output", type=Path, required=True)
    args = parser.parse_args()

    if args.public_output.resolve() == args.gold_output.resolve():
        parser.error("Public and private gold outputs must use different paths.")

    try:
        manifest = load_model(args.cases, ExtractionCaseManifest)
        public_package, gold_package = create_holdout_packages(manifest)
        write_json(args.public_output, public_package)
        write_json(args.gold_output, gold_package)
    except (OSError, ValidationError, HoldoutPackageError) as exc:
        parser.error(str(exc))

    print(f"Created {public_package.package_id} with {len(public_package.cases)} cases.")
    print(f"Public input: {args.public_output}")
    print(f"Private gold: {args.gold_output}")


if __name__ == "__main__":
    main()
