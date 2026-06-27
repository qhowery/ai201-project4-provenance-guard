LLM_WEIGHT = 0.60
STYLO_WEIGHT = 0.40
DIVERGENCE_THRESHOLD = 0.40


def compute_confidence(llm_score: float, stylo_score: float) -> dict:
    """
    Combine both signals into a single confidence score per planning.md.
    """
    divergence = abs(llm_score - stylo_score)

    if divergence > DIVERGENCE_THRESHOLD:
        return {
            "final_score": 0.50,
            "divergence": round(divergence, 3),
            "forced_uncertain": True,
        }

    final_score = (LLM_WEIGHT * llm_score) + (STYLO_WEIGHT * stylo_score)
    return {
        "final_score": round(final_score, 3),
        "divergence": round(divergence, 3),
        "forced_uncertain": False,
    }


def map_to_internal_label(final_score: float) -> str:
    if final_score >= 0.82:
        return "clearly_ai"
    if final_score >= 0.65:
        return "borderline_ai"
    if final_score >= 0.35:
        return "uncertain_internal"
    if final_score >= 0.18:
        return "borderline_human"
    return "clearly_human"


def map_to_external_label(internal_label: str) -> str:
    mapping = {
        "clearly_ai": "high-confidence AI",
        "borderline_ai": "uncertain",
        "uncertain_internal": "uncertain",
        "borderline_human": "uncertain",
        "clearly_human": "high-confidence human",
    }
    return mapping[internal_label]


def build_attribution(external_label: str, final_score: float) -> str:
    pct = round(final_score * 100)
    if external_label == "high-confidence AI":
        return f"This content was assessed as AI-generated ({pct}% confidence)."
    if external_label == "high-confidence human":
        return f"This content was assessed as human-written ({pct}% confidence)."
    return (
        f"This content could not be confidently attributed ({pct}% confidence). "
        "Attribution is uncertain."
    )
