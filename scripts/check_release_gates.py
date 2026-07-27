import argparse
import json
from pathlib import Path
from typing import Any

from callrhino.evaluation.io import require_distinct_paths
from callrhino.evaluation.release_gates import evaluate_release_readiness


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fail unless CallRhino has enough independent release evidence.",
    )
    parser.add_argument("--holdout-report", type=Path, required=True)
    parser.add_argument("--real-meeting-report", type=Path, required=True)
    parser.add_argument("--candidate-report", type=Path)
    parser.add_argument("--candidate-gating-enabled", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        if args.output:
            inputs = {
                "--holdout-report": args.holdout_report,
                "--real-meeting-report": args.real_meeting_report,
            }
            if args.candidate_report:
                inputs["--candidate-report"] = args.candidate_report
            require_distinct_paths(inputs=inputs, outputs={"--output": args.output})

        result = evaluate_release_readiness(
            holdout_report=_load_json(args.holdout_report),
            real_meeting_report=_load_json(args.real_meeting_report),
            candidate_gating_enabled=args.candidate_gating_enabled,
            candidate_report=(
                _load_json(args.candidate_report) if args.candidate_report else None
            ),
        )
        serialized = json.dumps(result.to_dict(), indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(serialized + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    print(serialized)
    if not result.ready:
        raise SystemExit(1)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


if __name__ == "__main__":
    main()
