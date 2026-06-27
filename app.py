import uuid

from flask import Flask, jsonify, request

import config
from audit import append_audit_entry, get_log, save_submission, utc_now_iso
from exceptions import ScoringError
from signals.llm_classifier import (
    attribution_from_signal1,
    classify_with_llm,
    signal1_log_tag,
)

app = Flask(__name__)

# Milestone 3 placeholders until Signal 2 + fusion land in Milestone 4
PLACEHOLDER_LABEL = "uncertain"


@app.post("/submit")
def submit():
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    creator_id = (body.get("creator_id") or "").strip()

    if not creator_id:
        return jsonify({"error": "creator_id is required."}), 422
    if len(text) < config.MIN_TEXT_LENGTH:
        return jsonify({"error": f"text must be at least {config.MIN_TEXT_LENGTH} characters."}), 422

    try:
        llm_score = classify_with_llm(text)
    except ScoringError as exc:
        return jsonify({"error": str(exc)}), 422

    content_id = str(uuid.uuid4())
    attribution = attribution_from_signal1(llm_score)
    confidence = llm_score  # placeholder — Milestone 4 replaces with fused final_score

    record = {
        "content_id": content_id,
        "creator_id": creator_id,
        "text": text,
        "timestamp": utc_now_iso(),
        "attribution": signal1_log_tag(llm_score),
        "confidence": confidence,
        "llm_score": llm_score,
        "label": PLACEHOLDER_LABEL,
        "status": "classified",
    }

    append_audit_entry(record)
    save_submission(content_id, record)

    return jsonify(
        {
            "content_id": content_id,
            "attribution": attribution,
            "confidence": confidence,
            "label": PLACEHOLDER_LABEL,
        }
    )


@app.get("/log")
def log_entries():
    return jsonify({"entries": get_log()})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
