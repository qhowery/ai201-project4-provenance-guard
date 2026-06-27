import json
import re

from groq import Groq

import config
from exceptions import ScoringError

PROMPT_TEMPLATE = """You are an authorship analyst. Rate how likely this text was AI-generated (not human-written).
Reply with ONLY valid JSON: {{"ai_probability": <float 0.0-1.0>}}

Consider: word choice originality, sentence rhythm variation, filler phrases, tone shifts.

TEXT:
{text}"""


def _parse_ai_probability(raw: str) -> float:
    raw = raw.strip()
    try:
        data = json.loads(raw)
        score = float(data["ai_probability"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        match = re.search(r"ai_probability[\"']?\s*:\s*([0-9]*\.?[0-9]+)", raw)
        if not match:
            raise ScoringError(f"Could not parse LLM response as JSON: {raw[:200]}")
        score = float(match.group(1))

    return max(0.0, min(1.0, score))


def classify_with_llm(text: str) -> float:
    """
    Returns llm_score in [0.0, 1.0] where higher = more likely AI-generated.
    """
    if not config.GROQ_API_KEY:
        raise ScoringError("GROQ_API_KEY is not set. Copy .env.example to .env and add your key.")

    client = Groq(api_key=config.GROQ_API_KEY)
    prompt = PROMPT_TEMPLATE.format(text=text)

    try:
        response = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        content = response.choices[0].message.content or ""
    except Exception as exc:
        raise ScoringError(f"Groq API call failed: {exc}") from exc

    return round(_parse_ai_probability(content), 3)


def attribution_from_signal1(llm_score: float) -> str:
    """Milestone 3 interim attribution based on Signal 1 only."""
    pct = round(llm_score * 100)
    if llm_score >= 0.65:
        return f"Signal 1 (LLM): likely AI-generated ({pct}% AI probability)."
    if llm_score <= 0.35:
        return f"Signal 1 (LLM): likely human-written ({pct}% AI probability)."
    return f"Signal 1 (LLM): mixed authorship indicators ({pct}% AI probability)."


def signal1_log_tag(llm_score: float) -> str:
    """Short tag for audit log attribution field in Milestone 3."""
    if llm_score >= 0.65:
        return "likely_ai"
    if llm_score <= 0.35:
        return "likely_human"
    return "uncertain_signal1"
