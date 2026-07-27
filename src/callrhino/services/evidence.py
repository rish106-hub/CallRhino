import re
from typing import Any

from callrhino.domain.models import TranscriptSegment

CONTEXT_RADIUS = 2

CONTEXT_DEPENDENT_OPENING = re.compile(
    r"^\s*(approved|agree|agreed|okay|ok|fine|yes|theek|done|confirmed)\b",
    re.IGNORECASE,
)
ANAPHORA_CUE = re.compile(
    r"\b(it|this|that|these|those|them|same|isko|usko|yeh|woh)\b",
    re.IGNORECASE,
)
REQUEST_RESPONSE_CUE = re.compile(
    r"""
    \b(
        approval|blocked|cannot|can't|commit\s+nahi|dependent|depends|first|
        hold|need|owner\s+open|pehle|refuse|refused|unassigned|until|wait
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)
CONTENT_STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "be",
    "by",
    "for",
    "in",
    "is",
    "of",
    "on",
    "the",
    "to",
    "will",
    "with",
}


def complete_evidence_context(
    payload: dict[str, Any],
    segments: list[TranscriptSegment],
) -> None:
    """Add only nearby context required to understand an extracted item."""
    if not segments:
        return

    ordered = sorted(segments, key=lambda segment: segment.sequence_no)
    index_by_id = {segment.id: index for index, segment in enumerate(ordered)}

    for decision in _dict_items(payload.get("decisions")):
        evidence_indexes = _known_evidence_indexes(decision, index_by_id)
        if not evidence_indexes:
            continue

        status = decision.get("status")
        if status in {"reversed", "deferred"}:
            _add_state_transition_context(evidence_indexes)
        elif _decision_needs_previous_context(
            decision,
            evidence_indexes,
            ordered,
        ):
            _add_previous_context(evidence_indexes, radius=1)
        elif status == "confirmed":
            _remove_non_contributing_previous_context(
                decision,
                evidence_indexes,
                ordered,
            )
        _complete_anaphoric_context(evidence_indexes, ordered)
        _set_evidence_ids(decision, evidence_indexes, ordered)

    for action in _dict_items(payload.get("action_items")):
        evidence_indexes = _known_evidence_indexes(action, index_by_id)
        if not evidence_indexes:
            continue

        if action.get("commitment_status") == "requested":
            _add_request_response_context(evidence_indexes, ordered)
        if action.get("owner_basis") == "group_commitment":
            _add_previous_context(evidence_indexes, radius=1)
        _complete_anaphoric_context(evidence_indexes, ordered)
        _set_evidence_ids(action, evidence_indexes, ordered)

    for collection_name in ("open_questions", "risks"):
        for item in _dict_items(payload.get(collection_name)):
            evidence_indexes = _known_evidence_indexes(item, index_by_id)
            if not evidence_indexes:
                continue
            _complete_anaphoric_context(evidence_indexes, ordered)
            _set_evidence_ids(item, evidence_indexes, ordered)


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _known_evidence_indexes(
    item: dict[str, Any],
    index_by_id: dict[str, int],
) -> set[int]:
    raw_ids = item.get("evidence_segment_ids")
    if not isinstance(raw_ids, list):
        return set()
    return {
        index_by_id[segment_id]
        for segment_id in raw_ids
        if isinstance(segment_id, str) and segment_id in index_by_id
    }


def _add_previous_context(indexes: set[int], *, radius: int) -> None:
    first_index = min(indexes)
    indexes.update(range(max(0, first_index - radius), first_index))


def _add_state_transition_context(indexes: set[int]) -> None:
    if len(indexes) == 1:
        _add_previous_context(indexes, radius=CONTEXT_RADIUS)
    indexes.update(range(min(indexes), max(indexes) + 1))


def _add_request_response_context(
    indexes: set[int],
    segments: list[TranscriptSegment],
) -> None:
    last_index = max(indexes)
    stop = min(len(segments), last_index + CONTEXT_RADIUS + 1)
    for index in range(last_index + 1, stop):
        if REQUEST_RESPONSE_CUE.search(segments[index].text):
            indexes.add(index)


def _complete_anaphoric_context(
    indexes: set[int],
    segments: list[TranscriptSegment],
) -> None:
    first_index = min(indexes)
    if first_index > 0 and ANAPHORA_CUE.search(segments[first_index].text):
        indexes.add(first_index - 1)


def _decision_needs_previous_context(
    decision: dict[str, Any],
    indexes: set[int],
    segments: list[TranscriptSegment],
) -> bool:
    first_text = segments[min(indexes)].text
    if not CONTEXT_DEPENDENT_OPENING.search(first_text):
        return False

    decision_text = decision.get("text")
    if not isinstance(decision_text, str):
        return True
    claim_tokens = _content_tokens(decision_text)
    if not claim_tokens:
        return True
    evidence_tokens = _content_tokens(first_text)
    coverage = len(claim_tokens & evidence_tokens) / len(claim_tokens)
    return coverage < 0.9


def _remove_non_contributing_previous_context(
    decision: dict[str, Any],
    indexes: set[int],
    segments: list[TranscriptSegment],
) -> None:
    if len(indexes) < 2:
        return
    decision_text = decision.get("text")
    if not isinstance(decision_text, str):
        return

    claim_tokens = _content_tokens(decision_text)
    primary_index = max(indexes)
    if not CONTEXT_DEPENDENT_OPENING.search(segments[primary_index].text):
        return
    missing_from_primary = claim_tokens - _content_tokens(segments[primary_index].text)
    if not missing_from_primary:
        indexes.intersection_update({primary_index})
        return

    contributing = {
        index
        for index in indexes
        if index == primary_index
        or bool(_content_tokens(segments[index].text) & missing_from_primary)
    }
    indexes.intersection_update(contributing)


def _content_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if token not in CONTENT_STOPWORDS
    }


def _set_evidence_ids(
    item: dict[str, Any],
    indexes: set[int],
    segments: list[TranscriptSegment],
) -> None:
    original_ids = item.get("evidence_segment_ids")
    known_ids = {segment.id for segment in segments}
    unknown_ids = (
        [
            segment_id
            for segment_id in original_ids
            if isinstance(segment_id, str)
            and segment_id not in known_ids
        ]
        if isinstance(original_ids, list)
        else []
    )
    item["evidence_segment_ids"] = [
        *(segments[index].id for index in sorted(indexes)),
        *unknown_ids,
    ]
