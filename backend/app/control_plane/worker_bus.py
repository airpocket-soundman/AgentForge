"""MCP-like worker message bus (NOT real MCP).

The schema-validated transport for inter-worker "instruction" (request) and
"report" (workers.html §7). Validation is the gate: a request that doesn't match
the schema is rejected and never acted on. Messages are logged to `worker_messages`
for traceability and correlation (task_id + in_reply_to).

This is the protocol/contract layer. The build pipeline still calls workers
directly today; routing every step through this bus (with wake-up of stopped
recipients) is the remaining, larger Phase 3 work — the contract here is the
foundation for it.
"""
from __future__ import annotations

import uuid

from pydantic import ValidationError

from app.firestore import get_db
from app.models.worker_protocol import WorkerReport, WorkerRequest

_COLLECTION = "worker_messages"


def new_message_id() -> str:
    return f"msg_{uuid.uuid4().hex[:12]}"


def validate_request(data: dict) -> tuple[WorkerRequest | None, str | None]:
    """Validate an incoming instruction. Returns (request, None) or (None, reason).
    A None request means the caller should reply with a 'rejected' report."""
    try:
        return WorkerRequest.model_validate(data), None
    except ValidationError as e:
        return None, f"schema validation failed: {e.errors()[:3]}"


def validate_report(data: dict) -> tuple[WorkerReport | None, str | None]:
    try:
        return WorkerReport.model_validate(data), None
    except ValidationError as e:
        return None, f"schema validation failed: {e.errors()[:3]}"


def log_message(kind: str, message: dict) -> None:
    """Persist a request/report for traceability (kind = 'request' | 'report')."""
    mid = message.get("message_id") or message.get("in_reply_to") or new_message_id()
    get_db().collection(_COLLECTION).document(f"{kind}:{mid}:{new_message_id()}").set(
        {"kind": kind, **message}
    )


def thread(task_id: str) -> list[dict]:
    """All logged messages for a task_id (for correlation/debugging)."""
    out = [d.to_dict() or {} for d in get_db().collection(_COLLECTION).stream()]
    out = [m for m in out if m.get("task_id") == task_id]
    out.sort(key=lambda m: m.get("message_id") or m.get("in_reply_to") or "")
    return out
