import argparse
import csv
import io
import random
import zipfile
from collections import defaultdict
from pathlib import Path

import httpx

from callrhino.evaluation.io import write_json
from callrhino.evaluation.models import (
    CandidateCase,
    CandidateCaseManifest,
    CandidateKind,
)

DATASET_URL = (
    "https://www.kaggle.com/api/v1/datasets/download/"
    "yusufayta/teams-meeting-transcripts"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare a balanced Kaggle action/decision candidate sample.",
    )
    parser.add_argument("--per-label", type=int, default=30)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/cache/kaggle/candidate_cases.json"),
    )
    args = parser.parse_args()

    response = httpx.get(DATASET_URL, follow_redirects=True, timeout=60)
    response.raise_for_status()
    with (
        zipfile.ZipFile(io.BytesIO(response.content)) as archive,
        archive.open("label.csv") as raw_file,
    ):
        rows = list(csv.DictReader(io.TextIOWrapper(raw_file, encoding="utf-8")))

    by_label: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if (row.get("source") or "").strip() != "synthetic_en":
            continue
        label = (row.get("label") or "").strip()
        if label in {item.value for item in CandidateKind}:
            by_label[label].append(row)

    randomizer = random.Random(42)
    cases: list[CandidateCase] = []
    for label in CandidateKind:
        candidates = by_label[label.value]
        randomizer.shuffle(candidates)
        if len(candidates) < args.per_label:
            raise SystemExit(f"Only {len(candidates)} {label.value} rows are available")
        cases.extend(
            CandidateCase(
                id=f"kaggle_{label.value.lower()}_{index:03d}",
                text=row["text"].strip(),
                label=label,
            )
            for index, row in enumerate(candidates[: args.per_label], start=1)
        )
    randomizer.shuffle(cases)
    manifest = CandidateCaseManifest(
        version="1.0",
        source="yusufayta/teams-meeting-transcripts",
        provenance="synthetic",
        cases=cases,
    )
    write_json(args.output, manifest)
    print(f"Prepared {len(cases)} balanced synthetic Kaggle snippets at {args.output}")


if __name__ == "__main__":
    main()
