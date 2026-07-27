from datetime import date
from typing import Protocol

from callrhino.domain.models import ApprovedMeeting, MeetingBrief, TranscriptSegment


class MeetingRepository(Protocol):
    def approve_meeting(
        self,
        *,
        series_name: str,
        title: str,
        meeting_date: date,
        source_type: str,
        transcript_text: str,
        segments: list[TranscriptSegment],
        brief: MeetingBrief,
    ) -> str: ...

    def list_meetings(self, *, series_name: str | None = None) -> list[ApprovedMeeting]: ...

    def list_series(self) -> list[str]: ...

