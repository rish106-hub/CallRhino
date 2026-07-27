import argparse
import json
import math
import time
from pathlib import Path

from callrhino.config import Settings
from callrhino.evaluation.audio import wav_duration_seconds
from callrhino.evaluation.io import load_model, write_json
from callrhino.evaluation.models import SttCaseManifest, SttPrediction
from callrhino.evaluation.stt_metrics import score_stt_case, summarize_stt
from callrhino.services.speech import SarvamSpeechClient

SARVAM_STT_INR_PER_HOUR = 30


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Sarvam Saaras STT with a cost cap.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("evals/cache/mucs_hinglish/manifest.json"),
    )
    parser.add_argument("--mode", choices=["transcribe", "codemix"], default="codemix")
    parser.add_argument("--language-code", default="unknown")
    parser.add_argument("--max-cost-inr", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = load_model(args.manifest, SttCaseManifest)
    durations = {
        case.id: wav_duration_seconds(case.audio_path) for case in manifest.cases
    }
    estimated_total = sum(
        math.ceil(duration) * SARVAM_STT_INR_PER_HOUR / 3600
        for duration in durations.values()
    )
    if estimated_total > args.max_cost_inr:
        raise SystemExit(
            f"Refusing provider calls: estimated ₹{estimated_total:.4f} exceeds "
            f"₹{args.max_cost_inr:.4f} cap."
        )

    settings = Settings()
    predictions: list[SttPrediction] = []
    scores = []
    with SarvamSpeechClient(settings) as client:
        for case in manifest.cases:
            started = time.perf_counter()
            result = client.transcribe(
                case.audio_path,
                mode=args.mode,
                language_code=args.language_code,
            )
            latency = time.perf_counter() - started
            cost = (
                math.ceil(durations[case.id]) * SARVAM_STT_INR_PER_HOUR / 3600
            )
            prediction = SttPrediction(
                case_id=case.id,
                provider="sarvam",
                model=result.model,
                transcript=result.transcript,
                latency_seconds=latency,
                audio_duration_seconds=durations[case.id],
                estimated_cost_inr=cost,
            )
            predictions.append(prediction)
            scores.append(score_stt_case(case, prediction))
            print(
                f"{case.id}: WER={scores[-1].wer:.3f}, "
                f"RTF={scores[-1].real_time_factor:.3f}, cost=₹{cost:.4f}"
            )

    output = {
        "provider": "sarvam",
        "model": "saaras:v3",
        "mode": args.mode,
        "estimated_total_cost_inr": estimated_total,
        "summary": summarize_stt(scores),
        "predictions": [item.model_dump(mode="json") for item in predictions],
    }
    write_json(args.output, output)
    print(json.dumps(output["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
