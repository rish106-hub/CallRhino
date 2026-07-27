from datetime import date
from html import escape

import streamlit as st

from callrhino.domain.models import (
    ActionItem,
    Decision,
    DecisionMakerBasis,
    MeetingBrief,
    OpenQuestion,
    OwnerBasis,
    Priority,
    Risk,
    TemporalPrecision,
    TranscriptSegment,
    WarningCode,
)


def render_page_intro(kicker: str, title: str, description: str) -> None:
    st.markdown(f'<div class="rhino-kicker">{escape(kicker)}</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<p class="rhino-deck">{escape(description)}</p>', unsafe_allow_html=True)


def render_evidence(
    evidence_ids: list[str],
    segment_lookup: dict[str, TranscriptSegment],
) -> None:
    for evidence_id in evidence_ids:
        segment = segment_lookup.get(evidence_id)
        if not segment:
            continue
        speaker = f"{segment.speaker_label}: " if segment.speaker_label else ""
        st.markdown(
            (
                '<div class="trace-card">'
                f'<span class="evidence-badge">{escape(evidence_id)}</span>'
                f"<p>{escape(speaker + segment.text)}</p>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )


def render_review_form(
    brief: MeetingBrief,
    segments: list[TranscriptSegment],
) -> MeetingBrief | None:
    segment_lookup = {segment.id: segment for segment in segments}

    with st.form("meeting_review"):
        st.subheader("Review the record")
        st.caption("Nothing enters the register until you approve it.")
        summary_text = st.text_area(
            "Executive summary",
            value=brief.summary.short,
            height=130,
        )

        st.markdown("### Decisions")
        decisions: list[Decision] = []
        for index, item in enumerate(brief.decisions):
            with st.container(border=True):
                include = st.checkbox(
                    "Include decision",
                    value=True,
                    key=f"decision_include_{index}",
                )
                text = st.text_area(
                    "Decision",
                    value=item.text,
                    key=f"decision_text_{index}",
                    height=80,
                )
                owner = st.text_input(
                    "Decision maker",
                    value=item.decision_maker_text or "",
                    key=f"decision_owner_{index}",
                    placeholder="Leave blank when no decision maker was stated",
                )
                st.caption(
                    f"Status: {item.status.value.replace('_', ' ').title()} | "
                    f"Evidence: {item.evidence_strength.value.replace('_', ' ').title()}"
                )
                with st.expander("View transcript evidence"):
                    render_evidence(item.evidence_segment_ids, segment_lookup)
                if include:
                    decision_maker = owner.strip() or None
                    decisions.append(
                        item.model_copy(
                            update={
                                "text": text.strip(),
                                "decision_maker_text": decision_maker,
                                "decision_maker_basis": (
                                    DecisionMakerBasis.REVIEWER_CONFIRMED
                                    if decision_maker
                                    else DecisionMakerBasis.UNASSIGNED
                                ),
                            }
                        )
                    )

        st.markdown("### Action items")
        action_items: list[ActionItem] = []
        for index, item in enumerate(brief.action_items):
            with st.container(border=True):
                include = st.checkbox(
                    "Include action item",
                    value=True,
                    key=f"action_include_{index}",
                )
                task = st.text_area(
                    "Task",
                    value=item.task,
                    key=f"action_task_{index}",
                    height=80,
                )
                left, right = st.columns(2)
                with left:
                    owner = st.text_input(
                        "Owner",
                        value=item.owner_text or "",
                        key=f"action_owner_{index}",
                        placeholder="Unassigned",
                    )
                    due_value = st.date_input(
                        "Concrete due date",
                        value=item.due_date,
                        key=f"action_due_date_{index}",
                    )
                with right:
                    due_text = st.text_input(
                        "Original deadline phrase",
                        value=item.due_text or "",
                        key=f"action_due_text_{index}",
                        placeholder="Example: next Wednesday",
                    )
                    priority = st.selectbox(
                        "Priority",
                        options=list(Priority),
                        index=list(Priority).index(item.priority),
                        format_func=lambda value: value.value.title(),
                        key=f"action_priority_{index}",
                    )
                st.caption(
                    f"Commitment: {item.commitment_status.value.replace('_', ' ').title()} | "
                    f"Owner basis: {item.owner_basis.value.replace('_', ' ').title()} | "
                    f"Evidence: {item.evidence_strength.value.replace('_', ' ').title()}"
                )
                with st.expander("View transcript evidence"):
                    render_evidence(item.evidence_segment_ids, segment_lookup)
                if include:
                    approved_owner = owner.strip() or None
                    approved_due_date = (
                        due_value if isinstance(due_value, date) else None
                    )
                    approved_due_text = due_text.strip() or None
                    deadline_precision = _reviewed_deadline_precision(
                        approved_due_date,
                        approved_due_text,
                    )
                    action_items.append(
                        item.model_copy(
                            update={
                                "task": task.strip(),
                                "owner_text": approved_owner,
                                "owner_basis": (
                                    OwnerBasis.REVIEWER_CONFIRMED
                                    if approved_owner
                                    else OwnerBasis.UNASSIGNED
                                ),
                                "suggested_owner_text": (
                                    item.suggested_owner_text
                                    if approved_owner is None
                                    else None
                                ),
                                "due_date": approved_due_date,
                                "due_text": approved_due_text,
                                "deadline_precision": deadline_precision,
                                "warnings": _reviewed_action_warnings(
                                    item,
                                    owner=approved_owner,
                                    deadline_precision=deadline_precision,
                                ),
                                "priority": priority,
                            }
                        )
                    )

        st.markdown("### Open questions")
        questions: list[OpenQuestion] = []
        for index, item in enumerate(brief.open_questions):
            with st.container(border=True):
                include = st.checkbox(
                    "Include question",
                    value=True,
                    key=f"question_include_{index}",
                )
                text = st.text_area(
                    "Question",
                    value=item.text,
                    key=f"question_text_{index}",
                    height=70,
                )
                with st.expander("View transcript evidence"):
                    render_evidence(item.evidence_segment_ids, segment_lookup)
                if include:
                    questions.append(item.model_copy(update={"text": text.strip()}))

        st.markdown("### Risks")
        risks: list[Risk] = []
        for index, item in enumerate(brief.risks):
            with st.container(border=True):
                include = st.checkbox("Include risk", value=True, key=f"risk_include_{index}")
                text = st.text_area(
                    "Risk",
                    value=item.text,
                    key=f"risk_text_{index}",
                    height=70,
                )
                with st.expander("View transcript evidence"):
                    render_evidence(item.evidence_segment_ids, segment_lookup)
                if include:
                    risks.append(item.model_copy(update={"text": text.strip()}))

        approved = st.form_submit_button(
            "Approve and add to register",
            type="primary",
            use_container_width=True,
        )

    if not approved:
        return None

    reviewed = brief.model_copy(
        update={
            "summary": brief.summary.model_copy(update={"short": summary_text.strip()}),
            "decisions": decisions,
            "action_items": action_items,
            "open_questions": questions,
            "risks": risks,
        }
    )
    return MeetingBrief.model_validate(reviewed.model_dump(mode="python"))


def _reviewed_deadline_precision(
    due_date: date | None,
    due_text: str | None,
) -> TemporalPrecision:
    if due_date and due_text:
        return TemporalPrecision.RESOLVED_RELATIVE
    if due_date:
        return TemporalPrecision.EXACT
    if due_text:
        return TemporalPrecision.VAGUE
    return TemporalPrecision.ABSENT


def _reviewed_action_warnings(
    item: ActionItem,
    *,
    owner: str | None,
    deadline_precision: TemporalPrecision,
) -> list[WarningCode]:
    managed = {
        WarningCode.MISSING_OWNER,
        WarningCode.MISSING_DEADLINE,
        WarningCode.VAGUE_DEADLINE,
        WarningCode.UNACCEPTED_ASSIGNMENT,
    }
    warnings = {warning for warning in item.warnings if warning not in managed}
    if owner is None:
        warnings.add(WarningCode.MISSING_OWNER)
        if item.suggested_owner_text:
            warnings.add(WarningCode.UNACCEPTED_ASSIGNMENT)
    if deadline_precision == TemporalPrecision.VAGUE:
        warnings.add(WarningCode.VAGUE_DEADLINE)
    elif deadline_precision == TemporalPrecision.ABSENT:
        warnings.add(WarningCode.MISSING_DEADLINE)
    return sorted(warnings, key=lambda warning: warning.value)
