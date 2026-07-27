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
