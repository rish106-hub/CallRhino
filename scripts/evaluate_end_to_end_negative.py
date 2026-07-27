import argparse
import json
import time
from datetime import date
from pathlib import Path

from callrhino.config import Settings
from callrhino.domain.transcript import segment_transcript
from callrhino.evaluation.io import load_model, write_json
from callrhino.evaluation.models import SttCaseManifest
from callrhino.services.extraction import BriefValidationError, MeetingExtractor
from callrhino.services.sarvam import SarvamChatClient

INPUT_PRICE = 4.0
OUTPUT_PRICE = 16.0
CONSERVATIVE_COST_CEILING_INR = 0.5


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a public Hinglish audio-to-record negative control.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("evals/cache/mucs_hinglish/manifest.json"),
    )
    parser.add_argument(
        "--stt-results",
        type=Path,
        default=Path("evals/results/stt_sarvam_saaras_v3_codemix.json"),
    )
    parser.add_argument("--max-cost-inr", type=float, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/results/end_to_end_mucs_negative.json"),
    )
    args = parser.parse_args()
    if args.max_cost_inr < CONSERVATIVE_COST_CEILING_INR:
        raise SystemExit(
            f"Refusing provider calls: conservative ceiling "
            f"₹{CONSERVATIVE_COST_CEILING_INR:.2f} exceeds cap."
        )

    manifest = load_model(args.manifest, SttCaseManifest)
    raw_results = json.loads(args.stt_results.read_text(encoding="utf-8"))
    predicted = {
        item["case_id"]: item["transcript"] for item in raw_results["predictions"]
    }
    gold_transcript = "\n".join(
        f"Narrator: {case.reference}" for case in manifest.cases
    )
    stt_transcript = "\n".join(
        f"Narrator: {predicted[case.id]}" for case in manifest.cases
    )

    settings = Settings(SARVAM_CHAT_MODEL="sarvam-105b")
    records = []
    with SarvamChatClient(settings) as client:
        extractor = MeetingExtractor(client, max_repairs=1)
        records.append(_extract("gold_transcript", gold_transcript, extractor))
        records.append(_extract("sarvam_codemix_transcript", stt_transcript, extractor))

    total_cost = sum(record["cost_inr"] for record in records)
    output = {
        "source": "MUCS-Hinglish public audio",
        "test_type": "negative_control",
        "expected_decisions": 0,
        "expected_actions": 0,
        "total_cost_inr": total_cost,
        "records": records,
    }
    write_json(args.output, output)
    print(json.dumps(output, ensure_ascii=False, indent=2))


def _extract(
    label: str,
    transcript: str,
    extractor: MeetingExtractor,
) -> dict:
    started = time.perf_counter()
    try:
        result = extractor.extract(
            meeting_date=date(2026, 7, 27),
            series_name="Public ASR negative control",
            meeting_title="Technical tutorial, not a meeting",
            meeting_type="non_meeting_negative_control",
            segments=segment_transcript(transcript),
        )
    except BriefValidationError as exc:
        return {
            "label": label,
            "schema_valid": False,
            "error": str(exc),
            "latency_seconds": time.perf_counter() - started,
            "cost_inr": _cost(
                exc.usage.prompt_tokens,
                exc.usage.completion_tokens,
            ),
        }
    return {
        "label": label,
        "schema_valid": True,
        "repaired": result.repaired,
        "decision_count": len(result.brief.decisions),
        "action_count": len(result.brief.action_items),
        "open_question_count": len(result.brief.open_questions),
        "risk_count": len(result.brief.risks),
        "latency_seconds": time.perf_counter() - started,
        "prompt_tokens": result.usage.prompt_tokens,
        "completion_tokens": result.usage.completion_tokens,
        "cost_inr": _cost(
            result.usage.prompt_tokens,
            result.usage.completion_tokens,
        ),
    }


def _cost(prompt_tokens: int, completion_tokens: int) -> float:
    return (prompt_tokens * INPUT_PRICE + completion_tokens * OUTPUT_PRICE) / 1_000_000


if __name__ == "__main__":
    main()
