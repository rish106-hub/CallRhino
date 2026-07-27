from datetime import date
from typing import Final

from callrhino.domain.models import PendingTranscript, ReviewedTranscript
from callrhino.domain.transcript import (
    apply_speaker_mapping,
    format_reviewed_transcript,
    segment_transcript,
)

MIN_TRANSCRIPT_CHARACTERS: Final = 80


def create_pending_transcript(
    *,
    series_name: str,
    meeting_title: str,
    meeting_date: date,
    source_type: str,
    transcript_text: str,
) -> PendingTranscript:
    normalized_series = series_name.strip()
    normalized_title = meeting_title.strip()
    _validate_transcript(transcript_text)

    return PendingTranscript(
        series_name=normalized_series,
        meeting_title=normalized_title,
        meeting_date=meeting_date,
        source_type=source_type,
        transcript_text=transcript_text,
        segments=segment_transcript(transcript_text),
    )


def confirm_transcript_review(
    pending: PendingTranscript,
    *,
    transcript_text: str,
    speaker_mapping: dict[str, str],
) -> ReviewedTranscript:
    _validate_transcript(transcript_text)
    segments = segment_transcript(transcript_text)
    mapped_segments = apply_speaker_mapping(segments, speaker_mapping)

    return ReviewedTranscript(
        series_name=pending.series_name,
        meeting_title=pending.meeting_title,
        meeting_date=pending.meeting_date,
        source_type=pending.source_type,
        transcript_text=format_reviewed_transcript(mapped_segments),
        segments=mapped_segments,
    )


def _validate_transcript(transcript_text: str) -> None:
    if len(transcript_text.strip()) < MIN_TRANSCRIPT_CHARACTERS:
        raise ValueError("The transcript is too short to process.")
