import json
from datetime import datetime, timezone

import config

# In-memory store for submissions (used by appeal flow in Milestone 5)
_submissions: dict[str, dict] = {}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def append_audit_entry(entry: dict) -> None:
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    with config.AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def get_log(limit: int | None = None) -> list[dict]:
    if not config.AUDIT_LOG_PATH.exists():
        return []

    entries: list[dict] = []
    with config.AUDIT_LOG_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    entries.reverse()
    if limit is not None:
        return entries[:limit]
    return entries


def save_submission(content_id: str, record: dict) -> None:
    _submissions[content_id] = record


def get_submission(content_id: str) -> dict | None:
    return _submissions.get(content_id)
