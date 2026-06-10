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

from typing import Callable

from pydantic import ValidationError

from app.control_plane import worker_status
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


def gate_report_fields(result: dict) -> dict:
    """Pure: map a Tester/Reviewer verdict dict to MCP-like report body fields."""
    verdict = result.get("verdict")
    status = "ok" if verdict in ("pass", "ok") else "needs_revision"
    findings = list(result.get("errors") or []) + list(result.get("findings") or [])
    return {"status": status, "result": result, "findings": findings}


def dispatch(
    *,
    task_id: str,
    sender: str,
    to: str,
    intent: str,
    payload: dict,
    handler: Callable[[dict], dict],
    project_id: str | None = None,
    model: str | None = None,
) -> dict:
    """Send an MCP-like request to `to`, run its handler, return the report dict.

    Logs both messages (request/report), validates the request (invalid → rejected
    without running the handler), wakes the recipient (status active) before and
    stops it after — the in-process realization of the wait + wake-up rule. The
    handler returns report body fields ({status, result, findings, error}); a raised
    handler maps to status=failed."""
    mid = new_message_id()
    req = {"task_id": task_id, "message_id": mid, "from": sender, "to": to, "intent": intent, "payload": payload}
    valid, err = validate_request(req)
    if valid is None:
        report = {"task_id": task_id, "in_reply_to": mid, "from": to, "to": sender, "status": "rejected", "error": err}
        log_message("report", report)
        return report

    log_message("request", req)
    if project_id:
        worker_status.start_worker(to, project_id, model=model, task_id=task_id)  # wake the recipient
    try:
        body = handler(payload)
        report = {"task_id": task_id, "in_reply_to": mid, "from": to, "to": sender, **body}
    except Exception as exc:  # noqa: BLE001
        report = {"task_id": task_id, "in_reply_to": mid, "from": to, "to": sender, "status": "failed", "error": str(exc)[:300]}
    finally:
        if project_id:
            worker_status.record_status(to, project_id, worker_status.STOPPED)
    log_message("report", report)
    return report
