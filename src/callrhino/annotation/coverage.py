from pydantic import Field

from callrhino.annotation.models import AnnotationRecord
from callrhino.domain.models import StrictModel


class CoverageQuota(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
    label: str = Field(min_length=1, max_length=200)
    required_tags: set[str] = Field(min_length=1)
    target_adjudicated_meetings: int = Field(gt=0)


class CoveragePlan(StrictModel):
    version: str = Field(min_length=1)
    minimum_adjudicated_meetings: int = Field(ge=20)
    minimum_expected_decisions: int = Field(ge=1)
    minimum_expected_actions: int = Field(ge=1)
    quotas: list[CoverageQuota] = Field(min_length=1)


class QuotaCoverage(StrictModel):
    id: str
    label: str
    required_tags: list[str]
    target_adjudicated_meetings: int
    registered_meetings: int
    dual_reviewed_meetings: int
    adjudicated_meetings: int
    remaining_meetings: int
    complete: bool


class CoverageReport(StrictModel):
    plan_version: str
    registered_meetings: int
    dual_reviewed_meetings: int
    adjudicated_meetings: int
    expected_decisions: int
    expected_actions: int
    remaining_adjudicated_meetings: int
    remaining_expected_decisions: int
    remaining_expected_actions: int
    quotas: list[QuotaCoverage]
    complete: bool
    blockers: list[str]


def evaluate_coverage(
    plan: CoveragePlan,
    records: list[AnnotationRecord],
) -> CoverageReport:
    registered = len(records)
    dual_reviewed = sum(len(record.submissions) == 2 for record in records)
    adjudicated_records = [
        record for record in records if record.adjudication is not None
    ]
    expected_decisions = sum(
        len(record.adjudication.extraction_case.expected_decisions)
        for record in adjudicated_records
        if record.adjudication is not None
    )
    expected_actions = sum(
        len(record.adjudication.extraction_case.expected_actions)
        for record in adjudicated_records
        if record.adjudication is not None
    )

    quota_reports = [_quota_coverage(quota, records) for quota in plan.quotas]
    blockers = []
    if len(adjudicated_records) < plan.minimum_adjudicated_meetings:
        blockers.append(
            f"Need {plan.minimum_adjudicated_meetings - len(adjudicated_records)} "
            "more adjudicated meetings."
        )
    if expected_decisions < plan.minimum_expected_decisions:
        blockers.append(
            f"Need {plan.minimum_expected_decisions - expected_decisions} "
            "more labelled decisions."
        )
    if expected_actions < plan.minimum_expected_actions:
        blockers.append(
            f"Need {plan.minimum_expected_actions - expected_actions} "
            "more labelled actions."
        )
    blockers.extend(
        f'{quota.label}: need {quota.remaining_meetings} more adjudicated meeting(s).'
        for quota in quota_reports
        if not quota.complete
    )

    return CoverageReport(
        plan_version=plan.version,
        registered_meetings=registered,
        dual_reviewed_meetings=dual_reviewed,
        adjudicated_meetings=len(adjudicated_records),
        expected_decisions=expected_decisions,
        expected_actions=expected_actions,
        remaining_adjudicated_meetings=max(
            0,
            plan.minimum_adjudicated_meetings - len(adjudicated_records),
        ),
        remaining_expected_decisions=max(
            0,
            plan.minimum_expected_decisions - expected_decisions,
        ),
        remaining_expected_actions=max(
            0,
            plan.minimum_expected_actions - expected_actions,
        ),
        quotas=quota_reports,
        complete=not blockers,
        blockers=blockers,
    )


def _quota_coverage(
    quota: CoverageQuota,
    records: list[AnnotationRecord],
) -> QuotaCoverage:
    required_tags = {tag.casefold() for tag in quota.required_tags}
    matching = [
        record
        for record in records
        if required_tags <= {tag.casefold() for tag in record.source.tags}
    ]
    dual_reviewed = sum(len(record.submissions) == 2 for record in matching)
    adjudicated = sum(record.adjudication is not None for record in matching)
    remaining = max(0, quota.target_adjudicated_meetings - adjudicated)
    return QuotaCoverage(
        id=quota.id,
        label=quota.label,
        required_tags=sorted(quota.required_tags),
        target_adjudicated_meetings=quota.target_adjudicated_meetings,
        registered_meetings=len(matching),
        dual_reviewed_meetings=dual_reviewed,
        adjudicated_meetings=adjudicated,
        remaining_meetings=remaining,
        complete=remaining == 0,
    )
