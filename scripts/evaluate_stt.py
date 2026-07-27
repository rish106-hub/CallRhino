import argparse
import json
import time
from pathlib import Path

from callrhino.evaluation.audio import ensure_ffmpeg_on_path, wav_duration_seconds
from callrhino.evaluation.io import load_model, write_json
from callrhino.evaluation.models import SttCaseManifest, SttPrediction
from callrhino.evaluation.stt_metrics import score_stt_case, summarize_stt


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a local MLX Whisper model.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("evals/cache/mucs_hinglish/manifest.json"),
    )
    parser.add_argument(
        "--model",
        default="mlx-community/whisper-small-mlx-4bit",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/results/stt_mlx_whisper_small_4bit.json"),
    )
    parser.add_argument(
        "--language",
        default="auto",
        help="Whisper language code or 'auto' for automatic detection.",
    )
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    try:
        import mlx_whisper
    except ImportError as exc:
        raise SystemExit("Install evaluation dependencies with: uv sync --group eval") from exc

    ensure_ffmpeg_on_path()
    manifest = load_model(args.manifest, SttCaseManifest)
    cases = manifest.cases[: args.limit] if args.limit else manifest.cases
    predictions: list[SttPrediction] = []
    scores = []
    for case in cases:
        started = time.perf_counter()
        options = {
            "path_or_hf_repo": args.model,
            "temperature": 0,
        }
        if args.language != "auto":
            options["language"] = args.language
        result = mlx_whisper.transcribe(str(case.audio_path), **options)
        latency = time.perf_counter() - started
        prediction = SttPrediction(
            case_id=case.id,
            provider="local",
            model=args.model,
            transcript=str(result["text"]).strip(),
            latency_seconds=latency,
            audio_duration_seconds=wav_duration_seconds(case.audio_path),
        )
        predictions.append(prediction)
        scores.append(score_stt_case(case, prediction))
        print(f"{case.id}: WER={scores[-1].wer:.3f}, RTF={scores[-1].real_time_factor:.3f}")

    output = {
        "provider": "local",
        "model": args.model,
        "summary": summarize_stt(scores),
        "predictions": [item.model_dump(mode="json") for item in predictions],
    }
    write_json(args.output, output)
    print(json.dumps(output["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
