from callrhino.domain.transcript import format_segments_for_prompt, segment_transcript


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

