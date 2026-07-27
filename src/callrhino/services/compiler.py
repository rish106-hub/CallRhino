import re
from datetime import date

from callrhino.domain.compact import (
    CompactActorBasis,
    CompactExtraction,
    CompactFact,
    CompactFactKind,
)
from callrhino.domain.models import (
    ActionItem,
    CommitmentStatus,
    Decision,
    DecisionMakerBasis,
    DecisionStatus,
    EvidenceStrength,
    ExtractionWarning,
    MeetingBrief,
    MeetingContext,
    MeetingSummary,
    OpenQuestion,
    OpenQuestionStatus,
    OwnerBasis,
    Priority,
    Risk,
    RiskKind,
    TemporalPrecision,
    TranscriptSegment,
    WarningCode,
)
from callrhino.services.normalization import resolve_date_phrase

GENERIC_ACTORS = {"i", "we", "us", "our", "team"}
MONTH_PATTERN = (
    r"january|february|march|april|may|june|july|august|"
    r"september|october|november|december"
)
DATE_PHRASE_PATTERN = re.compile(
    rf"\b(?:\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTH_PATTERN})|"
    r"today|tomorrow|aaj|innikku|eod|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)


class CompactCompilationError(ValueError):
    """Raised when compact facts cannot be compiled safely."""


def compile_meeting_brief(
    extraction: CompactExtraction,
    *,
    meeting_date: date,
    meeting_title: str,
    timezone: str,
    output_language: str,
    segments: list[TranscriptSegment],
) -> MeetingBrief:
    segment_map = {segment.id: segment for segment in segments}
    decisions: list[Decision] = []
    actions: list[ActionItem] = []
    questions: list[OpenQuestion] = []
    risks: list[Risk] = []

    for fact in _deduplicate(extraction.facts):
        unknown = set(fact.evidence_segment_ids) - segment_map.keys()
        if unknown:
            invalid = ", ".join(sorted(unknown))
            raise CompactCompilationError(f"Unknown evidence segment IDs: {invalid}")
        evidence_strength = (
            EvidenceStrength.EXPLICIT
            if len(fact.evidence_segment_ids) == 1
            else EvidenceStrength.STRONG_CONTEXT
        )
        if fact.kind == CompactFactKind.DECISION:
            decisions.append(
                _compile_decision(
                    fact,
                    meeting_date=meeting_date,
                    evidence_strength=evidence_strength,
                    segment_map=segment_map,
                )
            )
        elif fact.kind == CompactFactKind.ACTION:
            actions.append(
                _compile_action(
                    fact,
                    meeting_date=meeting_date,
                    evidence_strength=evidence_strength,
                    segment_map=segment_map,
                )
            )
        elif fact.kind == CompactFactKind.QUESTION:
            questions.append(
                OpenQuestion(
                    text=fact.text,
                    status=OpenQuestionStatus(fact.state.value),
                    evidence_strength=evidence_strength,
                    evidence_segment_ids=fact.evidence_segment_ids,
                )
            )
        else:
            risks.append(
                Risk(
                    text=fact.text,
                    kind=RiskKind(fact.state.value),
                    evidence_strength=evidence_strength,
                    evidence_segment_ids=fact.evidence_segment_ids,
                )
            )

    warnings = _top_level_warnings(actions)
    return MeetingBrief(
        schema_version="2.0",
        meeting=MeetingContext(
            suggested_title=meeting_title,
            meeting_date=meeting_date,
            languages_detected=_detect_languages(segments),
            timezone=timezone,
            output_language=output_language,
        ),
        summary=MeetingSummary(short=extraction.summary, topics=extraction.topics),
        decisions=decisions,
        action_items=actions,
        open_questions=questions,
        risks=risks,
        warnings=warnings,
    )


def _compile_decision(
    fact: CompactFact,
    *,
    meeting_date: date,
    evidence_strength: EvidenceStrength,
    segment_map: dict[str, TranscriptSegment],
) -> Decision:
    actor_text, actor_basis, actor_warnings = _decision_actor(fact)
    date_value, date_text, precision = _compile_date(
        fact,
        meeting_date,
        segment_map,
    )
    return Decision(
        text=fact.text,
        status=DecisionStatus(fact.state.value),
        decision_maker_text=actor_text,
        decision_maker_basis=actor_basis,
        effective_date=date_value,
        effective_date_text=date_text,
        date_precision=precision,
        evidence_strength=evidence_strength,
        evidence_segment_ids=fact.evidence_segment_ids,
        warnings=actor_warnings,
    )


def _compile_action(
    fact: CompactFact,
    *,
    meeting_date: date,
    evidence_strength: EvidenceStrength,
    segment_map: dict[str, TranscriptSegment],
) -> ActionItem:
    owner_text, owner_basis, owner_warnings = _action_actor(fact)
    due_date, due_text, precision = _compile_date(
        fact,
        meeting_date,
        segment_map,
    )
    warnings = list(owner_warnings)
    if precision == TemporalPrecision.ABSENT:
        warnings.append(WarningCode.MISSING_DEADLINE)
    elif precision == TemporalPrecision.VAGUE:
        warnings.append(WarningCode.VAGUE_DEADLINE)
    return ActionItem(
        task=fact.text,
        commitment_status=CommitmentStatus(fact.state.value),
        owner_text=owner_text,
        owner_basis=owner_basis,
        suggested_owner_text=(
            fact.suggested_actor_text if owner_basis == OwnerBasis.UNASSIGNED else None
        ),
        due_date=due_date,
        due_text=due_text,
        deadline_precision=precision,
        priority=_priority_from_evidence(fact.evidence_segment_ids, segment_map),
        evidence_strength=evidence_strength,
        evidence_segment_ids=fact.evidence_segment_ids,
        warnings=warnings,
    )


def _decision_actor(
    fact: CompactFact,
) -> tuple[str | None, DecisionMakerBasis, list[WarningCode]]:
    if _generic_or_missing(fact.actor_text):
        warnings = [WarningCode.UNCLEAR_SPEAKER] if fact.actor_text else []
        return None, DecisionMakerBasis.UNASSIGNED, warnings
    basis = (
        DecisionMakerBasis.GROUP
        if fact.actor_basis in {CompactActorBasis.GROUP, CompactActorBasis.GROUP_COMMITMENT}
        else DecisionMakerBasis.EXPLICIT
    )
    return fact.actor_text, basis, []


def _action_actor(
    fact: CompactFact,
) -> tuple[str | None, OwnerBasis, list[WarningCode]]:
    if _generic_or_missing(fact.actor_text):
        warnings = [WarningCode.MISSING_OWNER]
        if fact.actor_text:
            warnings.append(WarningCode.UNCLEAR_SPEAKER)
        if fact.suggested_actor_text:
            warnings.append(WarningCode.UNACCEPTED_ASSIGNMENT)
        return None, OwnerBasis.UNASSIGNED, warnings
    basis_map = {
        CompactActorBasis.SELF_COMMITMENT: OwnerBasis.SELF_COMMITMENT,
        CompactActorBasis.ASSIGNED_AND_ACCEPTED: OwnerBasis.ASSIGNED_AND_ACCEPTED,
        CompactActorBasis.GROUP_COMMITMENT: OwnerBasis.GROUP_COMMITMENT,
    }
    basis = basis_map.get(fact.actor_basis, OwnerBasis.ASSIGNED_AND_ACCEPTED)
    return fact.actor_text, basis, []


def _generic_or_missing(value: str | None) -> bool:
    return not value or value.strip().casefold() in GENERIC_ACTORS


def _compile_date(
    fact: CompactFact,
    meeting_date: date,
    segment_map: dict[str, TranscriptSegment],
) -> tuple[date | None, str | None, TemporalPrecision]:
    evidence_text = " ".join(
        segment_map[segment_id].text for segment_id in fact.evidence_segment_ids
    )
    source_text = _date_phrase_from_text(evidence_text)
    if (
        source_text is None
        and fact.date_text
        and fact.date_text.casefold() in evidence_text.casefold()
    ):
        source_text = fact.date_text
    if source_text is None:
        return None, None, TemporalPrecision.ABSENT
    resolved = resolve_date_phrase(source_text, meeting_date)
    if resolved is None:
        return None, source_text, TemporalPrecision.VAGUE
    value, precision = resolved
    return value, source_text, TemporalPrecision(precision)


def _date_phrase_from_text(text: str) -> str | None:
    match = DATE_PHRASE_PATTERN.search(text)
    return match.group(0) if match else None


def _priority_from_evidence(
    evidence_ids: list[str],
    segment_map: dict[str, TranscriptSegment],
) -> Priority:
    source = " ".join(segment_map[segment_id].text for segment_id in evidence_ids).casefold()
    for priority in (Priority.HIGH, Priority.MEDIUM, Priority.LOW):
        if re.search(rf"\b{priority.value}[\s-]+priority\b", source):
            return priority
    if re.search(r"\b(urgent|critical|p0|p1)\b", source):
        return Priority.HIGH
    return Priority.UNKNOWN


def _detect_languages(segments: list[TranscriptSegment]) -> list[str]:
    text = " ".join(segment.text for segment in segments)
    languages = []
    if re.search(r"[A-Za-z]", text):
        languages.append("en-IN")
    if re.search(r"[\u0900-\u097f]", text):
        languages.append("hi-IN")
    if re.search(r"[\u0b80-\u0bff]", text):
        languages.append("ta-IN")
    if re.search(r"[\u0c00-\u0c7f]", text):
        languages.append("te-IN")
    return languages or ["unknown"]


def _deduplicate(facts: list[CompactFact]) -> list[CompactFact]:
    deduplicated: list[CompactFact] = []
    seen: set[tuple[str, str]] = set()
    for fact in facts:
        normalized_text = re.sub(r"\W+", " ", fact.text.casefold()).strip()
        key = (fact.kind.value, normalized_text)
        if key not in seen:
            deduplicated.append(fact)
            seen.add(key)
    return deduplicated


def _top_level_warnings(actions: list[ActionItem]) -> list[ExtractionWarning]:
    messages = {
        WarningCode.MISSING_OWNER: "This action has no accepted owner.",
        WarningCode.MISSING_DEADLINE: "This action has no stated deadline.",
        WarningCode.VAGUE_DEADLINE: "This action has a vague deadline.",
        WarningCode.UNACCEPTED_ASSIGNMENT: "The suggested owner did not accept.",
        WarningCode.UNCLEAR_SPEAKER: "The action attribution uses an unclear speaker.",
    }
    return [
        ExtractionWarning(
            code=code,
            message=messages[code],
            related_item_type="action",
            related_item_index=index,
        )
        for index, action in enumerate(actions)
        for code in action.warnings
        if code in messages
    ]
