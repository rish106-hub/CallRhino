from datetime import date

import pytest

from callrhino.domain.models import MeetingBrief


@pytest.fixture
def valid_brief_data() -> dict:
    return {
        "schema_version": "2.0",
        "meeting": {
            "suggested_title": "Weekly Product Review",
            "meeting_date": "2026-07-27",
            "languages_detected": ["en-IN"],
            "timezone": "Asia/Kolkata",
            "output_language": "English",
        },
        "summary": {
            "short": "The team moved the release and assigned the upload fix.",
            "topics": ["release", "onboarding"],
        },
        "decisions": [
            {
                "text": "Move the beta release to 14 August.",
                "status": "confirmed",
                "decision_maker_text": "Product team",
                "decision_maker_basis": "group",
                "effective_date": None,
                "effective_date_text": None,
                "date_precision": "absent",
                "evidence_strength": "explicit",
                "evidence_segment_ids": ["seg_0003"],
                "warnings": [],
            }
        ],
        "action_items": [
            {
                "task": "Fix the upload timeout and open a pull request.",
                "commitment_status": "committed",
                "owner_text": "Rohan",
                "owner_basis": "self_commitment",
                "suggested_owner_text": None,
                "due_date": date(2026, 7, 29).isoformat(),
                "due_text": "by Wednesday",
                "deadline_precision": "resolved_relative",
                "priority": "high",
                "evidence_strength": "explicit",
                "evidence_segment_ids": ["seg_0007"],
                "warnings": [],
            }
        ],
        "open_questions": [
            {
                "text": "Can Vikram provide the file set by Tuesday?",
                "status": "open",
                "evidence_strength": "strong_context",
                "evidence_segment_ids": ["seg_0012"],
            }
        ],
        "risks": [
            {
                "text": "The release depends on receiving the test file set.",
                "kind": "dependency",
                "evidence_strength": "explicit",
                "evidence_segment_ids": ["seg_0012"],
            }
        ],
        "warnings": [],
    }


@pytest.fixture
def valid_brief(valid_brief_data: dict) -> MeetingBrief:
    return MeetingBrief.model_validate(valid_brief_data)


@pytest.fixture
def valid_compact_data() -> dict:
    return {
        "schema_version": "compact-1",
        "summary": "The team moved the release and assigned the upload fix.",
        "topics": ["release", "onboarding"],
        "facts": [
            {
                "kind": "decision",
                "text": "Move the beta release to 14 August.",
                "state": "confirmed",
                "actor_text": "Product team",
                "actor_basis": "group",
                "suggested_actor_text": None,
                "date_text": None,
                "evidence_segment_ids": ["seg_0003"],
            },
            {
                "kind": "action",
                "text": "Fix the upload timeout and open a pull request.",
                "state": "committed",
                "actor_text": "Rohan",
                "actor_basis": "self_commitment",
                "suggested_actor_text": None,
                "date_text": "Wednesday",
                "evidence_segment_ids": ["seg_0007"],
            },
            {
                "kind": "question",
                "text": "Can Vikram provide the file set by Tuesday?",
                "state": "open",
                "actor_text": None,
                "actor_basis": "unassigned",
                "suggested_actor_text": None,
                "date_text": None,
                "evidence_segment_ids": ["seg_0012"],
            },
            {
                "kind": "risk",
                "text": "The release depends on receiving the test file set.",
                "state": "dependency",
                "actor_text": None,
                "actor_basis": "unassigned",
                "suggested_actor_text": None,
                "date_text": None,
                "evidence_segment_ids": ["seg_0012"],
            },
        ],
    }
