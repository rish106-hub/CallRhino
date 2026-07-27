import argparse
import json
from pathlib import Path

from callrhino.evaluation.io import load_model, write_json
from callrhino.evaluation.long_meetings import evaluate_long_meetings
from callrhino.evaluation.models import ExtractionCaseManifest
from callrhino.services.candidates import (
    CONTEXT_RADIUS,
    MAX_SELECTION_RATIO,
    MIN_SEGMENTS_TO_FILTER,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate candidate-gate evidence retention and prompt reduction locally. "
            "This command makes no provider calls."
        ),
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("evals/cases/long_meetings.template.json"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--minimum-segments", type=int, default=MIN_SEGMENTS_TO_FILTER)
    parser.add_argument("--context-radius", type=int, default=CONTEXT_RADIUS)
    parser.add_argument(
        "--max-selection-ratio",
        type=float,
        default=MAX_SELECTION_RATIO,
    )
    parser.add_argument(
        "--require-gate",
        action="store_true",
        help="Exit unsuccessfully when the 100%% evidence-retention gate does not pass.",
    )
    args = parser.parse_args()

    manifest = load_model(args.cases, ExtractionCaseManifest)
    report = evaluate_long_meetings(
        manifest,
        minimum_segments=args.minimum_segments,
        context_radius=args.context_radius,
        max_selection_ratio=args.max_selection_ratio,
    )
    if args.output:
        write_json(args.output, report)
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.require_gate and not report.release_gate.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
