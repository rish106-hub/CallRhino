import re
from copy import deepcopy
from datetime import date, timedelta
from typing import Any

from callrhino.domain.models import TranscriptSegment, WarningCode

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
VAGUE_DATE_TERMS = (
    "soon",
    "sometime",
    "later",
    "next sprint",
    "jaldi",
)


def normalize_brief_payload(
    payload: dict[str, Any],
    *,
    meeting_date: date,
    timezone: str,
    output_language: str,
    segments: list[TranscriptSegment] | None = None,
) -> dict[str, Any]:
    """Apply only deterministic contract cleanup before strict validation."""
    normalized = deepcopy(payload)
    meeting = normalized.get("meeting")
    if isinstance(meeting, dict):
        meeting["meeting_date"] = meeting_date.isoformat()
        meeting["timezone"] = timezone
        meeting["output_language"] = output_language

    evidence = {segment.id: segment.text for segment in segments or []}
    for action in _dict_items(normalized.get("action_items")):
        _normalize_action(action, meeting_date, evidence)
    for decision in _dict_items(normalized.get("decisions")):
        _normalize_temporal(
            decision,
            text_key="effective_date_text",
            date_key="effective_date",
            precision_key="date_precision",
            meeting_date=meeting_date,
        )
    return normalized


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _normalize_action(
    action: dict[str, Any],
    meeting_date: date,
    evidence: dict[str, str],
) -> None:
    warnings = action.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
        action["warnings"] = warnings

    owner_basis = action.get("owner_basis")
    if owner_basis == "unassigned":
        _append_warning(warnings, WarningCode.MISSING_OWNER)
        if action.get("suggested_owner_text"):
            _append_warning(warnings, WarningCode.UNACCEPTED_ASSIGNMENT)
    else:
        _remove_warning(warnings, WarningCode.MISSING_OWNER)
        if not action.get("suggested_owner_text"):
            _remove_warning(warnings, WarningCode.UNACCEPTED_ASSIGNMENT)

    _normalize_temporal(
        action,
        text_key="due_text",
        date_key="due_date",
        precision_key="deadline_precision",
        meeting_date=meeting_date,
    )
    precision = action.get("deadline_precision")
    if precision == "absent":
        _append_warning(warnings, WarningCode.MISSING_DEADLINE)
        _remove_warning(warnings, WarningCode.VAGUE_DEADLINE)
    elif precision == "vague":
        _append_warning(warnings, WarningCode.VAGUE_DEADLINE)
        _remove_warning(warnings, WarningCode.MISSING_DEADLINE)
    else:
        _remove_warning(warnings, WarningCode.MISSING_DEADLINE)
        _remove_warning(warnings, WarningCode.VAGUE_DEADLINE)
    if action.get("evidence_strength") == "ambiguous":
        _append_warning(warnings, WarningCode.LOW_CONFIDENCE)
    else:
        _remove_warning(warnings, WarningCode.LOW_CONFIDENCE)

    if action.get("priority") in {"low", "medium", "high"}:
        source = " ".join(
            evidence.get(segment_id, "")
            for segment_id in action.get("evidence_segment_ids", [])
            if isinstance(segment_id, str)
        )
        if not _states_priority(source, str(action["priority"])):
            action["priority"] = "unknown"


def _append_warning(warnings: list[Any], code: WarningCode) -> None:
    if code.value not in warnings and code not in warnings:
        warnings.append(code.value)


def _remove_warning(warnings: list[Any], code: WarningCode) -> None:
    warnings[:] = [warning for warning in warnings if warning not in {code, code.value}]


def _states_priority(source: str, priority: str) -> bool:
    folded = source.casefold()
    if re.search(rf"\b{re.escape(priority)}[\s-]+priority\b", folded):
        return True
    if priority == "high":
        return bool(re.search(r"\b(urgent|critical|p0|p1)\b", folded))
    return False


def _normalize_temporal(
    item: dict[str, Any],
    *,
    text_key: str,
    date_key: str,
    precision_key: str,
    meeting_date: date,
) -> None:
    source_text = item.get(text_key)
    if not isinstance(source_text, str) or not source_text.strip():
        if item.get(date_key) is None:
            item[text_key] = None
            item[precision_key] = "absent"
        return

    source_text = source_text.strip()
    item[text_key] = source_text
    resolved = resolve_date_phrase(source_text, meeting_date)
    if resolved is not None:
        resolved_date, precision = resolved
        item[date_key] = resolved_date.isoformat()
        item[precision_key] = precision
        return

    if any(term in source_text.casefold() for term in VAGUE_DATE_TERMS):
        item[date_key] = None
        item[precision_key] = "vague"


def resolve_date_phrase(source_text: str, meeting_date: date) -> tuple[date, str] | None:
    folded = source_text.casefold()

    explicit = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(MONTHS) + r")\b",
        folded,
    )
    if explicit:
        day = int(explicit.group(1))
        month = MONTHS[explicit.group(2)]
        try:
            return date(meeting_date.year, month, day), "exact"
        except ValueError:
            return None

    if re.search(r"\b(today|aaj|innikku|eod)\b", folded):
        return meeting_date, "resolved_relative"
    if re.search(r"\btomorrow\b", folded):
        return meeting_date + timedelta(days=1), "resolved_relative"

    weekday_match = re.search(r"\b(" + "|".join(WEEKDAYS) + r")\b", folded)
    if weekday_match and not re.search(r"\bnext\s+" + weekday_match.group(1), folded):
        target = WEEKDAYS[weekday_match.group(1)]
        delta = (target - meeting_date.weekday()) % 7
        return meeting_date + timedelta(days=delta), "resolved_relative"
    return None
