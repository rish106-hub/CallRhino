import json
from hashlib import sha256
from typing import Literal

from callrhino.evaluation.models import ExtractionCaseManifest

EvidenceKind = Literal[
    "development",
    "frozen_holdout",
    "consented_real_meetings",
]


def manifest_fingerprint(manifest: ExtractionCaseManifest) -> str:
    payload = manifest.model_dump(mode="json")
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def evidence_metadata(
    *,
    kind: EvidenceKind,
    dataset_id: str,
    dataset_fingerprint: str,
    prompt_version: str | None,
    provider: str | None,
    model: str | None,
) -> dict[str, str | None]:
    return {
        "kind": kind,
        "dataset_id": dataset_id,
        "dataset_fingerprint": dataset_fingerprint,
        "prompt_version": prompt_version,
        "provider": provider,
        "model": model,
    }
