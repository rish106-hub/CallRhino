from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st

from callrhino.annotation import (
    AnnotatedAction,
    AnnotatedDecision,
    AnnotationRecord,
    AnnotationService,
    ConsentStatus,
    JsonAnnotationRepository,
    PiiReviewStatus,
    RedactionStatus,
    ReviewerSubmission,
    SourceMeeting,
)
from callrhino.annotation.table import parse_action_rows, parse_decision_rows
from callrhino.domain.models import CommitmentStatus, DecisionStatus, TemporalPrecision
from callrhino.domain.transcript import segment_transcript
from callrhino.evaluation.holdout import create_holdout_packages
from callrhino.ui.styles import apply_styles

ANNOTATION_ROOT = Path("data/annotations")

DECISION_COLUMNS = {
    "item_id": st.column_config.TextColumn("Stable item ID", required=True),
    "text": st.column_config.TextColumn("Decision", required=True, width="large"),
    "status": st.column_config.SelectboxColumn(
        "Status",
        options=[item.value for item in DecisionStatus],
        required=True,
    ),
    "decision_maker_text": st.column_config.TextColumn("Decision maker"),
    "effective_date": st.column_config.TextColumn("Date (YYYY-MM-DD)"),
    "effective_date_text": st.column_config.TextColumn("Original date phrase"),
    "date_precision": st.column_config.SelectboxColumn(
        "Date precision",
        options=[item.value for item in TemporalPrecision],
        required=True,
    ),
    "evidence_segment_ids": st.column_config.TextColumn(
        "Evidence IDs, comma-separated",
        required=True,
        width="large",
    ),
}
ACTION_COLUMNS = {
    "item_id": st.column_config.TextColumn("Stable item ID", required=True),
    "task": st.column_config.TextColumn("Action", required=True, width="large"),
    "commitment_status": st.column_config.SelectboxColumn(
        "Commitment",
        options=[item.value for item in CommitmentStatus],
        required=True,
    ),
    "owner_text": st.column_config.TextColumn("Accepted owner"),
    "suggested_owner_text": st.column_config.TextColumn("Suggested owner"),
    "due_date": st.column_config.TextColumn("Due date (YYYY-MM-DD)"),
    "due_text": st.column_config.TextColumn("Original deadline phrase"),
    "deadline_precision": st.column_config.SelectboxColumn(
        "Deadline precision",
        options=[item.value for item in TemporalPrecision],
        required=True,
    ),
    "evidence_segment_ids": st.column_config.TextColumn(
        "Evidence IDs, comma-separated",
        required=True,
        width="large",
    ),
}


@st.cache_resource
def get_annotation_service(root: str) -> AnnotationService:
    return AnnotationService(JsonAnnotationRepository(Path(root)))


def main() -> None:
    st.set_page_config(page_title="CallRhino Annotation Lab", layout="wide")
    apply_styles()
    service = get_annotation_service(str(ANNOTATION_ROOT))

    st.markdown(
        '<div class="rhino-kicker">Private evaluation workspace</div>',
        unsafe_allow_html=True,
    )
    st.title("Annotation lab")
    st.caption(
        "Local-only workflow for consented, redacted transcripts. "
        "Do not expose this app publicly."
    )

    register_tab, review_tab, adjudicate_tab, export_tab = st.tabs(
        ["Register meeting", "Independent review", "Adjudicate", "Consent & export"]
    )
    with register_tab:
        render_registration(service)
    with review_tab:
        render_review(service)
    with adjudicate_tab:
        render_adjudication(service)
    with export_tab:
        render_consent_and_export(service)


def render_registration(service: AnnotationService) -> None:
    st.subheader("Register a reviewed transcript")
    st.caption(
        "Register only after consent, transcript review, and any required redaction."
    )
    with st.form("annotation_register"):
        left, middle, right = st.columns([1.2, 1.4, 0.8])
        meeting_id = left.text_input("Meeting ID", placeholder="product_review_2026_07_27")
        title = middle.text_input("Meeting title")
        meeting_date = right.date_input("Meeting date", value=date.today())
        meeting_type = left.text_input("Meeting type", value="internal_project")
        tags = middle.text_input("Tags", placeholder="hinglish, product, noisy-call")
        consent_reference = right.text_input(
            "Consent reference",
            placeholder="Internal consent record ID",
        )
        pii_status = st.radio(
            "PII review result",
            [PiiReviewStatus.CLEAR, PiiReviewStatus.REDACTED],
            format_func=lambda item: item.value.title(),
            horizontal=True,
        )
        transcript = st.text_area(
            "Reviewed and redacted transcript",
            height=360,
            placeholder="Aditi: We will launch Friday.\nRohan: I will send the deck.",
        )
        submitted = st.form_submit_button(
            "Register for independent review",
            type="primary",
            use_container_width=True,
        )
    if not submitted:
        return
    try:
        source = SourceMeeting(
            id=meeting_id.strip(),
            title=title.strip(),
            meeting_date=meeting_date,
            meeting_type=meeting_type.strip(),
            tags=[item.strip() for item in tags.split(",") if item.strip()],
            consent_status=ConsentStatus.GRANTED,
            consent_reference=consent_reference.strip(),
            pii_review_status=pii_status,
            redaction_status=(
                RedactionStatus.NOT_REQUIRED
                if pii_status == PiiReviewStatus.CLEAR
                else RedactionStatus.COMPLETED
            ),
            reviewed_segments=segment_transcript(transcript),
        )
        service.register_meeting(source)
    except (ValueError, OSError) as exc:
        st.error(str(exc))
        return
    st.success("Meeting registered. Reviewers can now label it independently.")


def render_review(service: AnnotationService) -> None:
    records = [
        record
        for record in service.list_records()
        if record.adjudication is None and len(record.submissions) < 2
    ]
    st.subheader("Submit an independent review")
    st.caption("Do not show reviewers model output or the other reviewer's labels.")
    if not records:
        st.info("No meetings are waiting for reviewer submissions.")
        return

    record = _select_record("review_meeting", records)
    _render_transcript(record)
    reviewer_id = st.text_input("Reviewer identity", key=f"reviewer_{record.source.id}")
    st.markdown("#### Decisions")
    decision_rows = st.data_editor(
        [_blank_decision()],
        column_config=DECISION_COLUMNS,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        key=f"review_decisions_{record.source.id}",
    )
    st.markdown("#### Actions")
    action_rows = st.data_editor(
        [_blank_action()],
        column_config=ACTION_COLUMNS,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        key=f"review_actions_{record.source.id}",
    )
    forbidden_text = st.text_area(
        "Facts the extractor must never invent, one per line",
        key=f"review_forbidden_{record.source.id}",
    )
    if not st.button(
        "Submit immutable review",
        type="primary",
        use_container_width=True,
        key=f"submit_review_{record.source.id}",
    ):
        return
    try:
        submission = ReviewerSubmission(
            reviewer_id=reviewer_id,
            decisions=parse_decision_rows(decision_rows),
            actions=parse_action_rows(action_rows),
            forbidden_facts=_nonempty_lines(forbidden_text),
        )
        service.submit_review(record.source.id, submission)
    except (ValueError, OSError) as exc:
        st.error(str(exc))
        return
    st.success("Review stored. It cannot be overwritten.")


def render_adjudication(service: AnnotationService) -> None:
    records = [
        record
        for record in service.list_records()
        if len(record.submissions) == 2 and record.adjudication is None
    ]
    st.subheader("Adjudicate reviewer disagreements")
    if not records:
        st.info("No meetings are ready for adjudication.")
        return

    record = _select_record("adjudicate_meeting", records)
    _render_transcript(record)
    disagreements = service.disagreements(record.source.id)
    if disagreements:
        st.dataframe(
            [item.model_dump(mode="json") for item in disagreements],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.success("The two reviewers agree on every structured field.")

    decision_rows = st.data_editor(
        _merged_decision_rows(record),
        column_config=DECISION_COLUMNS,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        key=f"adjudicate_decisions_{record.source.id}",
    )
    action_rows = st.data_editor(
        _merged_action_rows(record),
        column_config=ACTION_COLUMNS,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        key=f"adjudicate_actions_{record.source.id}",
    )
    adjudicator_id = st.text_input(
        "Adjudicator identity",
        key=f"adjudicator_{record.source.id}",
    )
    forbidden_text = st.text_area(
        "Final forbidden facts, one per line",
        value="\n".join(
            sorted(
                {
                    fact
                    for submission in record.submissions
                    for fact in submission.forbidden_facts
                }
            )
        ),
        key=f"adjudicate_forbidden_{record.source.id}",
    )
    if not st.button(
        "Lock final gold labels",
        type="primary",
        use_container_width=True,
        key=f"submit_adjudication_{record.source.id}",
    ):
        return
    try:
        service.adjudicate(
            record.source.id,
            adjudicator_id=adjudicator_id,
            decisions=parse_decision_rows(decision_rows),
            actions=parse_action_rows(action_rows),
            forbidden_facts=_nonempty_lines(forbidden_text),
        )
    except (ValueError, OSError) as exc:
        st.error(str(exc))
        return
    st.success("Gold case locked. Corrections require a new meeting-record version.")


def render_consent_and_export(service: AnnotationService) -> None:
    records = service.list_records()
    st.subheader("Consent withdrawal")
    st.caption("Withdrawal deletes the local annotation record and stored transcript.")
    if records:
        record = _select_record("withdraw_meeting", records)
        confirmation = st.text_input(
            f'Type "{record.source.id}" to delete this record',
            key=f"withdraw_confirmation_{record.source.id}",
        )
        if st.button(
            "Delete consented record",
            disabled=confirmation != record.source.id,
            key=f"withdraw_{record.source.id}",
        ):
            service.withdraw_consent(record.source.id)
            st.success("The annotation record and transcript were deleted.")
            st.rerun()
    else:
        st.info("No consented records are stored.")

    st.divider()
    st.subheader("Export adjudicated gold")
    manifest = service.export_adjudicated_manifest()
    st.metric("Adjudicated meetings", len(manifest.cases))
    if not manifest.cases:
        st.caption("Complete two reviews and adjudication before exporting.")
        return

    st.download_button(
        "Download private gold manifest",
        data=manifest.model_dump_json(indent=2),
        file_name="callrhino-consented-gold.json",
        mime="application/json",
        use_container_width=True,
    )
    public_package, gold_package = create_holdout_packages(manifest)
    left, right = st.columns(2)
    left.download_button(
        "Download blind holdout input",
        data=public_package.model_dump_json(indent=2),
        file_name=f"{public_package.package_id}-input.json",
        mime="application/json",
        use_container_width=True,
    )
    right.download_button(
        "Download private holdout gold",
        data=gold_package.model_dump_json(indent=2),
        file_name=f"{gold_package.package_id}-gold.json",
        mime="application/json",
        use_container_width=True,
    )
    st.warning("Keep private gold away from prompt authors and the extraction environment.")


def _select_record(key: str, records: list[AnnotationRecord]) -> AnnotationRecord:
    record_by_id = {record.source.id: record for record in records}
    selected_id = st.selectbox(
        "Meeting",
        options=list(record_by_id),
        format_func=lambda item: f"{item} | {record_by_id[item].source.title}",
        key=key,
    )
    return record_by_id[selected_id]


def _render_transcript(record: AnnotationRecord) -> None:
    st.caption(
        f"{record.source.meeting_date.isoformat()} | "
        f"{len(record.submissions)}/2 reviews submitted"
    )
    st.dataframe(
        [
            {
                "Segment": segment.id,
                "Speaker": segment.speaker_label or "Unknown",
                "Text": segment.text,
            }
            for segment in record.source.reviewed_segments
        ],
        hide_index=True,
        use_container_width=True,
    )


def _blank_decision() -> dict[str, Any]:
    return {
        "item_id": "",
        "text": "",
        "status": DecisionStatus.CONFIRMED.value,
        "decision_maker_text": "",
        "effective_date": "",
        "effective_date_text": "",
        "date_precision": TemporalPrecision.ABSENT.value,
        "evidence_segment_ids": "",
    }


def _blank_action() -> dict[str, Any]:
    return {
        "item_id": "",
        "task": "",
        "commitment_status": CommitmentStatus.COMMITTED.value,
        "owner_text": "",
        "suggested_owner_text": "",
        "due_date": "",
        "due_text": "",
        "deadline_precision": TemporalPrecision.ABSENT.value,
        "evidence_segment_ids": "",
    }


def _merged_decision_rows(record: AnnotationRecord) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for submission in record.submissions:
        for item in submission.decisions:
            rows.setdefault(item.item_id, _decision_row(item))
    return list(rows.values()) or [_blank_decision()]


def _merged_action_rows(record: AnnotationRecord) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for submission in record.submissions:
        for item in submission.actions:
            rows.setdefault(item.item_id, _action_row(item))
    return list(rows.values()) or [_blank_action()]


def _decision_row(item: AnnotatedDecision) -> dict[str, Any]:
    row = item.model_dump(mode="json")
    row["evidence_segment_ids"] = ", ".join(item.evidence_segment_ids)
    return row


def _action_row(item: AnnotatedAction) -> dict[str, Any]:
    row = item.model_dump(mode="json")
    row["evidence_segment_ids"] = ", ".join(item.evidence_segment_ids)
    return row


def _nonempty_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


if __name__ == "__main__":
    main()
