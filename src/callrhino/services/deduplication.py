import re
from typing import Any

OPERATIONAL_STATE_CUE = re.compile(
    r"\b("
    r"defer|gate|hold|keep\s+(?:the\s+)?owner\s+open|owner\s+open|pause|"
    r"reassign|remain\s+unassigned|wait"
    r")\b",
    re.IGNORECASE,
)
DECISION_CHOICE_CUE = re.compile(
    r"\b(approve|approved|cancel|choose|chose|decide|decided|reject|rejected|reverse)\b",
    re.IGNORECASE,
)
FUTURE_COMMITMENT_CUE = re.compile(
    r"\b(will|kar\s+denge|karenge|panren)\b",
    re.IGNORECASE,
)


def remove_duplicate_items(payload: dict[str, Any]) -> None:
    """Remove model output that describes one state as two canonical items."""
    _remove_duplicate_operational_actions(payload)
    _remove_duplicate_commitment_decisions(payload)


def _remove_duplicate_operational_actions(payload: dict[str, Any]) -> None:
    decisions = _dict_items(payload.get("decisions"))
    actions = payload.get("action_items")
    if not isinstance(actions, list):
        return

    kept_actions: list[Any] = []
    index_map: dict[int, int] = {}
    for old_index, action in enumerate(actions):
        if isinstance(action, dict) and _duplicates_operational_decision(action, decisions):
            continue
        index_map[old_index] = len(kept_actions)
        kept_actions.append(action)
    payload["action_items"] = kept_actions
    _reindex_related_warnings(
        payload,
        related_item_type="action_item",
        index_map=index_map,
    )


def _remove_duplicate_commitment_decisions(payload: dict[str, Any]) -> None:
    decisions = payload.get("decisions")
    actions = _dict_items(payload.get("action_items"))
    if not isinstance(decisions, list):
        return

    kept_decisions: list[Any] = []
    index_map: dict[int, int] = {}
    for old_index, decision in enumerate(decisions):
        if isinstance(decision, dict) and _duplicates_owner_commitment(decision, actions):
            continue
        index_map[old_index] = len(kept_decisions)
        kept_decisions.append(decision)
    payload["decisions"] = kept_decisions
    _reindex_related_warnings(
        payload,
        related_item_type="decision",
        index_map=index_map,
    )


def _duplicates_owner_commitment(
    decision: dict[str, Any],
    actions: list[dict[str, Any]],
) -> bool:
    decision_text = decision.get("text")
    decision_maker = decision.get("decision_maker_text")
    if (
        decision.get("status") != "confirmed"
        or not isinstance(decision_text, str)
        or not isinstance(decision_maker, str)
        or DECISION_CHOICE_CUE.search(decision_text)
        or not FUTURE_COMMITMENT_CUE.search(decision_text)
    ):
        return False

    decision_tokens = _content_tokens(decision_text)
    for action in actions:
        task = action.get("task")
        owner = action.get("owner_text")
        if (
            action.get("commitment_status") not in {"committed", "conditional"}
            or not isinstance(task, str)
            or not isinstance(owner, str)
            or owner.casefold() != decision_maker.casefold()
            or not _evidence_overlaps(decision, action)
        ):
            continue
        task_tokens = _content_tokens(task)
        if not task_tokens:
            continue
        overlap = len(decision_tokens & task_tokens) / min(
            len(decision_tokens),
            len(task_tokens),
        )
        if overlap >= 0.6:
            return True
    return False


def _duplicates_operational_decision(
    action: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> bool:
    task = action.get("task")
    if not isinstance(task, str) or not OPERATIONAL_STATE_CUE.search(task):
        return False
    task_tokens = _content_tokens(task)
    if not task_tokens:
        return False

    for decision in decisions:
        decision_text = decision.get("text")
        if not isinstance(decision_text, str):
            continue
        decision_tokens = _content_tokens(decision_text)
        if not decision_tokens:
            continue
        overlap = len(task_tokens & decision_tokens) / min(
            len(task_tokens),
            len(decision_tokens),
        )
        if overlap >= 0.6 and _evidence_overlaps(action, decision):
            return True
    return False


def _reindex_related_warnings(
    payload: dict[str, Any],
    *,
    related_item_type: str,
    index_map: dict[int, int],
) -> None:
    warnings = payload.get("warnings")
    if not isinstance(warnings, list):
        return

    kept: list[Any] = []
    for warning in warnings:
        if not isinstance(warning, dict) or warning.get("related_item_type") != related_item_type:
            kept.append(warning)
            continue
        old_index = warning.get("related_item_index")
        if not isinstance(old_index, int):
            kept.append(warning)
        elif old_index in index_map:
            warning["related_item_index"] = index_map[old_index]
            kept.append(warning)
    payload["warnings"] = kept


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _content_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


def _evidence_overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_ids = _string_set(left.get("evidence_segment_ids"))
    right_ids = _string_set(right.get("evidence_segment_ids"))
    return bool(left_ids & right_ids)


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, str)}
