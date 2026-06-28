#!/usr/bin/env python3
"""Milestone 4 scoring tests — run: python test_milestone4.py"""

from scoring import (
    build_attribution,
    compute_confidence,
    map_to_external_label,
    map_to_internal_label,
)
from signals.stylometrics import score_stylometrics

TEST_CASES = {
    "clearly_ai": (
        "Artificial intelligence represents a transformative paradigm shift in modern society. "
        "It is important to note that while the benefits of AI are numerous, it is equally "
        "essential to consider the ethical implications. Furthermore, stakeholders across "
        "various sectors must collaborate to ensure responsible deployment."
    ),
    "clearly_human": (
        "ok so i finally tried that new ramen place downtown and honestly? "
        "underwhelming. the broth was fine but they put WAY too much sodium in it and "
        "i was thirsty for like three hours after. my friend got the spicy version and "
        "said it was better. probably won't go back unless someone drags me there"
    ),
    "borderline_formal_human": (
        "The relationship between monetary policy and asset price inflation has been "
        "extensively studied in the literature. Central banks face a fundamental tension "
        "between their mandate for price stability and the unintended consequences of "
        "prolonged low interest rates on equity and real estate valuations."
    ),
    "borderline_edited_ai": (
        "I've been thinking a lot about remote work lately. There are genuine tradeoffs — "
        "flexibility and no commute on one side, isolation and blurred work-life boundaries "
        "on the other. Studies show productivity varies widely by individual and role type."
    ),
}

# Representative LLM scores when API unavailable — stylometrics still runs live.
MOCK_LLM_SCORES = {
    "clearly_ai": 0.92,
    "clearly_human": 0.18,
    "borderline_formal_human": 0.58,
    "borderline_edited_ai": 0.48,
}


def run_stylometrics_only() -> None:
    print("=== Signal 2: Stylometrics (standalone) ===\n")
    for name, text in TEST_CASES.items():
        stylo = score_stylometrics(text)
        print(f"{name:28} stylo_score={stylo:.3f}")


def run_fusion(use_live_llm: bool = False) -> None:
    print("\n=== Combined scoring ===\n")
    print(f"{'case':28} {'llm':>6} {'stylo':>6} {'final':>6} {'div':>6} {'label'}")
    print("-" * 78)

    llm_fn = None
    if use_live_llm:
        from signals.llm_classifier import classify_with_llm

        llm_fn = classify_with_llm

    for name, text in TEST_CASES.items():
        llm_score = llm_fn(text) if llm_fn else MOCK_LLM_SCORES[name]
        stylo_score = score_stylometrics(text)
        result = compute_confidence(llm_score, stylo_score)
        internal = map_to_internal_label(
            result["final_score"],
            llm_score=llm_score,
            stylo_score=stylo_score,
            forced_uncertain=result["forced_uncertain"],
        )
        external = map_to_external_label(internal)
        forced = " *forced*" if result["forced_uncertain"] else ""
        print(
            f"{name:28} {llm_score:6.3f} {stylo_score:6.3f} "
            f"{result['final_score']:6.3f} {result['divergence']:6.3f} "
            f"{external}{forced}"
        )
        print(f"{'':28} → {build_attribution(external, result['final_score'])}")


def test_human_agreement_rule() -> None:
    """Both signals low and aligned → high-confidence human."""
    llm, stylo = 0.23, 0.22
    result = compute_confidence(llm, stylo)
    internal = map_to_internal_label(
        result["final_score"],
        llm_score=llm,
        stylo_score=stylo,
        forced_uncertain=result["forced_uncertain"],
    )
    external = map_to_external_label(internal)
    assert external == "high-confidence human", f"got {external} for fused {result['final_score']}"
    print("  human agreement rule OK\n")


if __name__ == "__main__":
    test_human_agreement_rule()
    run_stylometrics_only()

    try:
        import config

        if config.GROQ_API_KEY:
            print("\n(Groq key found — running live LLM scores)")
            run_fusion(use_live_llm=True)
        else:
            print("\n(No GROQ_API_KEY — using mock LLM scores for fusion demo)")
            run_fusion(use_live_llm=False)
    except Exception as exc:
        print(f"\nFusion test error: {exc}")
        run_fusion(use_live_llm=False)
