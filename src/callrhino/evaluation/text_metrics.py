import re
import unicodedata
from collections.abc import Sequence

_PUNCTUATION_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = _PUNCTUATION_RE.sub(" ", normalized)
    return _WHITESPACE_RE.sub(" ", normalized).strip()


def word_error_rate(reference: str, hypothesis: str) -> float:
    return error_rate(normalize_text(reference).split(), normalize_text(hypothesis).split())


def character_error_rate(reference: str, hypothesis: str) -> float:
    reference_chars = list(normalize_text(reference).replace(" ", ""))
    hypothesis_chars = list(normalize_text(hypothesis).replace(" ", ""))
    return error_rate(reference_chars, hypothesis_chars)


def error_rate(reference: Sequence[str], hypothesis: Sequence[str]) -> float:
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return edit_distance(reference, hypothesis) / len(reference)


def edit_distance(left: Sequence[str], right: Sequence[str]) -> int:
    previous = list(range(len(right) + 1))
    for left_index, left_item in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_item in enumerate(right, start=1):
            substitution = previous[right_index - 1] + (left_item != right_item)
            current.append(
                min(
                    previous[right_index] + 1,
                    current[right_index - 1] + 1,
                    substitution,
                )
            )
        previous = current
    return previous[-1]


def token_f1(reference: str, hypothesis: str) -> float:
    precision, recall = token_precision_recall(reference, hypothesis)
    return (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )


def token_precision_recall(reference: str, hypothesis: str) -> tuple[float, float]:
    reference_tokens = normalize_text(reference).split()
    hypothesis_tokens = normalize_text(hypothesis).split()
    if not reference_tokens or not hypothesis_tokens:
        exact = float(reference_tokens == hypothesis_tokens)
        return exact, exact

    remaining = list(hypothesis_tokens)
    overlap = 0
    for token in reference_tokens:
        if token in remaining:
            overlap += 1
            remaining.remove(token)
    precision = overlap / len(hypothesis_tokens)
    recall = overlap / len(reference_tokens)
    return precision, recall


def phrase_recall(phrases: list[str], hypothesis: str) -> float:
    if not phrases:
        return 1.0
    normalized_hypothesis = normalize_text(hypothesis)
    found = sum(normalize_text(phrase) in normalized_hypothesis for phrase in phrases)
    return found / len(phrases)
