from copy import deepcopy

import pytest
from pydantic import ValidationError

from callrhino.domain.models import ActionItem, MeetingBrief


def test_requested_action_can_name_candidate_without_assigning_them() -> None:
    item = ActionItem.model_validate(
        {
            "task": "Prepare the launch report.",
            "commitment_status": "requested",
            "owner_text": None,
            "owner_basis": "unassigned",
            "suggested_owner_text": "Rohan",
            "due_date": None,
            "due_text": None,
            "deadline_precision": "absent",
            "priority": "unknown",
            "evidence_strength": "explicit",
            "evidence_segment_ids": ["seg_0001"],
            "warnings": [
                "UNACCEPTED_ASSIGNMENT",
                "MISSING_OWNER",
                "MISSING_DEADLINE",
            ],
        }
    )

    assert item.owner_text is None
    assert item.suggested_owner_text == "Rohan"


def test_unassigned_action_cannot_have_canonical_owner() -> None:
    with pytest.raises(ValidationError):
        ActionItem.model_validate(
            {
                "task": "Prepare the launch report.",
                "commitment_status": "requested",
                "owner_text": "Rohan",
                "owner_basis": "unassigned",
                "suggested_owner_text": None,
                "due_date": None,
                "due_text": None,
                "deadline_precision": "absent",
                "priority": "unknown",
                "evidence_strength": "explicit",
                "evidence_segment_ids": ["seg_0001"],
                "warnings": [],
            }
        )


def test_resolved_relative_deadline_requires_date(valid_brief_data: dict) -> None:
    invalid = deepcopy(valid_brief_data)
    invalid["action_items"][0]["due_date"] = None

    with pytest.raises(ValidationError):
        MeetingBrief.model_validate(invalid)


def test_missing_deadline_requires_warning(valid_brief_data: dict) -> None:
    invalid = deepcopy(valid_brief_data)
    item = invalid["action_items"][0]
    item["due_date"] = None
    item["due_text"] = None
    item["deadline_precision"] = "absent"

    with pytest.raises(ValidationError):
        MeetingBrief.model_validate(invalid)


def test_legacy_v1_brief_is_upgraded_on_read(valid_brief_data: dict) -> None:
    legacy = deepcopy(valid_brief_data)
    legacy.pop("schema_version")
    legacy["meeting"]["date_mentioned"] = legacy["meeting"].pop("meeting_date")
    legacy["meeting"].pop("timezone")
    legacy["meeting"].pop("output_language")
    decision = legacy["decisions"][0]
    decision["owner_text"] = decision.pop("decision_maker_text")
    decision["confidence"] = 0.96
    for key in (
        "status",
        "decision_maker_basis",
        "effective_date",
        "effective_date_text",
        "date_precision",
        "evidence_strength",
    ):
        decision.pop(key)
    action = legacy["action_items"][0]
    action["confidence"] = 0.92
    for key in (
        "commitment_status",
        "owner_basis",
        "suggested_owner_text",
        "deadline_precision",
        "evidence_strength",
    ):
        action.pop(key)
    question = legacy["open_questions"][0]
    question["confidence"] = 0.9
    question.pop("status")
    question.pop("evidence_strength")
    risk = legacy["risks"][0]
    risk.pop("kind")
    risk.pop("evidence_strength")

    brief = MeetingBrief.model_validate(legacy)

    assert brief.schema_version == "2.0"
    assert brief.meeting.meeting_date.isoformat() == "2026-07-27"
    assert brief.meeting.timezone == "Asia/Kolkata"
    assert brief.action_items[0].owner_basis.value == "reviewer_confirmed"
