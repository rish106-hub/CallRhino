from datetime import date
from html import escape

import streamlit as st

from callrhino.domain.models import (
    ActionItem,
    Decision,
    MeetingBrief,
    OpenQuestion,
    Priority,
    Risk,
    TranscriptSegment,
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
                    "Owner",
                    value=item.owner_text or "",
                    key=f"decision_owner_{index}",
                    placeholder="Leave blank when no owner was stated",
                )
                st.caption(f"Confidence {item.confidence:.0%}")
                with st.expander("View transcript evidence"):
                    render_evidence(item.evidence_segment_ids, segment_lookup)
                if include:
                    decisions.append(
                        item.model_copy(
                            update={
                                "text": text.strip(),
                                "owner_text": owner.strip() or None,
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
                st.caption(f"Confidence {item.confidence:.0%}")
                with st.expander("View transcript evidence"):
                    render_evidence(item.evidence_segment_ids, segment_lookup)
                if include:
                    action_items.append(
                        item.model_copy(
                            update={
                                "task": task.strip(),
                                "owner_text": owner.strip() or None,
                                "due_date": due_value if isinstance(due_value, date) else None,
                                "due_text": due_text.strip() or None,
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

    return brief.model_copy(
        update={
            "summary": brief.summary.model_copy(update={"short": summary_text.strip()}),
            "decisions": decisions,
            "action_items": action_items,
            "open_questions": questions,
            "risks": risks,
        }
    )
