import math
import re
import statistics

PUNCTUATION_MARKS = set(".,!?;:'\"—…")

LLM_WEIGHT = 0.60
STYLO_WEIGHT = 0.40
DIVERGENCE_THRESHOLD = 0.40
MIN_SENTENCES = 3


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"[.!?]+", text)
    return [part.strip() for part in parts if part.strip()]


def _sentence_word_counts(text: str) -> list[int]:
    sentences = _split_sentences(text)
    counts: list[int] = []
    for sentence in sentences:
        words = re.findall(r"\b[\w']+\b", sentence)
        if words:
            counts.append(len(words))
    return counts


def _burst_ai_score(text: str) -> float:
    counts = _sentence_word_counts(text)
    if len(counts) < 2:
        return 0.50

    mean_len = statistics.mean(counts)
    if mean_len == 0:
        return 0.50

    burstiness = statistics.pstdev(counts) / mean_len
    return _clamp(1.0 - (burstiness / 0.85))


def _punct_ai_score(text: str) -> float:
    counts: dict[str, int] = {}
    total = 0
    for char in text:
        if char in PUNCTUATION_MARKS:
            counts[char] = counts.get(char, 0) + 1
            total += 1

    if total == 0 or len(counts) <= 1:
        return 1.0

    entropy = 0.0
    for count in counts.values():
        probability = count / total
        entropy -= probability * math.log2(probability)

    max_entropy = math.log2(len(counts))
    entropy_norm = entropy / max_entropy if max_entropy > 0 else 0.0
    return _clamp(1.0 - entropy_norm)


def score_stylometrics(text: str) -> float:
    """
    Returns stylo_score in [0.0, 1.0] where higher = more likely AI-generated.
    Combines burstiness and punctuation entropy per planning.md.
    """
    sentences = _split_sentences(text)
    if len(sentences) < MIN_SENTENCES:
        return 0.50

    burst_ai = _burst_ai_score(text)
    punct_ai = _punct_ai_score(text)
    stylo_score = (0.55 * burst_ai) + (0.45 * punct_ai)
    return round(_clamp(stylo_score), 3)
