import json

import config

# In-memory store keyed by content_id (hydrated from audit log on demand)
_submissions: dict[str, dict] = {}


def utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def append_audit_entry(entry: dict) -> None:
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    with config.AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def _hydrate_submissions_from_log() -> None:
    if not config.AUDIT_LOG_PATH.exists():
        return

    ordered: list[dict] = []
    with config.AUDIT_LOG_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                ordered.append(json.loads(line))

    for entry in ordered:
        content_id = entry.get("content_id")
        if not content_id:
            continue

        if entry.get("event_type") == "appeal":
            if content_id in _submissions:
                _submissions[content_id]["status"] = "under_review"
                _submissions[content_id]["appeal_reasoning"] = entry.get("appeal_reasoning")
                _submissions[content_id]["appeal_timestamp"] = entry.get("appeal_timestamp")
                _submissions[content_id]["appeal_filed"] = True
        elif entry.get("event_type", "classification") == "classification":
            _submissions[content_id] = entry.copy()


def get_log(limit: int | None = None) -> list[dict]:
    if not config.AUDIT_LOG_PATH.exists():
        return []

    entries: list[dict] = []
    with config.AUDIT_LOG_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    # Enrich classification entries with current appeal status from store
    _hydrate_submissions_from_log()
    enriched: list[dict] = []
    for entry in entries:
        if entry.get("event_type", "classification") == "classification":
            current = _submissions.get(entry["content_id"], entry)
            merged = {**entry, **{
                "status": current.get("status", entry.get("status", "classified")),
                "appeal_filed": current.get("appeal_filed", False),
            }}
            if current.get("appeal_reasoning"):
                merged["appeal_reasoning"] = current["appeal_reasoning"]
            enriched.append(merged)
        else:
            enriched.append(entry)

    enriched.reverse()
    if limit is not None:
        return enriched[:limit]
    return enriched


def save_submission(content_id: str, record: dict) -> None:
    record.setdefault("event_type", "classification")
    record.setdefault("appeal_filed", False)
    _submissions[content_id] = record


def get_submission(content_id: str) -> dict | None:
    if content_id not in _submissions:
        _hydrate_submissions_from_log()
    return _submissions.get(content_id)


def update_submission(content_id: str, updates: dict) -> dict | None:
    record = get_submission(content_id)
    if record is None:
        return None
    record.update(updates)
    _submissions[content_id] = record
    return record
