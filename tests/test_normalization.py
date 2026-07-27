from datetime import date

from callrhino.domain.transcript import segment_transcript
from callrhino.services.normalization import normalize_brief_payload, resolve_date_phrase


def test_resolves_supported_indian_meeting_date_phrases() -> None:
    meeting_date = date(2026, 7, 27)

    assert resolve_date_phrase("Wednesday tak", meeting_date) == (
        date(2026, 7, 29),
        "resolved_relative",
    )
    assert resolve_date_phrase("Friday ko", meeting_date) == (
        date(2026, 7, 31),
        "resolved_relative",
    )
    assert resolve_date_phrase("innikku", meeting_date) == (
        meeting_date,
        "resolved_relative",
    )
    assert resolve_date_phrase("by 31 July", meeting_date) == (
        date(2026, 7, 31),
        "exact",
    )
    assert resolve_date_phrase("kal", meeting_date) is None
    assert resolve_date_phrase("next Friday", meeting_date) is None


def test_normalizes_mechanical_action_contract_without_inventing_owner() -> None:
    payload = {
        "meeting": {
            "meeting_date": "2025-01-01",
            "timezone": "UTC",
            "output_language": "Hindi",
        },
        "action_items": [
            {
                "owner_text": None,
                "owner_basis": "unassigned",
                "suggested_owner_text": "Kunal",
                "due_date": "2026-07-28",
                "due_text": None,
                "deadline_precision": "resolved_relative",
                "evidence_strength": "ambiguous",
                "warnings": [],
            }
        ],
        "decisions": [],
    }

    normalized = normalize_brief_payload(
        payload,
        meeting_date=date(2026, 7, 27),
        timezone="Asia/Kolkata",
        output_language="English",
    )
    action = normalized["action_items"][0]

    assert normalized["meeting"]["meeting_date"] == "2026-07-27"
    assert normalized["meeting"]["timezone"] == "Asia/Kolkata"
    assert normalized["meeting"]["output_language"] == "English"
    assert action["owner_text"] is None
    assert action["deadline_precision"] == "resolved_relative"
    assert "MISSING_OWNER" in action["warnings"]
    assert "UNACCEPTED_ASSIGNMENT" in action["warnings"]
    assert "LOW_CONFIDENCE" in action["warnings"]


def test_normalizes_vague_and_relative_deadlines() -> None:
    payload = {
        "meeting": {},
        "action_items": [
            {
                "due_date": "2026-07-28",
                "due_text": "jaldi",
                "deadline_precision": "resolved_relative",
                "warnings": [],
            },
            {
                "due_date": "2026-07-30",
                "due_text": "Wednesday tak",
                "deadline_precision": "exact",
                "warnings": [],
            },
        ],
        "decisions": [],
    }

    normalized = normalize_brief_payload(
        payload,
        meeting_date=date(2026, 7, 27),
        timezone="Asia/Kolkata",
        output_language="English",
    )

    vague, relative = normalized["action_items"]
    assert vague["due_date"] is None
    assert vague["deadline_precision"] == "vague"
    assert "VAGUE_DEADLINE" in vague["warnings"]
    assert relative["due_date"] == "2026-07-29"
    assert relative["deadline_precision"] == "resolved_relative"


def test_removes_inferred_priority_and_stale_deadline_warning() -> None:
    payload = {
        "meeting": {},
        "action_items": [
            {
                "priority": "high",
                "due_date": "2026-07-28",
                "due_text": "EOD",
                "deadline_precision": "vague",
                "warnings": ["VAGUE_DEADLINE"],
                "evidence_segment_ids": ["seg_0001"],
            }
        ],
        "decisions": [],
    }

    normalized = normalize_brief_payload(
        payload,
        meeting_date=date(2026, 7, 27),
        timezone="Asia/Kolkata",
        output_language="English",
        segments=segment_transcript("Meera: Please send this by EOD."),
    )
    action = normalized["action_items"][0]

    assert action["priority"] == "unknown"
    assert action["due_date"] == "2026-07-27"
    assert action["deadline_precision"] == "resolved_relative"
    assert "VAGUE_DEADLINE" not in action["warnings"]


def test_removes_duplicate_operational_action_and_its_warning() -> None:
    payload = {
        "meeting": {},
        "decisions": [
            {
                "text": "Keep the owner open until finance approval.",
                "evidence_segment_ids": ["seg_0002", "seg_0003"],
            }
        ],
        "action_items": [
            {
                "task": "Send the updated PO.",
                "commitment_status": "requested",
                "owner_basis": "unassigned",
                "owner_text": None,
                "suggested_owner_text": "Kunal",
                "due_date": None,
                "due_text": "EOD",
                "deadline_precision": "resolved_relative",
                "evidence_strength": "explicit",
                "priority": "unknown",
                "evidence_segment_ids": ["seg_0001", "seg_0002"],
                "warnings": ["MISSING_OWNER", "UNACCEPTED_ASSIGNMENT"],
            },
            {
                "task": "Keep the owner open until approval.",
                "commitment_status": "committed",
                "owner_basis": "group_commitment",
                "owner_text": "Meera",
                "suggested_owner_text": None,
                "due_date": None,
                "due_text": None,
                "deadline_precision": "absent",
                "evidence_strength": "explicit",
                "priority": "unknown",
                "evidence_segment_ids": ["seg_0002", "seg_0003"],
                "warnings": ["MISSING_DEADLINE"],
            },
        ],
        "warnings": [
            {
                "code": "MISSING_OWNER",
                "message": "The PO action has no accepted owner.",
                "related_item_type": "action_item",
                "related_item_index": 0,
            },
            {
                "code": "MISSING_DEADLINE",
                "message": "The duplicate state action has no deadline.",
                "related_item_type": "action_item",
                "related_item_index": 1,
            },
        ],
    }

    normalized = normalize_brief_payload(
        payload,
        meeting_date=date(2026, 7, 27),
        timezone="Asia/Kolkata",
        output_language="English",
        segments=segment_transcript(
            "Meera: Send the updated PO by EOD.\n"
            "Kunal: I cannot commit before finance approval.\n"
            "Meera: Keep the owner open until approval."
        ),
    )

    assert [item["task"] for item in normalized["action_items"]] == [
        "Send the updated PO."
    ]
    assert normalized["warnings"] == [
        {
            "code": "MISSING_OWNER",
            "message": "The PO action has no accepted owner.",
            "related_item_type": "action_item",
            "related_item_index": 0,
        }
    ]


def test_removes_top_level_warning_after_local_deadline_resolution() -> None:
    payload = {
        "meeting": {},
        "decisions": [],
        "action_items": [
            {
                "task": "Send the PO.",
                "owner_basis": "self_commitment",
                "owner_text": "Meera",
                "suggested_owner_text": None,
                "due_date": None,
                "due_text": "EOD",
                "deadline_precision": "vague",
                "evidence_strength": "explicit",
                "priority": "unknown",
                "evidence_segment_ids": ["seg_0001"],
                "warnings": ["VAGUE_DEADLINE"],
            }
        ],
        "warnings": [
            {
                "code": "VAGUE_DEADLINE",
                "message": "EOD is vague.",
                "related_item_type": "action_item",
                "related_item_index": 0,
            }
        ],
    }

    normalized = normalize_brief_payload(
        payload,
        meeting_date=date(2026, 7, 27),
        timezone="Asia/Kolkata",
        output_language="English",
        segments=segment_transcript("Meera: I will send the PO by EOD."),
    )

    assert normalized["action_items"][0]["deadline_precision"] == "resolved_relative"
    assert normalized["warnings"] == []


def test_removes_decision_that_duplicates_same_owner_commitment() -> None:
    payload = {
        "meeting": {},
        "decisions": [
            {
                "text": "Priya's team will share the Hindi dashboard soon.",
                "status": "confirmed",
                "decision_maker_text": "Priya's team",
                "evidence_segment_ids": ["seg_0002"],
            }
        ],
        "action_items": [
            {
                "task": "Share the Hindi dashboard.",
                "commitment_status": "committed",
                "owner_text": "Priya's team",
                "owner_basis": "group_commitment",
                "suggested_owner_text": None,
                "due_date": None,
                "due_text": "jaldi",
                "deadline_precision": "vague",
                "evidence_strength": "strong_context",
                "priority": "unknown",
                "evidence_segment_ids": ["seg_0001", "seg_0002"],
                "warnings": ["VAGUE_DEADLINE"],
            }
        ],
        "warnings": [],
    }

    normalized = normalize_brief_payload(
        payload,
        meeting_date=date(2026, 7, 27),
        timezone="Asia/Kolkata",
        output_language="English",
        segments=segment_transcript(
            "Client: When will we get the Hindi dashboard?\n"
            "Priya: Hum jaldi share kar denge."
        ),
    )

    assert normalized["decisions"] == []
    assert len(normalized["action_items"]) == 1


def test_removes_decision_date_not_supported_by_evidence() -> None:
    payload = {
        "meeting": {},
        "decisions": [
            {
                "text": "Approve the agency quote.",
                "status": "confirmed",
                "decision_maker_text": "Vikram",
                "effective_date": "2026-07-27",
                "effective_date_text": "today",
                "date_precision": "resolved_relative",
                "evidence_segment_ids": ["seg_0001"],
            }
        ],
        "action_items": [],
        "warnings": [],
    }

    normalized = normalize_brief_payload(
        payload,
        meeting_date=date(2026, 7, 27),
        timezone="Asia/Kolkata",
        output_language="English",
        segments=segment_transcript("Vikram: Approved the agency quote."),
    )

    decision = normalized["decisions"][0]
    assert decision["effective_date"] is None
    assert decision["effective_date_text"] is None
    assert decision["date_precision"] == "absent"
