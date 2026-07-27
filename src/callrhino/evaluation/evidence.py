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


def manifest_case_fingerprints(manifest: ExtractionCaseManifest) -> list[str]:
    return [
        sha256(
            json.dumps(
                case.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        for case in sorted(manifest.cases, key=lambda item: item.id)
    ]


def evidence_metadata(
    *,
    kind: EvidenceKind,
    dataset_id: str,
    dataset_fingerprint: str,
    prompt_version: str | None,
    provider: str | None,
    model: str | None,
    case_fingerprints: list[str],
) -> dict[str, str | list[str] | None]:
    return {
        "kind": kind,
        "dataset_id": dataset_id,
        "dataset_fingerprint": dataset_fingerprint,
        "prompt_version": prompt_version,
        "provider": provider,
        "model": model,
        "case_fingerprints": sorted(case_fingerprints),
    }
