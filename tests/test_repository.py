from datetime import date

from callrhino.domain.transcript import segment_transcript
from callrhino.repositories.sqlite import SQLiteMeetingRepository


def test_approved_meeting_round_trip(tmp_path, valid_brief) -> None:
    repository = SQLiteMeetingRepository(tmp_path / "callrhino.db")
    transcript = "Aditi: Move the release.\nRohan: I will fix the upload."
    segments = segment_transcript(transcript)

    meeting_id = repository.approve_meeting(
        series_name="Weekly Product Review",
        title="Launch review",
        meeting_date=date(2026, 7, 27),
        source_type="pasted",
        transcript_text=transcript,
        segments=segments,
        brief=valid_brief,
    )

    meetings = repository.list_meetings(series_name="weekly product review")

    assert len(meetings) == 1
    assert meetings[0].id == meeting_id
    assert meetings[0].brief.decisions[0].text.startswith("Move the beta")
    assert repository.list_series() == ["Weekly Product Review"]

