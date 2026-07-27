import pytest

from callrhino.domain.transcript import (
    apply_speaker_mapping,
    detected_speaker_labels,
    format_reviewed_transcript,
    format_segments_for_prompt,
    segment_transcript,
)


def test_segments_speaker_lines_and_continuations() -> None:
    transcript = """\
[00:00] Aditi: We need to move the launch.
The upload issue is still open.
[00:15] Rohan: I can fix it by Wednesday.
"""

    segments = segment_transcript(transcript)

    assert len(segments) == 2
    assert segments[0].id == "seg_0001"
    assert segments[0].speaker_label == "Aditi"
    assert segments[0].start_ms == 0
    assert segments[0].text == "We need to move the launch. The upload issue is still open."
    assert segments[1].start_ms == 15_000


def test_formats_stable_ids_for_prompt() -> None:
    segments = segment_transcript("Aditi: Ship Friday.\nRohan: I own the fix.")

    formatted = format_segments_for_prompt(segments)

    assert "[seg_0001] Aditi: Ship Friday." in formatted
    assert "[seg_0002] Rohan: I own the fix." in formatted


def test_rejects_empty_transcript() -> None:
    try:
        segment_transcript(" \n ")
    except ValueError as exc:
        assert str(exc) == "Transcript is empty."
    else:
        raise AssertionError("empty transcript should fail")


def test_detects_speakers_in_first_appearance_order() -> None:
    segments = segment_transcript(
        "Speaker 2: Opening.\n"
        "Speaker 1: Reply.\n"
        "Speaker 2: Follow-up.\n"
        "A line without a speaker after a blank line."
    )

    assert detected_speaker_labels(segments) == ["Speaker 2", "Speaker 1"]


def test_applies_speaker_mapping_without_changing_segment_evidence() -> None:
    segments = segment_transcript(
        "[00:01] Speaker 0: Rohan said Speaker 1 owns the fix.\n"
        "[00:04] Speaker 1: I will send it."
    )
    segments[0] = segments[0].model_copy(update={"end_ms": 3_500})

    mapped = apply_speaker_mapping(
        segments,
        {"Speaker 0": " Aditi ", "Speaker 1": "Rohan"},
    )

    assert [segment.speaker_label for segment in mapped] == ["Aditi", "Rohan"]
    assert [segment.id for segment in mapped] == ["seg_0001", "seg_0002"]
    assert [segment.sequence_no for segment in mapped] == [1, 2]
    assert [segment.start_ms for segment in mapped] == [1_000, 4_000]
    assert [segment.end_ms for segment in mapped] == [3_500, None]
    assert mapped[0].text == "Rohan said Speaker 1 owns the fix."
    assert segments[0].speaker_label == "Speaker 0"


def test_allows_multiple_labels_to_map_to_one_speaker() -> None:
    segments = segment_transcript(
        "Speaker 0: First part.\nSpeaker 1: Second part.\nSpeaker 0: Third part."
    )

    mapped = apply_speaker_mapping(
        segments,
        {"Speaker 0": "Aditi", "Speaker 1": "Aditi"},
    )

    assert [segment.speaker_label for segment in mapped] == ["Aditi", "Aditi", "Aditi"]
    assert [segment.text for segment in mapped] == [
        "First part.",
        "Second part.",
        "Third part.",
    ]


def test_rejects_an_empty_speaker_name() -> None:
    segments = segment_transcript("Speaker 0: This is enough text for one segment.")

    with pytest.raises(ValueError, match='Add a name for speaker "Speaker 0"'):
        apply_speaker_mapping(segments, {"Speaker 0": "  "})


def test_formats_reviewed_segments_with_mapped_speakers_and_timestamps() -> None:
    segments = segment_transcript(
        "[00:01] Speaker 0: Opening.\n[01:02:03] Speaker 1: Reply."
    )
    mapped = apply_speaker_mapping(
        segments,
        {"Speaker 0": "Aditi", "Speaker 1": "Rohan"},
    )

    assert format_reviewed_transcript(mapped) == (
        "[00:01] Aditi: Opening.\n[01:02:03] Rohan: Reply."
    )
