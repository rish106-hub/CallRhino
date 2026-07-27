from callrhino.domain.transcript import segment_transcript
from callrhino.services.candidates import select_candidate_segments


def _long_transcript(overrides: dict[int, str] | None = None) -> list:
    overrides = overrides or {}
    lines = [
        f"Speaker {index % 3}: {overrides.get(index, f'General discussion segment {index}.')}"
        for index in range(30)
    ]
    return segment_transcript("\n".join(lines))


def test_short_meetings_bypass_candidate_filter() -> None:
    segments = segment_transcript(
        "Aditi: We approved the release.\nRohan: I will ship it by Friday."
    )

    selection = select_candidate_segments(segments)

    assert selection.filtered is False
    assert selection.segments == segments
    assert selection.reduction_ratio == 0


def test_long_meeting_keeps_cues_context_and_original_ids() -> None:
    segments = _long_transcript(
        {
            12: "The upload is blocked by the vendor API.",
            18: "Main revised report Friday tak bhej dunga.",
        }
    )

    selection = select_candidate_segments(segments)

    assert selection.filtered is True
    assert selection.selected_segment_count < selection.original_segment_count
    assert selection.cue_segment_count == 2
    assert {segment.sequence_no for segment in selection.segments} >= {
        1,
        11,
        12,
        13,
        14,
        15,
        17,
        18,
        19,
        20,
        21,
        30,
    }
    assert all(
        segment.id == f"seg_{segment.sequence_no:04d}" for segment in selection.segments
    )


def test_long_meeting_without_cues_fails_open() -> None:
    segments = _long_transcript()

    selection = select_candidate_segments(segments)

    assert selection.filtered is False
    assert selection.segments == segments


def test_dense_candidate_meeting_fails_open() -> None:
    segments = _long_transcript(
        {index: "We will decide and follow up." for index in range(30)}
    )

    selection = select_candidate_segments(segments)

    assert selection.filtered is False
    assert selection.segments == segments
