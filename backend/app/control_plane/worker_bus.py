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
from datetime import datetime, timezone
from typing import Callable

from pydantic import ValidationError

from app.control_plane import worker_status
from app.firestore import get_db
from app.harness import service as harness
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_message(kind: str, message: dict) -> None:
    """Persist a request/report/event for traceability."""
    mid = message.get("message_id") or message.get("in_reply_to") or new_message_id()
    get_db().collection(_COLLECTION).document(f"{kind}:{mid}:{new_message_id()}").set(
        {"kind": kind, "ts": _now_iso(), **message}
    )


def log_event(task_id: str, text: str, project_id: str | None = None, event: str = "progress") -> None:
    """One pipeline event (progress line / retry / outcome) on the run's thread —
    the per-run EVENT LOG a developer can read end to end."""
    try:
        log_message("event", {"task_id": task_id, "project_id": project_id,
                              "event": event, "text": text[:300]})
        harness.record_event(
            task_id,
            project_id=project_id,
            stage=event,
            worker=None,
            status="info",
            message=text,
            user_visible=True,
        )
    except Exception:  # noqa: BLE001 — logging must never break the pipeline
        pass


def thread(task_id: str) -> list[dict]:
    """All logged messages/events for a task_id, in chronological order."""
    out = [d.to_dict() or {} for d in get_db().collection(_COLLECTION).stream()]
    out = [m for m in out if m.get("task_id") == task_id]
    out.sort(key=lambda m: (m.get("ts") or "", m.get("message_id") or ""))
    return out


# A run's kind is its task_id prefix — reliable, unlike per-message intent (the
# inner Tester/Reviewer sub-requests share the run's task_id with intent
# verify/review and would otherwise mislabel the whole run).
_RUN_KIND = {"plan": "設計案", "build": "新規生成", "edit": "改変", "rev": "プレビュー修正", "investigate": "調査"}


def list_runs(project_id: str | None = None, limit: int = 20) -> list[dict]:
    """Recent pipeline runs (grouped by task_id): kind, goal, span, outcome.

    The kind comes from the task_id prefix and the outcome from the TOP-LEVEL
    report (the one addressed back to the Receptor) — inner verify/review
    sub-messages share the task_id but must not define the run's kind/result."""
    runs: dict[str, dict] = {}
    for d in get_db().collection(_COLLECTION).stream():
        m = d.to_dict() or {}
        tid = m.get("task_id")
        if not tid:
            continue
        if project_id and m.get("project_id") not in (None, project_id):
            continue
        r = runs.setdefault(tid, {"task_id": tid, "first_ts": None, "last_ts": None,
                                  "goal": None, "events": 0, "last_status": None,
                                  "intent": _RUN_KIND.get(tid.split("_")[0], tid.split("_")[0]),
                                  "running": False, "project_id": m.get("project_id")})
        ts = m.get("ts") or ""
        if ts and (r["first_ts"] is None or ts < r["first_ts"]):
            r["first_ts"] = ts
        if ts and (r["last_ts"] is None or ts > r["last_ts"]):
            r["last_ts"] = ts
        r["events"] += 1
        kind = m.get("kind")
        if kind == "request":
            # The top-level goal is on the Receptor→Orchestrator request; keep the
            # first goal we see only as a fallback.
            g = (m.get("payload") or {}).get("goal") or (m.get("payload") or {}).get("instruction")
            if m.get("from") == "Receptor" and g:
                r["goal"] = g
            elif g and not r["goal"]:
                r["goal"] = g
        elif kind == "report" and m.get("status"):
            # Outcome = the report addressed back to the Receptor (top-level);
            # fall back to the latest sub-report only if no top-level one exists.
            if m.get("to") == "Receptor":
                r["last_status"] = m["status"]
            elif r["last_status"] is None:
                r["last_status"] = m["status"]
    # Mark runs still in flight (a Receptor→Orchestrator request with no top-level
    # report yet) using the live build record, so the monitor shows 実行中.
    for r in runs.values():
        pid = r.get("project_id")
        if r["last_status"] is None and pid:
            try:
                snap = get_db().collection("conversations").document(f"conv_{pid}").get()
                if (snap.to_dict() or {}).get("build", {}).get("status") == "designing":
                    r["running"] = True
            except Exception:  # noqa: BLE001
                pass
    out = sorted(runs.values(), key=lambda r: r.get("last_ts") or "", reverse=True)
    return out[:limit]


def list_structured_runs(project_id: str, limit: int = 20) -> list[dict]:
    """Harness-first run list with worker_bus fallback for older records."""
    try:
        structured = harness.list_runs(project_id, limit)
        if structured:
            return structured
    except Exception:  # noqa: BLE001
        pass
    return list_runs(project_id, limit)


def gate_report_fields(result: dict) -> dict:
    """Pure: map a Tester/Reviewer verdict dict to MCP-like report body fields."""
    verdict = result.get("verdict")
    status = "ok" if verdict in ("pass", "ok") else "needs_revision"
    findings = list(result.get("errors") or []) + list(result.get("findings") or [])
    return {"status": status, "result": result, "findings": findings}


def normalize_report_body(body: dict) -> dict:
    """Accept legacy/simple worker replies and return valid report body fields."""
    if "status" in body:
        return body
    if "report" in body:
        return {"status": "ok", "result": {"report": body.get("report")}}
    return body


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
    req = {"task_id": task_id, "message_id": mid, "from": sender, "to": to, "intent": intent,
           "payload": payload, "project_id": project_id}
    valid, err = validate_request(req)
    if valid is None:
        report = {"task_id": task_id, "in_reply_to": mid, "from": to, "to": sender,
                  "status": "rejected", "error": err, "project_id": project_id}
        log_message("report", report)
        return report

    log_message("request", req)
    try:
        goal = payload.get("goal") or payload.get("instruction")
        feature = payload.get("feature") or (payload.get("design_plan") or {}).get("feature")
        harness.ensure_run(
            task_id,
            project_id=project_id,
            request_text=goal,
            request_type=intent,
            feature=feature,
            current_stage=f"{intent}_requested",
            worker=sender,
            model=model,
        )
        harness.record_event(
            task_id,
            project_id=project_id,
            stage=f"{intent}_requested",
            worker=sender,
            status="requested",
            message=f"{sender} → {to}: {intent}",
            metadata={"payload": payload},
        )
    except Exception:  # noqa: BLE001
        pass
    if project_id:
        worker_status.start_worker(to, project_id, model=model, task_id=task_id)  # wake the recipient
    try:
        body = normalize_report_body(handler(payload))
        report = {"task_id": task_id, "in_reply_to": mid, "from": to, "to": sender,
                  "project_id": project_id, **body}
    except Exception as exc:  # noqa: BLE001
        report = {"task_id": task_id, "in_reply_to": mid, "from": to, "to": sender,
                  "status": "failed", "error": str(exc)[:300], "project_id": project_id}
    finally:
        if project_id:
            worker_status.record_status(to, project_id, worker_status.STOPPED)
    log_message("report", report)
    try:
        status = str(report.get("status") or "")
        harness.record_event(
            task_id,
            project_id=project_id,
            stage=f"{intent}_reported",
            worker=to,
            status=status or "reported",
            message=(report.get("error") or status or "reported")[:1000],
            metadata={
                "result": report.get("result"),
                "findings": report.get("findings"),
            },
        )
        if to == "Orchestrator" and sender == "Receptor" and status in {"ok", "needs_revision", "failed", "rejected"}:
            if status == "ok":
                harness.complete_run(task_id, "Orchestrator の処理が完了しました。", status="ok")
            elif status == "failed":
                harness.fail_run(task_id, str(report.get("error") or "failed"), retryable=True)
            else:
                harness.complete_run(task_id, str(status), status=status)
    except Exception:  # noqa: BLE001
        pass
    return report
