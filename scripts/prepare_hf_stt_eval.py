import argparse
import re
from pathlib import Path

import httpx

from callrhino.evaluation.huggingface import download_audio, fetch_row
from callrhino.evaluation.io import write_json
from callrhino.evaluation.models import SttCase, SttCaseManifest

DATASET = "dianavdavidson/MUCS-Hinglish"
DEFAULT_OFFSETS = [0, 19, 137, 401, 733, 1099, 1481, 1907, 2311, 2701, 3007]
ENGLISH_RE = re.compile(r"[A-Za-z][A-Za-z0-9+./_-]*")
ENTITY_RE = re.compile(r"(?:₹\s*)?\d+(?:[.,]\d+)*")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download a small, deterministic MUCS-Hinglish STT sample.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("evals/cache/mucs_hinglish"))
    parser.add_argument("--limit", type=int, default=len(DEFAULT_OFFSETS))
    args = parser.parse_args()
    if args.limit < 1 or args.limit > len(DEFAULT_OFFSETS):
        raise SystemExit(f"--limit must be between 1 and {len(DEFAULT_OFFSETS)}")

    cases: list[SttCase] = []
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for offset in DEFAULT_OFFSETS[: args.limit]:
            row = fetch_row(
                dataset=DATASET,
                config="default",
                split="test",
                offset=offset,
                client=client,
            )
            case_id = f"mucs_test_{offset:04d}"
            audio_path = args.output_dir / f"{case_id}.wav"
            if not audio_path.exists():
                download_audio(
                    audio_value=row["audio"],
                    destination=audio_path,
                    client=client,
                )
            reference = str(row["transcript"])
            ratio = float(row.get("ratio_english_words") or 0)
            cases.append(
                SttCase(
                    id=case_id,
                    dataset_id="mucs_hinglish",
                    split="test",
                    row_index=offset,
                    audio_path=audio_path,
                    reference=reference,
                    tags=["hinglish", _ratio_tag(ratio)],
                    english_terms=sorted(set(ENGLISH_RE.findall(reference))),
                    entities=sorted(set(ENTITY_RE.findall(reference))),
                )
            )

    manifest = SttCaseManifest(version="1.0", cases=cases)
    output_path = args.output_dir / "manifest.json"
    write_json(output_path, manifest)
    print(f"Prepared {len(cases)} samples at {output_path}")


def _ratio_tag(ratio: float) -> str:
    if ratio < 0.2:
        return "english_low"
    if ratio < 0.4:
        return "english_medium"
    return "english_high"


if __name__ == "__main__":
    main()
