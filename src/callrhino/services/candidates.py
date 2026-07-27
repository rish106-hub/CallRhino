import re
from dataclasses import dataclass

from callrhino.domain.models import TranscriptSegment

MIN_SEGMENTS_TO_FILTER = 24
CONTEXT_RADIUS = 2
MAX_SELECTION_RATIO = 0.85

CANDIDATE_CUES = re.compile(
    r"""
    \?|
    \b(
        action|agree|agreed|approval|approve|approved|assign|assigned|
        block|blocked|blocker|cancel|cancelled|commit|committed|critical|
        decide|decided|decision|defer|deferred|deliver|dependency|due|
        eod|final|fix|follow[\s-]?up|high[\s-]?priority|issue|launch|
        must|owner|please|reject|rejected|resolve|reverse|reversed|risk|
        should|ship|timeline|urgent|waiting|will|won't|would|
        aaj|bhej|dunga|dungi|jaldi|kab|karenge|karunga|karungi|main|
        panren|pannala|share|theek|innikku
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True)
class CandidateSelection:
    segments: list[TranscriptSegment]
    original_segment_count: int
    selected_segment_count: int
    cue_segment_count: int
    filtered: bool

    @property
    def reduction_ratio(self) -> float:
        if self.original_segment_count == 0:
            return 0
        return 1 - (self.selected_segment_count / self.original_segment_count)


def select_candidate_segments(
    segments: list[TranscriptSegment],
    *,
    enabled: bool = True,
    minimum_segments: int = MIN_SEGMENTS_TO_FILTER,
    context_radius: int = CONTEXT_RADIUS,
    max_selection_ratio: float = MAX_SELECTION_RATIO,
) -> CandidateSelection:
    """Select likely meeting facts while failing open when filtering is unsafe."""
    if not enabled or len(segments) < minimum_segments:
        return _full_selection(segments, cue_count=_cue_count(segments))

    cue_indexes = {
        index
        for index, segment in enumerate(segments)
        if CANDIDATE_CUES.search(segment.text)
    }
    if not cue_indexes:
        return _full_selection(segments, cue_count=0)

    selected_indexes = {0, len(segments) - 1}
    for cue_index in cue_indexes:
        start = max(0, cue_index - context_radius)
        stop = min(len(segments), cue_index + context_radius + 1)
        selected_indexes.update(range(start, stop))

    selection_ratio = len(selected_indexes) / len(segments)
    if selection_ratio >= max_selection_ratio:
        return _full_selection(segments, cue_count=len(cue_indexes))

    selected = [segment for index, segment in enumerate(segments) if index in selected_indexes]
    return CandidateSelection(
        segments=selected,
        original_segment_count=len(segments),
        selected_segment_count=len(selected),
        cue_segment_count=len(cue_indexes),
        filtered=True,
    )


def _cue_count(segments: list[TranscriptSegment]) -> int:
    return sum(bool(CANDIDATE_CUES.search(segment.text)) for segment in segments)


def _full_selection(
    segments: list[TranscriptSegment],
    *,
    cue_count: int,
) -> CandidateSelection:
    return CandidateSelection(
        segments=list(segments),
        original_segment_count=len(segments),
        selected_segment_count=len(segments),
        cue_segment_count=cue_count,
        filtered=False,
    )
