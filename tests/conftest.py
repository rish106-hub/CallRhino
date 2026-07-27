from datetime import date

import pytest

from callrhino.domain.models import MeetingBrief


@pytest.fixture
def valid_brief_data() -> dict:
    return {
        "meeting": {
            "suggested_title": "Weekly Product Review",
            "date_mentioned": None,
            "languages_detected": ["en-IN"],
        },
        "summary": {
            "short": "The team moved the release and assigned the upload fix.",
            "topics": ["release", "onboarding"],
        },
        "decisions": [
            {
                "text": "Move the beta release to 14 August.",
                "owner_text": None,
                "confidence": 0.96,
                "evidence_segment_ids": ["seg_0003"],
                "warnings": [],
            }
        ],
        "action_items": [
            {
                "task": "Fix the upload timeout and open a pull request.",
                "owner_text": "Rohan",
                "due_date": date(2026, 7, 29).isoformat(),
                "due_text": "by Wednesday",
                "priority": "high",
                "confidence": 0.92,
                "evidence_segment_ids": ["seg_0007"],
                "warnings": [],
            }
        ],
        "open_questions": [
            {
                "text": "Can Vikram provide the file set by Tuesday?",
                "confidence": 0.9,
                "evidence_segment_ids": ["seg_0012"],
            }
        ],
        "risks": [
            {
                "text": "The release depends on receiving the test file set.",
                "evidence_segment_ids": ["seg_0012"],
            }
        ],
        "warnings": [],
    }


@pytest.fixture
def valid_brief(valid_brief_data: dict) -> MeetingBrief:
    return MeetingBrief.model_validate(valid_brief_data)

