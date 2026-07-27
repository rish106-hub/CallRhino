import json
from copy import deepcopy
from datetime import date

from callrhino.domain.transcript import segment_transcript
from callrhino.services.extraction import CompactMeetingExtractor, MeetingExtractor
from callrhino.services.sarvam import (
    SarvamResponseError,
    StructuredChatResult,
    TokenUsage,
)


class FakeGenerator:
    def __init__(self, responses: list[dict | Exception]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def generate_structured(self, **kwargs: object) -> StructuredChatResult:
        self.calls.append(kwargs)
        data = self.responses.pop(0)
        if isinstance(data, Exception):
            raise data
        return StructuredChatResult(
            content=json.dumps(data),
            data=data,
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            model="sarvam-105b",
            request_id="chat_test",
        )


def _segments() -> list:
    lines = [f"Speaker: Segment {index}" for index in range(1, 13)]
    lines[6] = "Rohan: I will fix the upload timeout by Wednesday."
    return segment_transcript("\n".join(lines))


def test_compiles_compact_extraction_into_canonical_brief(
    valid_compact_data: dict,
) -> None:
    generator = FakeGenerator([valid_compact_data])

    result = CompactMeetingExtractor(generator).extract(
        meeting_date=date(2026, 7, 27),
        series_name="Weekly Product Review",
        meeting_title="Launch review",
        segments=_segments(),
    )

    action = result.brief.action_items[0]
    assert action.owner_text == "Rohan"
    assert action.owner_basis.value == "self_commitment"
    assert action.due_date == date(2026, 7, 29)
    assert action.deadline_precision.value == "resolved_relative"
    assert result.usage.total_tokens == 150
    assert result.repaired is False
    assert generator.calls[0]["schema_name"] == "compact_meeting_facts"


def test_repairs_unknown_evidence_once(valid_compact_data: dict) -> None:
    invalid = deepcopy(valid_compact_data)
    invalid["facts"][0]["evidence_segment_ids"] = ["seg_9999"]
    generator = FakeGenerator([invalid, valid_compact_data])

    result = CompactMeetingExtractor(generator).extract(
        meeting_date=date(2026, 7, 27),
        series_name="Weekly Product Review",
        meeting_title="Launch review",
        segments=_segments(),
    )

    assert result.repaired is True
    assert result.usage.total_tokens == 300
    assert len(generator.calls) == 2
    assert "Unknown evidence segment IDs" in generator.calls[1]["messages"][-1]["content"]


def test_repairs_incompatible_fact_state(valid_compact_data: dict) -> None:
    invalid = deepcopy(valid_compact_data)
    invalid["facts"][0]["state"] = "committed"
    generator = FakeGenerator([invalid, valid_compact_data])

    result = CompactMeetingExtractor(generator).extract(
        meeting_date=date(2026, 7, 27),
        series_name="Weekly Product Review",
        meeting_title="Launch review",
        segments=_segments(),
    )

    assert result.repaired is True
    assert "not valid for" in generator.calls[1]["messages"][-1]["content"]


def test_compiler_adds_missing_contract_fields_without_paid_repair(
    valid_compact_data: dict,
) -> None:
    compact = deepcopy(valid_compact_data)
    action = compact["facts"][1]
    action.update(
        {
            "state": "requested",
            "actor_text": None,
            "actor_basis": "unassigned",
            "suggested_actor_text": "Rohan",
            "date_text": None,
            "evidence_segment_ids": ["seg_0008"],
        }
    )
    generator = FakeGenerator([compact])

    result = CompactMeetingExtractor(generator).extract(
        meeting_date=date(2026, 7, 27),
        series_name="Weekly Product Review",
        meeting_title="Launch review",
        segments=_segments(),
    )

    assert result.repaired is False
    assert len(generator.calls) == 1
    item = result.brief.action_items[0]
    assert item.owner_text is None
    assert item.deadline_precision.value == "absent"
    assert {warning.value for warning in item.warnings} == {
        "MISSING_OWNER",
        "UNACCEPTED_ASSIGNMENT",
        "MISSING_DEADLINE",
    }


def test_generic_group_actor_fails_safe_without_repair(valid_compact_data: dict) -> None:
    compact = deepcopy(valid_compact_data)
    compact["facts"][1]["actor_text"] = "We"
    compact["facts"][1]["actor_basis"] = "group_commitment"
    generator = FakeGenerator([compact])

    result = CompactMeetingExtractor(generator).extract(
        meeting_date=date(2026, 7, 27),
        series_name="Weekly Product Review",
        meeting_title="Launch review",
        segments=_segments(),
    )

    item = result.brief.action_items[0]
    assert result.repaired is False
    assert item.owner_text is None
    assert item.owner_basis.value == "unassigned"
    assert {warning.value for warning in item.warnings} >= {
        "MISSING_OWNER",
        "UNCLEAR_SPEAKER",
    }


def test_canonical_extractor_is_the_product_default(valid_brief_data: dict) -> None:
    generator = FakeGenerator([valid_brief_data])

    result = MeetingExtractor(generator).extract(
        meeting_date=date(2026, 7, 27),
        series_name="Weekly Product Review",
        meeting_title="Launch review",
        segments=_segments(),
    )

    assert generator.calls[0]["schema_name"] == "meeting_brief"
    assert result.brief.action_items[0].owner_text == "Rohan"
    assert result.original_segment_count == 12
    assert result.selected_segment_count == 12


def test_canonical_extractor_keeps_long_transcripts_by_default(
    valid_brief_data: dict,
) -> None:
    empty_brief = deepcopy(valid_brief_data)
    empty_brief["decisions"] = []
    empty_brief["action_items"] = []
    empty_brief["open_questions"] = []
    empty_brief["risks"] = []
    empty_brief["warnings"] = []
    lines = [f"Speaker: General discussion segment {index}." for index in range(30)]
    lines[14] = "Rohan: I will send the final report by Friday."
    generator = FakeGenerator([empty_brief])

    result = MeetingExtractor(generator).extract(
        meeting_date=date(2026, 7, 27),
        series_name="Weekly Product Review",
        meeting_title="Launch review",
        segments=segment_transcript("\n".join(lines)),
    )

    prompt = generator.calls[0]["messages"][1]["content"]
    assert result.original_segment_count == 30
    assert result.selected_segment_count == 30
    assert "[seg_0015]" in prompt
    assert "[seg_0002]" in prompt


def test_canonical_extractor_can_gate_long_transcripts(
    valid_brief_data: dict,
) -> None:
    empty_brief = deepcopy(valid_brief_data)
    empty_brief["decisions"] = []
    empty_brief["action_items"] = []
    empty_brief["open_questions"] = []
    empty_brief["risks"] = []
    empty_brief["warnings"] = []
    lines = [f"Speaker: General discussion segment {index}." for index in range(30)]
    lines[14] = "Rohan: I will send the final report by Friday."
    generator = FakeGenerator([empty_brief])

    result = MeetingExtractor(
        generator,
        candidate_gating_enabled=True,
    ).extract(
        meeting_date=date(2026, 7, 27),
        series_name="Weekly Product Review",
        meeting_title="Launch review",
        segments=segment_transcript("\n".join(lines)),
    )

    prompt = generator.calls[0]["messages"][1]["content"]
    assert result.original_segment_count == 30
    assert result.selected_segment_count < 30
    assert "[seg_0015]" in prompt
    assert "[seg_0002]" not in prompt


def test_canonical_extractor_retries_truncated_generation_once(
    valid_brief_data: dict,
) -> None:
    truncated = SarvamResponseError(
        "Sarvam returned an invalid structured response (finish_reason=length).",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=4096, total_tokens=4196),
    )
    generator = FakeGenerator([truncated, valid_brief_data])

    result = MeetingExtractor(generator).extract(
        meeting_date=date(2026, 7, 27),
        series_name="Weekly Product Review",
        meeting_title="Launch review",
        segments=_segments(),
    )

    assert result.repaired is True
    assert result.usage.total_tokens == 4346
    assert len(generator.calls) == 2
    assert "no repeated text" in generator.calls[1]["messages"][-1]["content"]
