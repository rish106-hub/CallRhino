from dataclasses import dataclass
from hashlib import sha256

from callrhino.evaluation.models import ExtractionCaseManifest
from callrhino.evaluation.text_metrics import normalize_text


@dataclass(frozen=True)
class SplitValidationReport:
    development_cases: int
    holdout_cases: int
    shared_ids: tuple[str, ...]
    shared_transcript_hashes: tuple[str, ...]

    @property
    def independent(self) -> bool:
        return not self.shared_ids and not self.shared_transcript_hashes


def validate_split_independence(
    development: ExtractionCaseManifest,
    holdout: ExtractionCaseManifest,
) -> SplitValidationReport:
    development_ids = {case.id for case in development.cases}
    holdout_ids = {case.id for case in holdout.cases}
    development_hashes = {_transcript_hash(case.transcript) for case in development.cases}
    holdout_hashes = {_transcript_hash(case.transcript) for case in holdout.cases}
    return SplitValidationReport(
        development_cases=len(development.cases),
        holdout_cases=len(holdout.cases),
        shared_ids=tuple(sorted(development_ids & holdout_ids)),
        shared_transcript_hashes=tuple(sorted(development_hashes & holdout_hashes)),
    )


def assert_independent_splits(report: SplitValidationReport) -> None:
    problems = []
    if report.shared_ids:
        problems.append(f"shared case IDs: {', '.join(report.shared_ids)}")
    if report.shared_transcript_hashes:
        problems.append(
            f"shared transcript fingerprints: {', '.join(report.shared_transcript_hashes)}"
        )
    if problems:
        raise ValueError("Evaluation split leakage detected: " + "; ".join(problems))


def _transcript_hash(transcript: str) -> str:
    normalized = normalize_text(transcript)
    return sha256(normalized.encode("utf-8")).hexdigest()[:16]
