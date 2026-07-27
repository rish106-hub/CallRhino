from pathlib import Path
from typing import Any

import httpx

DATASET_ROWS_URL = "https://datasets-server.huggingface.co/rows"


def fetch_row(
    *,
    dataset: str,
    config: str,
    split: str,
    offset: int,
    client: httpx.Client,
) -> dict[str, Any]:
    response = client.get(
        DATASET_ROWS_URL,
        params={
            "dataset": dataset,
            "config": config,
            "split": split,
            "offset": offset,
            "length": 1,
        },
    )
    response.raise_for_status()
    rows = response.json().get("rows", [])
    if not rows:
        raise ValueError(f"No row at offset {offset} for {dataset}/{split}")
    return rows[0]["row"]


def download_audio(
    *,
    audio_value: object,
    destination: Path,
    client: httpx.Client,
) -> None:
    source = _audio_source(audio_value)
    response = client.get(source)
    response.raise_for_status()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(response.content)


def _audio_source(value: object) -> str:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        source = value[0].get("src")
    elif isinstance(value, dict):
        source = value.get("src")
    else:
        source = None
    if not source:
        raise ValueError("Dataset row does not contain a downloadable audio URL")
    return str(source)

