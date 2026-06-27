#!/usr/bin/env python3
"""Milestone 5 tests — run: python test_milestone5.py"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import config
import audit

tmpdir = tempfile.mkdtemp()
config.LOG_DIR = Path(tmpdir)
config.AUDIT_LOG_PATH = config.LOG_DIR / "audit.jsonl"
audit._submissions.clear()

from app import app  # noqa: E402
from scoring import build_attribution, map_to_external_label, map_to_internal_label  # noqa: E402

client = app.test_client()

AI_TEXT = (
    "Artificial intelligence represents a transformative paradigm shift in modern society. "
    "It is important to note that while the benefits of AI are numerous, it is equally "
    "essential to consider the ethical implications. Furthermore, stakeholders across "
    "various sectors must collaborate to ensure responsible deployment."
)
HUMAN_TEXT = (
    "ok so i finally tried that new ramen place downtown and honestly? "
    "underwhelming. the broth was fine but they put WAY too much sodium in it and "
    "i was thirsty for like three hours after. my friend got the spicy version and "
    "said it was better. probably won't go back unless someone drags me there"
)
UNCERTAIN_TEXT = (
    "I've been thinking a lot about remote work lately. There are genuine tradeoffs — "
    "flexibility and no commute on one side, isolation and blurred work-life boundaries "
    "on the other. Studies show productivity varies widely by individual and role type."
)


def test_label_variants() -> None:
    print("=== Three label variants ===")
    cases = [
        (0.88, "high-confidence AI"),
        (0.12, "high-confidence human"),
        (0.55, "uncertain"),
    ]
    for score, expected in cases:
        internal = map_to_internal_label(score)
        external = map_to_external_label(internal)
        attribution = build_attribution(external, score)
        assert external == expected, f"score {score}: got {external}"
        print(f"  {expected}: {attribution}")
    print("  OK\n")


def test_submit_appeal_log() -> None:
    print("=== Submit + appeal + log ===")

    def mock_llm(text: str) -> float:
        if "paradigm" in text:
            return 0.90
        if "ramen" in text:
            return 0.15
        return 0.48

    with patch("app.classify_with_llm", side_effect=mock_llm):
        ai = client.post("/submit", json={"text": AI_TEXT, "creator_id": "writer-1"})
        human = client.post("/submit", json={"text": HUMAN_TEXT, "creator_id": "writer-2"})
        mid = client.post("/submit", json={"text": UNCERTAIN_TEXT, "creator_id": "writer-3"})

    ai_body = ai.get_json()
    print(f"  AI label: {ai_body['label']} (confidence={ai_body['confidence']})")
    print(f"  Human label: {human.get_json()['label']}")
    print(f"  Borderline label: {mid.get_json()['label']}")

    labels = {ai_body["label"], human.get_json()["label"], mid.get_json()["label"]}
    assert "high-confidence human" in labels
    assert len(labels) >= 2, "labels should vary across inputs"

    appeal = client.post(
        "/appeal",
        json={
            "content_id": ai_body["content_id"],
            "creator_id": "writer-1",
            "creator_reasoning": (
                "I wrote this myself from personal experience. I am a non-native English "
                "speaker and my writing style may appear more formal than typical."
            ),
        },
    )
    assert appeal.status_code == 200, appeal.get_json()
    print(f"  Appeal: {appeal.get_json()['message']}")

    log = client.get("/log").get_json()["entries"]
    appealed = next(e for e in log if e.get("content_id") == ai_body["content_id"] and e.get("event_type") != "appeal")
    assert appealed["status"] == "under_review"
    assert appealed.get("appeal_reasoning")
    print(f"  Log status: {appealed['status']}, appeal_reasoning present: True")
    print("  OK\n")


def test_rate_limit() -> None:
    print("=== Rate limiting (12 rapid submits) ===")
    audit._submissions.clear()
    config.AUDIT_LOG_PATH.unlink(missing_ok=True)

    # Clear in-memory limiter counters from earlier tests in this process
    from app import limiter

    if hasattr(limiter.storage, "storage"):
        limiter.storage.storage.clear()

    payload = {
        "text": "This is a test submission for rate limit testing purposes only.",
        "creator_id": "ratelimit-test",
    }

    codes = []
    with patch("app.classify_with_llm", return_value=0.5):
        for _ in range(12):
            resp = client.post("/submit", json=payload)
            codes.append(resp.status_code)

    print("  Status codes:", " ".join(str(c) for c in codes))
    assert codes[:10] == [200] * 10
    assert all(code == 429 for code in codes[10:])
    print("  OK — first 10 returned 200, later requests returned 429\n")


if __name__ == "__main__":
    test_label_variants()
    test_submit_appeal_log()
    test_rate_limit()
    print("All Milestone 5 tests passed.")
