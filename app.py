from datetime import date
from pathlib import Path

import streamlit as st

from callrhino.config import Settings, get_settings
from callrhino.domain.models import MeetingBrief, TranscriptSegment
from callrhino.domain.transcript import segment_transcript
from callrhino.repositories.sqlite import SQLiteMeetingRepository
from callrhino.services.exports import brief_to_json, brief_to_markdown
from callrhino.services.extraction import BriefValidationError, MeetingExtractor
from callrhino.services.sarvam import SarvamChatClient, SarvamError
from callrhino.ui.components import render_page_intro, render_review_form
from callrhino.ui.styles import apply_styles

st.set_page_config(
    page_title="CallRhino",
    layout="wide",
    initial_sidebar_state="auto",
)
apply_styles()


@st.cache_resource
def get_repository(db_path: str) -> SQLiteMeetingRepository:
    return SQLiteMeetingRepository(Path(db_path))


def sidebar(settings: Settings) -> str:
    with st.sidebar:
        st.markdown(
            '<div class="rhino-wordmark">CALL<span>RHINO</span></div>'
            '<div class="rhino-meta">Meeting accountability</div>',
            unsafe_allow_html=True,
        )
        st.markdown("")
        page = st.radio(
            "Workspace",
            ["New meeting", "Series register", "Meeting history"],
            label_visibility="collapsed",
        )
        sarvam_status = (
            "Sarvam: configured"
            if settings.has_sarvam_credentials
            else "Sarvam: add SARVAM_API_KEY"
        )
        if settings.openai_fallback_active:
            openai_status = "OpenAI: fallback enabled"
        elif settings.has_openai_credentials:
            openai_status = "OpenAI: key saved, calls disabled"
        else:
            openai_status = "OpenAI: optional key not added"
        storage_status = (
            "Storage: Supabase configured"
            if settings.has_supabase_credentials
            else "Storage: local SQLite"
        )
        st.markdown(
            '<div class="rhino-status">'
            f"{sarvam_status}<br>{openai_status}<br>{storage_status}"
            "</div>",
            unsafe_allow_html=True,
        )
    return page


def load_sample() -> str:
    sample_path = Path("samples/weekly_product_review.txt")
    return sample_path.read_text(encoding="utf-8") if sample_path.exists() else ""


def render_new_meeting(repository: SQLiteMeetingRepository) -> None:
    render_page_intro(
        "01 / Process",
        "Turn talk into a record.",
        "Paste a meeting transcript. CallRhino finds decisions, actions, missing owners, "
        "deadlines, and unresolved questions. You approve the result before it is saved.",
    )

    if "draft_brief" in st.session_state:
        render_current_draft(repository)
        return

    if st.button("Use sample transcript"):
        st.session_state.transcript_input = load_sample()
        st.rerun()

    with st.form("new_meeting"):
        top_left, top_middle, top_right = st.columns([1.2, 1.2, 0.8])
        with top_left:
            series_name = st.text_input(
                "Meeting series",
                value="Weekly Product Review",
                placeholder="Example: Weekly Product Review",
            )
        with top_middle:
            meeting_title = st.text_input(
                "Meeting title",
                value="Product and launch review",
            )
        with top_right:
            meeting_date = st.date_input("Meeting date", value=date.today())

        transcript_input = st.text_area(
            "Transcript",
            key="transcript_input",
            height=390,
            placeholder="Aditi: We need to move the launch...\nRohan: I can own the migration.",
        )
        transcript_file = st.file_uploader(
            "Or upload a transcript",
            type=["txt", "md"],
            help="UTF-8 text and Markdown files are supported.",
        )
        submitted = st.form_submit_button(
            "Create meeting brief",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        return
    if not series_name.strip() or not meeting_title.strip():
        st.error("Add a meeting series and title.")
        return
    try:
        transcript = (
            transcript_file.getvalue().decode("utf-8")
            if transcript_file is not None
            else transcript_input
        )
    except UnicodeDecodeError:
        st.error("The uploaded transcript must be a UTF-8 text file.")
        return
    if len(transcript.strip()) < 80:
        st.error("The transcript is too short to process.")
        return

    try:
        segments = segment_transcript(transcript)
        settings = get_settings()
        with (
            st.spinner("Reading commitments, decisions, and loose ends..."),
            SarvamChatClient(settings) as client,
        ):
            result = MeetingExtractor(client).extract(
                meeting_date=meeting_date,
                series_name=series_name.strip(),
                meeting_title=meeting_title.strip(),
                segments=segments,
            )
    except (ValueError, SarvamError, BriefValidationError) as exc:
        st.error(str(exc))
        return

    st.session_state.draft_brief = result.brief
    st.session_state.draft_segments = segments
    st.session_state.draft_context = {
        "series_name": series_name.strip(),
        "meeting_title": meeting_title.strip(),
        "meeting_date": meeting_date,
        "transcript": transcript,
        "source_type": "text_file" if transcript_file is not None else "pasted",
        "model": result.model,
        "tokens": result.usage.total_tokens,
        "repaired": result.repaired,
    }
    st.rerun()


def render_current_draft(repository: SQLiteMeetingRepository) -> None:
    brief: MeetingBrief = st.session_state.draft_brief
    segments: list[TranscriptSegment] = st.session_state.draft_segments
    context: dict = st.session_state.draft_context

    controls = st.columns([1, 1, 2])
    if controls[0].button("Discard draft"):
        clear_draft()
        st.rerun()

    controls[2].caption(
        f"Model: {context['model']} | Tokens: {context['tokens']}"
        + (" | Repaired once" if context["repaired"] else "")
    )

    warning_count = len(brief.warnings)
    metrics = st.columns(4)
    metrics[0].metric("Decisions", len(brief.decisions))
    metrics[1].metric("Actions", len(brief.action_items))
    metrics[2].metric("Open questions", len(brief.open_questions))
    metrics[3].metric("Warnings", warning_count)

    if brief.warnings:
        with st.expander(f"Review {warning_count} extraction warnings", expanded=True):
            for warning in brief.warnings:
                st.warning(warning.message)

    markdown_export = brief_to_markdown(
        brief,
        title=context["meeting_title"],
        series_name=context["series_name"],
    )
    json_export = brief_to_json(brief)
    export_columns = st.columns(2)
    export_columns[0].download_button(
        "Download draft Markdown",
        data=markdown_export,
        file_name="callrhino-meeting-brief.md",
        mime="text/markdown",
        use_container_width=True,
    )
    export_columns[1].download_button(
        "Download draft JSON",
        data=json_export,
        file_name="callrhino-meeting-brief.json",
        mime="application/json",
        use_container_width=True,
    )

    approved_brief = render_review_form(brief, segments)
    if approved_brief is None:
        return

    meeting_id = repository.approve_meeting(
        series_name=context["series_name"],
        title=context["meeting_title"],
        meeting_date=context["meeting_date"],
        source_type=context["source_type"],
        transcript_text=context["transcript"],
        segments=segments,
        brief=approved_brief,
    )
    clear_draft()
    st.success(f"Meeting approved and saved. Record ID: {meeting_id[:8]}")


def clear_draft() -> None:
    for key in ("draft_brief", "draft_segments", "draft_context"):
        st.session_state.pop(key, None)


def render_register(repository: SQLiteMeetingRepository) -> None:
    render_page_intro(
        "02 / Track",
        "The series register.",
        "Approved commitments from recurring meetings. Missing owners and dates stay visible.",
    )
    series = repository.list_series()
    if not series:
        st.info("Approve the first meeting to create a register.")
        return

    selected_series = st.selectbox("Meeting series", options=series)
    meetings = repository.list_meetings(series_name=selected_series)
    actions = [
        {
            "Meeting": meeting.title,
            "Task": item.task,
            "Owner": item.owner_text or "Unassigned",
            "Due": item.due_text or (item.due_date.isoformat() if item.due_date else "Not set"),
            "Priority": item.priority.value,
        }
        for meeting in meetings
        for item in meeting.brief.action_items
    ]
    decisions = [
        {
            "Meeting": meeting.title,
            "Decision": item.text,
            "Owner": item.owner_text or "Unassigned",
            "Confidence": f"{item.confidence:.0%}",
        }
        for meeting in meetings
        for item in meeting.brief.decisions
    ]

    metric_columns = st.columns(3)
    metric_columns[0].metric("Approved meetings", len(meetings))
    metric_columns[1].metric("Action items", len(actions))
    metric_columns[2].metric("Decisions", len(decisions))

    st.subheader("Action items")
    if actions:
        st.dataframe(actions, use_container_width=True, hide_index=True)
    else:
        st.caption("No approved action items.")

    st.subheader("Decision register")
    if decisions:
        st.dataframe(decisions, use_container_width=True, hide_index=True)
    else:
        st.caption("No approved decisions.")


def render_history(repository: SQLiteMeetingRepository) -> None:
    render_page_intro(
        "03 / Recall",
        "Approved meeting history.",
        "Open the record your team agreed to, not an unreviewed model response.",
    )
    meetings = repository.list_meetings()
    if not meetings:
        st.info("No approved meetings yet.")
        return

    for meeting in meetings:
        with st.expander(
            f"{meeting.meeting_date.isoformat()} | {meeting.series_name} | {meeting.title}"
        ):
            st.write(meeting.brief.summary.short)
            left, right = st.columns(2)
            left.metric("Decisions", len(meeting.brief.decisions))
            right.metric("Actions", len(meeting.brief.action_items))
            st.download_button(
                "Download approved brief",
                data=brief_to_markdown(
                    meeting.brief,
                    title=meeting.title,
                    series_name=meeting.series_name,
                ),
                file_name=f"{meeting.meeting_date.isoformat()}-meeting-brief.md",
                mime="text/markdown",
                key=f"history_download_{meeting.id}",
            )


def main() -> None:
    settings = get_settings()
    settings.ensure_storage_directory()
    repository = get_repository(str(settings.db_path))
    page = sidebar(settings)

    if page == "New meeting":
        render_new_meeting(repository)
    elif page == "Series register":
        render_register(repository)
    else:
        render_history(repository)


if __name__ == "__main__":
    main()
