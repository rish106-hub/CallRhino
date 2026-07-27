import argparse
import json
from pathlib import Path
from typing import Any

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

    result = evaluate_release_readiness(
        holdout_summary=_load_summary(args.holdout_report),
        real_meeting_summary=_load_summary(args.real_meeting_report),
        candidate_gating_enabled=args.candidate_gating_enabled,
        candidate_report=(
            _load_json(args.candidate_report) if args.candidate_report else None
        ),
    )
    serialized = json.dumps(result.to_dict(), indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    if not result.ready:
        raise SystemExit(1)


def _load_summary(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    summary = payload.get("summary", payload)
    if not isinstance(summary, dict):
        raise ValueError(f"{path} does not contain an extraction summary")
    return summary


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


if __name__ == "__main__":
    main()
