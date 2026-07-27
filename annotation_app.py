from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st

from callrhino.annotation import (
    AnnotatedAction,
    AnnotatedDecision,
    AnnotationRecord,
    AnnotationRepositoryError,
    AnnotationService,
    ConsentStatus,
    CoveragePlan,
    JsonAnnotationRepository,
    PiiReviewStatus,
    RedactionStatus,
    ReviewerSubmission,
    SourceMeeting,
    evaluate_coverage,
)
from callrhino.annotation.table import parse_action_rows, parse_decision_rows
from callrhino.domain.models import CommitmentStatus, DecisionStatus, TemporalPrecision
from callrhino.domain.transcript import segment_transcript
from callrhino.evaluation.holdout import HoldoutPackageError, create_holdout_packages
from callrhino.ui.styles import apply_styles

ANNOTATION_ROOT = Path("data/annotations")
DEFAULT_COVERAGE_PLAN = Path("evals/annotation-plan.template.json")

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

    coverage_tab, register_tab, review_tab, adjudicate_tab, export_tab = st.tabs(
        [
            "Coverage",
            "Register meeting",
            "Independent review",
            "Adjudicate",
            "Consent & export",
        ]
    )
    for tab, renderer in (
        (coverage_tab, render_coverage),
        (register_tab, render_registration),
        (review_tab, render_review),
        (adjudicate_tab, render_adjudication),
        (export_tab, render_consent_and_export),
    ):
        with tab:
            try:
                renderer(service)
            except AnnotationRepositoryError as exc:
                st.error(str(exc))


def render_coverage(service: AnnotationService) -> None:
    st.subheader("Evidence collection coverage")
    uploaded_plan = st.file_uploader(
        "Coverage plan",
        type=["json"],
        help="Leave empty to use the strict private-beta template.",
    )
    try:
        plan = CoveragePlan.model_validate_json(
            uploaded_plan.getvalue()
            if uploaded_plan is not None
            else DEFAULT_COVERAGE_PLAN.read_bytes()
        )
        report = evaluate_coverage(plan, service.list_records())
    except (ValueError, OSError) as exc:
        st.error(str(exc))
        return

    first, second, third = st.columns(3)
    first.metric(
        "Adjudicated meetings",
        report.adjudicated_meetings,
        f"{report.remaining_adjudicated_meetings} remaining",
        delta_color="off",
    )
    second.metric(
        "Labelled decisions",
        report.expected_decisions,
        f"{report.remaining_expected_decisions} remaining",
        delta_color="off",
    )
    third.metric(
        "Labelled actions",
        report.expected_actions,
        f"{report.remaining_expected_actions} remaining",
        delta_color="off",
    )
    st.dataframe(
        [quota.model_dump(mode="json") for quota in report.quotas],
        hide_index=True,
        use_container_width=True,
    )
    if report.complete:
        st.success("The annotation coverage plan is complete.")
    else:
        st.warning("This dataset is not ready for a 99.5% release claim.")
        for blocker in report.blockers:
            st.write(f"- {blocker}")


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
    except (ValueError, OSError, AnnotationRepositoryError) as exc:
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
    reviewer_scope = reviewer_id.strip().casefold() or "unidentified"
    decision_key = f"review_decisions_{record.source.id}_{reviewer_scope}"
    action_key = f"review_actions_{record.source.id}_{reviewer_scope}"
    forbidden_key = f"review_forbidden_{record.source.id}_{reviewer_scope}"
    st.markdown("#### Decisions")
    decision_rows = st.data_editor(
        [_blank_decision()],
        column_config=DECISION_COLUMNS,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        key=decision_key,
    )
    st.markdown("#### Actions")
    action_rows = st.data_editor(
        [_blank_action()],
        column_config=ACTION_COLUMNS,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        key=action_key,
    )
    forbidden_text = st.text_area(
        "Facts the extractor must never invent, one per line",
        key=forbidden_key,
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
    except (ValueError, OSError, AnnotationRepositoryError) as exc:
        st.error(str(exc))
        return
    for key in (decision_key, action_key, forbidden_key):
        st.session_state.pop(key, None)
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
    except (ValueError, OSError, AnnotationRepositoryError) as exc:
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
            try:
                service.withdraw_consent(record.source.id)
            except (ValueError, OSError, AnnotationRepositoryError) as exc:
                st.error(str(exc))
                return
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
    try:
        public_package, gold_package = _cached_holdout_packages(manifest)
    except HoldoutPackageError as exc:
        st.error(str(exc))
        return
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
    rows: dict[str, list[dict[str, Any]]] = {}
    for submission in record.submissions:
        for item in submission.decisions:
            rows.setdefault(item.item_id, []).append(_item_row(item))
    return _unbiased_rows(rows, _blank_decision)


def _merged_action_rows(record: AnnotationRecord) -> list[dict[str, Any]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for submission in record.submissions:
        for item in submission.actions:
            rows.setdefault(item.item_id, []).append(_item_row(item))
    return _unbiased_rows(rows, _blank_action)


def _item_row(item: AnnotatedDecision | AnnotatedAction) -> dict[str, Any]:
    row = item.model_dump(mode="json")
    row["evidence_segment_ids"] = ", ".join(item.evidence_segment_ids)
    return row


def _unbiased_rows(
    grouped_rows: dict[str, list[dict[str, Any]]],
    blank_factory: Any,
) -> list[dict[str, Any]]:
    merged = []
    for item_id, reviewer_rows in grouped_rows.items():
        if len(reviewer_rows) == 2 and reviewer_rows[0] == reviewer_rows[1]:
            merged.append(reviewer_rows[0])
            continue
        blank = blank_factory()
        blank["item_id"] = item_id
        merged.append(blank)
    return merged or [blank_factory()]


@st.cache_data(show_spinner=False)
def _cached_holdout_packages(manifest: Any) -> Any:
    return create_holdout_packages(manifest)


def _nonempty_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


if __name__ == "__main__":
    main()
