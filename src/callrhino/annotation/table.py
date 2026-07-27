from datetime import date
from typing import Any

from callrhino.annotation.models import AnnotatedAction, AnnotatedDecision


def parse_decision_rows(value: Any) -> list[AnnotatedDecision]:
    decisions = []
    for row in table_records(value):
        if not clean_text(row.get("item_id")):
            continue
        decisions.append(
            AnnotatedDecision(
                item_id=clean_text(row.get("item_id")),
                text=clean_text(row.get("text")),
                status=clean_text(row.get("status")),
                decision_maker_text=optional_text(row.get("decision_maker_text")),
                effective_date=optional_date(row.get("effective_date")),
                effective_date_text=optional_text(row.get("effective_date_text")),
                date_precision=clean_text(row.get("date_precision")),
                evidence_segment_ids=evidence_ids(row.get("evidence_segment_ids")),
            )
        )
    return decisions


def parse_action_rows(value: Any) -> list[AnnotatedAction]:
    actions = []
    for row in table_records(value):
        if not clean_text(row.get("item_id")):
            continue
        actions.append(
            AnnotatedAction(
                item_id=clean_text(row.get("item_id")),
                task=clean_text(row.get("task")),
                commitment_status=clean_text(row.get("commitment_status")),
                owner_text=optional_text(row.get("owner_text")),
                suggested_owner_text=optional_text(row.get("suggested_owner_text")),
                due_date=optional_date(row.get("due_date")),
                due_text=optional_text(row.get("due_text")),
                deadline_precision=clean_text(row.get("deadline_precision")),
                evidence_segment_ids=evidence_ids(row.get("evidence_segment_ids")),
            )
        )
    return actions


def table_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if hasattr(value, "to_dict"):
        records = value.to_dict("records")
        return [row for row in records if isinstance(row, dict)]
    raise ValueError("Annotation table returned an unsupported value.")


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def optional_text(value: Any) -> str | None:
    cleaned = clean_text(value)
    return cleaned or None


def optional_date(value: Any) -> date | None:
    cleaned = clean_text(value)
    return date.fromisoformat(cleaned) if cleaned else None


def evidence_ids(value: Any) -> list[str]:
    return [item.strip() for item in clean_text(value).split(",") if item.strip()]
