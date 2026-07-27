from datetime import date

from callrhino.domain.compact import CompactExtraction
from callrhino.domain.transcript import segment_transcript
from callrhino.services.compiler import compile_meeting_brief


def test_compiler_deduplicates_facts_and_derives_mechanical_fields() -> None:
    compact = CompactExtraction.model_validate(
        {
            "schema_version": "compact-1",
            "summary": "Rohan committed to the report.",
            "topics": ["report"],
            "facts": [
                {
                    "kind": "action",
                    "text": "Send the report by Friday.",
                    "state": "committed",
                    "actor_text": "Rohan",
                    "actor_basis": "self_commitment",
                    "suggested_actor_text": None,
                    "date_text": "Friday",
                    "evidence_segment_ids": ["seg_0001"],
                },
                {
                    "kind": "action",
                    "text": "Send the report by Friday.",
                    "state": "committed",
                    "actor_text": "Rohan",
                    "actor_basis": "self_commitment",
                    "suggested_actor_text": None,
                    "date_text": "Friday",
                    "evidence_segment_ids": ["seg_0001"],
                },
            ],
        }
    )
    segments = segment_transcript("Rohan: I will send the report by Friday.")

    brief = compile_meeting_brief(
        compact,
        meeting_date=date(2026, 7, 27),
        meeting_title="Weekly review",
        timezone="Asia/Kolkata",
        output_language="English",
        segments=segments,
    )

    assert len(brief.action_items) == 1
    action = brief.action_items[0]
    assert action.due_date == date(2026, 7, 31)
    assert action.deadline_precision.value == "resolved_relative"
    assert action.priority.value == "unknown"
    assert brief.meeting.languages_detected == ["en-IN"]


def test_compiler_uses_explicit_date_from_fact_text_when_phrase_field_is_missing() -> None:
    compact = CompactExtraction.model_validate(
        {
            "schema_version": "compact-1",
            "summary": "The launch was cancelled.",
            "topics": ["launch"],
            "facts": [
                {
                    "kind": "decision",
                    "text": "Cancel the 30 July launch.",
                    "state": "reversed",
                    "actor_text": "Neha",
                    "actor_basis": "explicit",
                    "suggested_actor_text": None,
                    "date_text": None,
                    "evidence_segment_ids": ["seg_0001"],
                }
            ],
        }
    )

    brief = compile_meeting_brief(
        compact,
        meeting_date=date(2026, 7, 27),
        meeting_title="Release review",
        timezone="Asia/Kolkata",
        output_language="English",
        segments=segment_transcript("Neha: Cancel the 30 July launch."),
    )

    decision = brief.decisions[0]
    assert decision.effective_date == date(2026, 7, 30)
    assert decision.effective_date_text == "30 July"
    assert decision.date_precision.value == "exact"


def test_compiler_ignores_date_not_grounded_in_cited_evidence() -> None:
    compact = CompactExtraction.model_validate(
        {
            "schema_version": "compact-1",
            "summary": "The budget was approved.",
            "topics": ["budget"],
            "facts": [
                {
                    "kind": "decision",
                    "text": "Approve the budget cap.",
                    "state": "confirmed",
                    "actor_text": "Vikram",
                    "actor_basis": "explicit",
                    "suggested_actor_text": None,
                    "date_text": "2026-07-27",
                    "evidence_segment_ids": ["seg_0001"],
                }
            ],
        }
    )

    brief = compile_meeting_brief(
        compact,
        meeting_date=date(2026, 7, 27),
        meeting_title="Budget review",
        timezone="Asia/Kolkata",
        output_language="English",
        segments=segment_transcript("Vikram: Approved. Cap total spend at ₹2 lakh."),
    )

    decision = brief.decisions[0]
    assert decision.effective_date is None
    assert decision.effective_date_text is None
    assert decision.date_precision.value == "absent"
