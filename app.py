import uuid

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import config
from audit import append_audit_entry, get_log, get_submission, save_submission, update_submission, utc_now_iso
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

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

MIN_APPEAL_REASONING = 20


@app.post("/submit")
@limiter.limit(config.SUBMIT_RATE_LIMIT)
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
    internal_label = map_to_internal_label(
        final_score,
        llm_score=llm_score,
        stylo_score=stylo_score,
        forced_uncertain=confidence_result["forced_uncertain"],
    )
    external_label = map_to_external_label(internal_label)
    attribution = build_attribution(external_label, final_score)

    content_id = str(uuid.uuid4())
    record = {
        "event_type": "classification",
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
        "appeal_filed": False,
    }

    append_audit_entry(record)
    save_submission(content_id, record)

    return jsonify(
        {
            "content_id": content_id,
            "attribution": attribution,
            "confidence": final_score,
            "label": external_label,
            "llm_score": llm_score,
            "stylo_score": stylo_score,
        }
    )


@app.post("/appeal")
def appeal():
    body = request.get_json(silent=True) or {}
    content_id = (body.get("content_id") or "").strip()
    creator_id = (body.get("creator_id") or "").strip()
    creator_reasoning = (body.get("creator_reasoning") or "").strip()

    if not content_id:
        return jsonify({"error": "content_id is required."}), 422
    if not creator_id:
        return jsonify({"error": "creator_id is required."}), 422
    if len(creator_reasoning) < MIN_APPEAL_REASONING:
        return jsonify(
            {"error": f"creator_reasoning must be at least {MIN_APPEAL_REASONING} characters."}
        ), 422

    original = get_submission(content_id)
    if original is None:
        return jsonify({"error": f"No submission found for content_id '{content_id}'."}), 422
    if original.get("creator_id") != creator_id:
        return jsonify({"error": "creator_id does not match the original submitter."}), 422
    if original.get("status") == "under_review":
        return jsonify({"error": "An appeal is already under review for this submission."}), 422

    appeal_timestamp = utc_now_iso()
    update_submission(
        content_id,
        {
            "status": "under_review",
            "appeal_filed": True,
            "appeal_reasoning": creator_reasoning,
            "appeal_timestamp": appeal_timestamp,
        },
    )

    appeal_entry = {
        "event_type": "appeal",
        "content_id": content_id,
        "creator_id": creator_id,
        "appeal_reasoning": creator_reasoning,
        "appeal_timestamp": appeal_timestamp,
        "original_confidence": original.get("confidence"),
        "original_label": original.get("label"),
        "original_llm_score": original.get("llm_score"),
        "original_stylo_score": original.get("stylo_score"),
        "original_attribution": original.get("attribution"),
        "status": "under_review",
    }
    append_audit_entry(appeal_entry)

    return jsonify(
        {
            "content_id": content_id,
            "status": "under_review",
            "message": "Appeal received and is under review.",
        }
    )


@app.get("/log")
def log_entries():
    return jsonify({"entries": get_log()})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
