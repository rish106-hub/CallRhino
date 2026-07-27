import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from callrhino.annotation import (
    AnnotationRepositoryError,
    CoveragePlan,
    JsonAnnotationRepository,
    evaluate_coverage,
)
from callrhino.evaluation.io import load_model, require_distinct_paths, write_json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report remaining consented annotation coverage requirements.",
    )
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("data/annotations"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()

    try:
        if args.output:
            require_distinct_paths(
                inputs={"--plan": args.plan},
                outputs={"--output": args.output},
            )
        plan = load_model(args.plan, CoveragePlan)
        records = JsonAnnotationRepository(args.root).list_records()
        report = evaluate_coverage(plan, records)
        if args.output:
            write_json(args.output, report)
    except (OSError, ValidationError, AnnotationRepositoryError, ValueError) as exc:
        parser.error(str(exc))

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    if args.require_complete and not report.complete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
