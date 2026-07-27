import json
from copy import deepcopy
from datetime import date

from callrhino.domain.transcript import segment_transcript
from callrhino.services.extraction import MeetingExtractor
from callrhino.services.sarvam import StructuredChatResult, TokenUsage


class FakeGenerator:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def generate_structured(self, **kwargs: object) -> StructuredChatResult:
        self.calls.append(kwargs)
        data = self.responses.pop(0)
        return StructuredChatResult(
            content=json.dumps(data),
            data=data,
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            model="sarvam-30b",
            request_id="chat_test",
        )


def test_extracts_and_validates_brief(valid_brief_data: dict) -> None:
    generator = FakeGenerator([valid_brief_data])
    extractor = MeetingExtractor(generator)
    segments = segment_transcript(
        "\n".join(f"Speaker: Segment {index}" for index in range(1, 13))
    )

    result = extractor.extract(
        meeting_date=date(2026, 7, 27),
        series_name="Weekly Product Review",
        meeting_title="Launch review",
        segments=segments,
    )

    assert result.brief.action_items[0].owner_text == "Rohan"
    assert result.usage.total_tokens == 150
    assert result.repaired is False
    assert len(generator.calls) == 1


def test_repairs_unknown_evidence_once(valid_brief_data: dict) -> None:
    invalid = deepcopy(valid_brief_data)
    invalid["decisions"][0]["evidence_segment_ids"] = ["seg_9999"]
    generator = FakeGenerator([invalid, valid_brief_data])
    extractor = MeetingExtractor(generator)
    segments = segment_transcript(
        "\n".join(f"Speaker: Segment {index}" for index in range(1, 13))
    )

    result = extractor.extract(
        meeting_date=date(2026, 7, 27),
        series_name="Weekly Product Review",
        meeting_title="Launch review",
        segments=segments,
    )

    assert result.repaired is True
    assert len(generator.calls) == 2
    repair_messages = generator.calls[1]["messages"]
    assert "Unknown evidence segment IDs" in repair_messages[-1]["content"]

