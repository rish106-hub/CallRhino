import json
from collections.abc import Iterable
from datetime import date
from hashlib import sha256
from typing import Any, Literal

from pydantic import Field, field_validator

from callrhino.evaluation.evidence import evidence_metadata
from callrhino.evaluation.extraction_metrics import (
    score_extraction_case,
    summarize_extraction,
)
from callrhino.evaluation.models import (
    EvalModel,
    ExtractionCase,
    ExtractionCaseManifest,
    ExtractionPrediction,
)
from callrhino.evaluation.text_metrics import normalize_text
from callrhino.services.prompts import EXTRACTION_PROMPT_VERSION

HOLDOUT_FORMAT_VERSION = "1.0"
_FINGERPRINT_LENGTH = 64


class HoldoutPackageError(ValueError):
    """Raised when holdout artifacts cannot be safely combined."""


class PublicHoldoutCase(EvalModel):
    id: str
    title: str
    meeting_date: date
    meeting_type: str
    transcript: str = Field(min_length=1)
    tags: list[str]
    provenance: Literal["synthetic", "public", "consented"]
    transcript_fingerprint: str = Field(
        min_length=_FINGERPRINT_LENGTH,
        max_length=_FINGERPRINT_LENGTH,
        pattern=r"^[0-9a-f]{64}$",
    )
    input_fingerprint: str = Field(
        min_length=_FINGERPRINT_LENGTH,
        max_length=_FINGERPRINT_LENGTH,
        pattern=r"^[0-9a-f]{64}$",
    )

    @field_validator("transcript", mode="before")
    @classmethod
    def reject_blank_transcript(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            raise ValueError("holdout transcript cannot be blank")
        return value


class PublicHoldoutPackage(EvalModel):
    format_version: Literal["1.0"] = HOLDOUT_FORMAT_VERSION
    source_version: str
    package_id: str
    cases: list[PublicHoldoutCase]


class PrivateGoldCase(EvalModel):
    transcript_fingerprint: str = Field(
        min_length=_FINGERPRINT_LENGTH,
        max_length=_FINGERPRINT_LENGTH,
        pattern=r"^[0-9a-f]{64}$",
    )
    input_fingerprint: str = Field(
        min_length=_FINGERPRINT_LENGTH,
        max_length=_FINGERPRINT_LENGTH,
        pattern=r"^[0-9a-f]{64}$",
    )
    case: ExtractionCase


class PrivateGoldPackage(EvalModel):
    format_version: Literal["1.0"] = HOLDOUT_FORMAT_VERSION
    source_version: str
    package_id: str
    cases: list[PrivateGoldCase]


class HoldoutPrediction(ExtractionPrediction):
    input_fingerprint: str = Field(
        min_length=_FINGERPRINT_LENGTH,
        max_length=_FINGERPRINT_LENGTH,
        pattern=r"^[0-9a-f]{64}$",
    )


class HoldoutPredictionPackage(EvalModel):
    format_version: Literal["1.0"] = HOLDOUT_FORMAT_VERSION
    package_id: str
    strategy: Literal["canonical"] = "canonical"
    prompt_version: str = EXTRACTION_PROMPT_VERSION
    actual_total_cost_inr: float = Field(default=0, ge=0)
    predictions: list[HoldoutPrediction]


def create_holdout_packages(
    manifest: ExtractionCaseManifest,
) -> tuple[PublicHoldoutPackage, PrivateGoldPackage]:
    _assert_unique_source_cases(manifest.cases)
    public_cases = sorted(
        (_to_public_case(case) for case in manifest.cases),
        key=lambda case: case.id,
    )
    package_id = _package_id(public_cases)
    public_package = PublicHoldoutPackage(
        source_version=manifest.version,
        package_id=package_id,
        cases=public_cases,
    )
    source_by_id = {case.id: case for case in manifest.cases}
    private_package = PrivateGoldPackage(
        source_version=manifest.version,
        package_id=package_id,
        cases=[
            PrivateGoldCase(
                transcript_fingerprint=public_case.transcript_fingerprint,
                input_fingerprint=public_case.input_fingerprint,
                case=source_by_id[public_case.id],
            )
            for public_case in public_cases
        ],
    )
    validate_public_package(public_package)
    validate_gold_package(private_package)
    return public_package, private_package


def validate_public_package(package: PublicHoldoutPackage) -> None:
    if not package.cases:
        raise HoldoutPackageError("Holdout package must contain at least one case.")
    _assert_unique_public_cases(package.cases)
    fingerprint_errors = [
        case.id
        for case in package.cases
        if case.transcript_fingerprint != transcript_fingerprint(case.transcript)
        or case.input_fingerprint != input_fingerprint(case)
    ]
    if fingerprint_errors:
        raise HoldoutPackageError(
            "Public package contains invalid fingerprints for case IDs: "
            + ", ".join(sorted(fingerprint_errors))
        )
    expected_package_id = _package_id(package.cases)
    if package.package_id != expected_package_id:
        raise HoldoutPackageError(
            f"Public package ID mismatch: expected {expected_package_id}, "
            f"received {package.package_id}."
        )


def validate_gold_package(package: PrivateGoldPackage) -> None:
    if not package.cases:
        raise HoldoutPackageError("Private gold package must contain at least one case.")
    source_cases = [item.case for item in package.cases]
    _assert_unique_source_cases(source_cases)
    public_cases = [_to_public_case(item.case) for item in package.cases]
    fingerprint_errors = [
        item.case.id
        for item, public_case in zip(package.cases, public_cases, strict=True)
        if item.transcript_fingerprint != public_case.transcript_fingerprint
        or item.input_fingerprint != public_case.input_fingerprint
    ]
    if fingerprint_errors:
        raise HoldoutPackageError(
            "Private gold package contains invalid fingerprints for case IDs: "
            + ", ".join(sorted(fingerprint_errors))
        )
    expected_package_id = _package_id(public_cases)
    if package.package_id != expected_package_id:
        raise HoldoutPackageError(
            f"Private gold package ID mismatch: expected {expected_package_id}, "
            f"received {package.package_id}."
        )


def score_holdout_package(
    gold: PrivateGoldPackage,
    predictions: HoldoutPredictionPackage,
) -> dict[str, Any]:
    validate_gold_package(gold)
    if predictions.package_id != gold.package_id:
        raise HoldoutPackageError(
            f"Package ID mismatch: gold is {gold.package_id}, "
            f"predictions are {predictions.package_id}."
        )
    if predictions.prompt_version != EXTRACTION_PROMPT_VERSION:
        raise HoldoutPackageError(
            f"Prompt version mismatch: predictions used {predictions.prompt_version}, "
            f"current prompt is {EXTRACTION_PROMPT_VERSION}."
        )

    prediction_by_id = _prediction_index(predictions.predictions)
    gold_by_id = {item.case.id: item for item in gold.cases}
    missing_ids = sorted(gold_by_id.keys() - prediction_by_id.keys())
    extra_ids = sorted(prediction_by_id.keys() - gold_by_id.keys())
    id_errors = []
    if missing_ids:
        id_errors.append("missing prediction IDs: " + ", ".join(missing_ids))
    if extra_ids:
        id_errors.append("extra prediction IDs: " + ", ".join(extra_ids))
    if id_errors:
        raise HoldoutPackageError("Prediction case set mismatch: " + "; ".join(id_errors))

    fingerprint_errors = [
        case_id
        for case_id, gold_case in gold_by_id.items()
        if prediction_by_id[case_id].input_fingerprint != gold_case.input_fingerprint
    ]
    if fingerprint_errors:
        raise HoldoutPackageError(
            "Prediction input fingerprint mismatch for case IDs: "
            + ", ".join(sorted(fingerprint_errors))
        )

    scores = [
        score_extraction_case(item.case, prediction_by_id[item.case.id])
        for item in sorted(gold.cases, key=lambda value: value.case.id)
    ]
    providers = {item.provider for item in predictions.predictions}
    models = {item.model for item in predictions.predictions}
    dataset_fingerprint = _fingerprint(
        "callrhino-holdout-gold-v1",
        [
            {
                "case_id": item.case.id,
                "input_fingerprint": item.input_fingerprint,
            }
            for item in sorted(gold.cases, key=lambda value: value.case.id)
        ],
    )
    return {
        "format_version": HOLDOUT_FORMAT_VERSION,
        "package_id": gold.package_id,
        "source_version": gold.source_version,
        "evidence": evidence_metadata(
            kind="frozen_holdout",
            dataset_id=gold.package_id,
            dataset_fingerprint=dataset_fingerprint,
            prompt_version=predictions.prompt_version,
            provider=next(iter(providers)) if len(providers) == 1 else None,
            model=next(iter(models)) if len(models) == 1 else None,
            case_fingerprints=[
                item.input_fingerprint
                for item in sorted(gold.cases, key=lambda value: value.case.id)
            ],
        ),
        "summary": summarize_extraction(scores),
    }


def transcript_fingerprint(transcript: str) -> str:
    normalized = normalize_text(transcript)
    return _fingerprint("callrhino-holdout-transcript-v1", normalized)


def input_fingerprint(case: PublicHoldoutCase) -> str:
    visible_input = {
        "id": case.id,
        "title": case.title,
        "meeting_date": case.meeting_date.isoformat(),
        "meeting_type": case.meeting_type,
        "transcript": case.transcript,
        "tags": sorted(case.tags),
        "provenance": case.provenance,
    }
    return _fingerprint("callrhino-holdout-input-v1", visible_input)


def _to_public_case(case: ExtractionCase) -> PublicHoldoutCase:
    public_case = PublicHoldoutCase(
        id=case.id,
        title=case.title,
        meeting_date=case.meeting_date,
        meeting_type=case.meeting_type,
        transcript=case.transcript,
        tags=sorted(case.tags),
        provenance=case.provenance,
        transcript_fingerprint=transcript_fingerprint(case.transcript),
        input_fingerprint="0" * _FINGERPRINT_LENGTH,
    )
    return public_case.model_copy(
        update={"input_fingerprint": input_fingerprint(public_case)}
    )


def _package_id(cases: list[PublicHoldoutCase]) -> str:
    package_index = [
        {"id": case.id, "input_fingerprint": case.input_fingerprint}
        for case in sorted(cases, key=lambda value: value.id)
    ]
    digest = _fingerprint("callrhino-holdout-package-v1", package_index)
    return f"holdout_{digest[:24]}"


def _assert_unique_source_cases(cases: list[ExtractionCase]) -> None:
    if not cases:
        raise HoldoutPackageError("Holdout source must contain at least one case.")
    _assert_unique_values(
        ((case.id, case.id) for case in cases),
        label="case IDs",
    )
    _assert_unique_values(
        (
            (transcript_fingerprint(case.transcript), case.id)
            for case in cases
        ),
        label="normalized transcripts",
    )


def _assert_unique_public_cases(cases: list[PublicHoldoutCase]) -> None:
    _assert_unique_values(
        ((case.id, case.id) for case in cases),
        label="case IDs",
    )
    _assert_unique_values(
        ((case.transcript_fingerprint, case.id) for case in cases),
        label="normalized transcripts",
    )


def _assert_unique_values(
    values: Iterable[tuple[str, str]],
    *,
    label: str,
) -> None:
    owners: dict[str, str] = {}
    duplicates: set[str] = set()
    for value, case_id in values:
        if value in owners:
            duplicates.update((owners[value], case_id))
        else:
            owners[value] = case_id
    if duplicates:
        raise HoldoutPackageError(
            f"Duplicate {label} detected for case IDs: "
            + ", ".join(sorted(duplicates))
        )


def _prediction_index(
    predictions: list[HoldoutPrediction],
) -> dict[str, HoldoutPrediction]:
    by_id: dict[str, HoldoutPrediction] = {}
    duplicates: set[str] = set()
    for prediction in predictions:
        if prediction.case_id in by_id:
            duplicates.add(prediction.case_id)
        by_id[prediction.case_id] = prediction
    if duplicates:
        raise HoldoutPackageError(
            "Duplicate prediction case IDs: " + ", ".join(sorted(duplicates))
        )
    return by_id


def _fingerprint(namespace: str, value: Any) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(f"{namespace}\n{canonical}".encode()).hexdigest()
