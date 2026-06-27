import uuid

from flask import Flask, jsonify, request

import config
from audit import append_audit_entry, get_log, save_submission, utc_now_iso
from exceptions import ScoringError
from scoring import (
    build_attribution,
    compute_confidence,
    map_to_external_label,
    map_to_internal_label,
)
from signals.llm_classifier import classify_with_llm
from signals.stylometrics import score_stylometrics

app = Flask(__name__)


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

    stylo_score = score_stylometrics(text)
    confidence_result = compute_confidence(llm_score, stylo_score)
    final_score = confidence_result["final_score"]
    internal_label = map_to_internal_label(final_score)
    external_label = map_to_external_label(internal_label)
    attribution = build_attribution(external_label, final_score)

    content_id = str(uuid.uuid4())
    record = {
        "content_id": content_id,
        "creator_id": creator_id,
        "text": text,
        "timestamp": utc_now_iso(),
        "llm_score": llm_score,
        "stylo_score": stylo_score,
        "confidence": final_score,
        "divergence": confidence_result["divergence"],
        "forced_uncertain": confidence_result["forced_uncertain"],
        "internal_label": internal_label,
        "label": external_label,
        "attribution": attribution,
        "status": "classified",
    }

    append_audit_entry(record)
    save_submission(content_id, record)

    return jsonify(
        {
            "content_id": content_id,
            "attribution": attribution,
            "confidence": final_score,
            "label": external_label,
        }
    )


@app.get("/log")
def log_entries():
    return jsonify({"entries": get_log()})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
