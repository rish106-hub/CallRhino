import re
from collections.abc import Iterable, Mapping

from callrhino.domain.models import TranscriptSegment

SPEAKER_LINE = re.compile(
    r"^(?:\[(?P<timestamp>\d{1,2}:\d{2}(?::\d{2})?)\]\s*)?"
    r"(?P<speaker>[A-Za-z][A-Za-z0-9 ._'-]{0,60}):\s*(?P<text>.+)$"
)


def _timestamp_to_ms(value: str | None) -> int | None:
    if value is None:
        return None
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        return (minutes * 60 + seconds) * 1000
    hours, minutes, seconds = parts
    return (hours * 3600 + minutes * 60 + seconds) * 1000


def _clean_lines(transcript: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in transcript.splitlines()]


def segment_transcript(transcript: str) -> list[TranscriptSegment]:
    if not transcript or not transcript.strip():
        raise ValueError("Transcript is empty.")

    raw_segments: list[dict[str, str | int | None]] = []
    current: dict[str, str | int | None] | None = None

    for line in _clean_lines(transcript):
        if not line:
            if current:
                raw_segments.append(current)
                current = None
            continue

        match = SPEAKER_LINE.match(line)
        if match:
            if current:
                raw_segments.append(current)
            current = {
                "speaker": match.group("speaker").strip(),
                "start_ms": _timestamp_to_ms(match.group("timestamp")),
                "text": match.group("text").strip(),
            }
            continue

        if current:
            current["text"] = f"{current['text']} {line}".strip()
        else:
            current = {"speaker": None, "start_ms": None, "text": line}

    if current:
        raw_segments.append(current)

    return [
        TranscriptSegment(
            id=f"seg_{index:04d}",
            sequence_no=index,
            speaker_label=segment["speaker"] if isinstance(segment["speaker"], str) else None,
            start_ms=segment["start_ms"] if isinstance(segment["start_ms"], int) else None,
            end_ms=None,
            text=str(segment["text"]),
        )
        for index, segment in enumerate(raw_segments, start=1)
    ]


def format_segments_for_prompt(segments: Iterable[TranscriptSegment]) -> str:
    lines = []
    for segment in segments:
        speaker = f"{segment.speaker_label}: " if segment.speaker_label else ""
        lines.append(f"[{segment.id}] {speaker}{segment.text}")
    return "\n".join(lines)


def detected_speaker_labels(segments: Iterable[TranscriptSegment]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for segment in segments:
        label = segment.speaker_label
        if label is not None and label not in seen:
            labels.append(label)
            seen.add(label)
    return labels


def apply_speaker_mapping(
    segments: Iterable[TranscriptSegment],
    speaker_mapping: Mapping[str, str],
) -> list[TranscriptSegment]:
    ordered_segments = list(segments)
    detected_labels = set(detected_speaker_labels(ordered_segments))
    normalized_mapping: dict[str, str] = {}

    for source_label, target_label in speaker_mapping.items():
        if source_label not in detected_labels:
            continue
        normalized_target = target_label.strip()
        if not normalized_target:
            raise ValueError(f'Add a name for speaker "{source_label}".')
        normalized_mapping[source_label] = normalized_target

    return [
        segment.model_copy(
            update={
                "speaker_label": normalized_mapping.get(
                    segment.speaker_label,
                    segment.speaker_label,
                )
            }
        )
        for segment in ordered_segments
    ]


def format_reviewed_transcript(segments: Iterable[TranscriptSegment]) -> str:
    lines = []
    for segment in segments:
        timestamp = (
            f"[{_milliseconds_to_timestamp(segment.start_ms)}] "
            if segment.start_ms is not None
            else ""
        )
        speaker = f"{segment.speaker_label}: " if segment.speaker_label else ""
        lines.append(f"{timestamp}{speaker}{segment.text}")
    return "\n".join(lines)


def _milliseconds_to_timestamp(value: int) -> str:
    total_seconds = value // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"
