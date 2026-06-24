"""Structured Agent Harness run store.

The user-facing chat should show short progress, not raw traces. This module
keeps the raw-but-structured pipeline history for status/admin views and for
generating concise summaries before publish.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.firestore import get_db

_COLLECTION = "pipeline_runs"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_run(
    run_id: str | None,
    *,
    project_id: str | None,
    request_text: str | None = None,
    request_type: str | None = None,
    feature: str | None = None,
    current_stage: str | None = None,
    worker: str | None = None,
    model: str | None = None,
) -> str:
    """Create a run if missing, otherwise merge updated metadata."""
    rid = run_id or f"run_{uuid.uuid4().hex[:12]}"
    ref = get_db().collection(_COLLECTION).document(rid)
    snap = ref.get()
    now = _now_iso()
    payload: dict[str, Any] = {
        "run_id": rid,
        "updated_at": now,
    }
    if not snap.exists:
        payload.update(
            {
                "project_id": project_id,
                "feature": feature,
                "request_text": request_text,
                "request_type": request_type,
                "status": "running",
                "current_stage": current_stage or "received",
                "started_at": now,
                "completed_at": None,
                "workers": {},
                "event_count": 0,
                "last_event": None,
                "decision_summary": "",
                "user_visible_summary": "",
            }
        )
    else:
        if project_id:
            payload["project_id"] = project_id
        if feature:
            payload["feature"] = feature
        if request_text:
            payload["request_text"] = request_text
        if request_type:
            payload["request_type"] = request_type
        if current_stage:
            payload["current_stage"] = current_stage
    if worker:
        payload[f"workers.{worker}.last_seen_at"] = now
        if model:
            payload[f"workers.{worker}.model"] = model
    ref.set(payload, merge=True)
    return rid


def record_event(
    run_id: str,
    *,
    project_id: str | None = None,
    stage: str,
    worker: str | None,
    status: str = "info",
    message: str = "",
    user_visible: bool = False,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append an event and update the run's current status."""
    ensure_run(run_id, project_id=project_id, current_stage=stage, worker=worker)
    now = _now_iso()
    eid = f"evt_{uuid.uuid4().hex[:12]}"
    event = {
        "event_id": eid,
        "run_id": run_id,
        "project_id": project_id,
        "stage": stage,
        "worker": worker,
        "status": status,
        "message": message[:1200],
        "user_visible": user_visible,
        "metadata": metadata or {},
        "created_at": now,
    }
    db = get_db()
    db.collection(_COLLECTION).document(run_id).collection("events").document(eid).set(event)
    db.collection(_COLLECTION).document(run_id).set(
        {
            "updated_at": now,
            "current_stage": stage,
            "last_event": event,
            "event_count": firestore_increment(1),
        },
        merge=True,
    )


def attach_artifact(run_id: str, kind: str, payload: dict[str, Any]) -> None:
    """Store a bounded artifact such as design plan, gate result, or manifest meta."""
    ensure_run(run_id, project_id=payload.get("project_id"))
    aid = f"art_{uuid.uuid4().hex[:12]}"
    get_db().collection(_COLLECTION).document(run_id).collection("artifacts").document(aid).set(
        {
            "artifact_id": aid,
            "run_id": run_id,
            "kind": kind,
            "payload": _bounded(payload),
            "created_at": _now_iso(),
        }
    )


def complete_run(run_id: str, summary: str = "", *, status: str = "ok") -> None:
    ensure_run(run_id, project_id=None)
    get_db().collection(_COLLECTION).document(run_id).set(
        {
            "status": status,
            "completed_at": _now_iso(),
            "updated_at": _now_iso(),
            "user_visible_summary": summary[:2000],
        },
        merge=True,
    )


def fail_run(run_id: str, reason: str, *, retryable: bool = False) -> None:
    ensure_run(run_id, project_id=None)
    get_db().collection(_COLLECTION).document(run_id).set(
        {
            "status": "failed",
            "completed_at": _now_iso(),
            "updated_at": _now_iso(),
            "failure_reason": reason[:1000],
            "retryable": retryable,
        },
        merge=True,
    )


def list_runs(project_id: str, limit: int = 20) -> list[dict]:
    """Newest-first structured run list."""
    out: list[dict] = []
    for d in get_db().collection(_COLLECTION).stream():
        x = d.to_dict() or {}
        if x.get("project_id") == project_id:
            out.append(x)
    out.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    return out[:limit]


def get_events(run_id: str) -> list[dict]:
    out = [d.to_dict() or {} for d in get_db().collection(_COLLECTION).document(run_id).collection("events").stream()]
    out.sort(key=lambda r: r.get("created_at", ""))
    return out


def _bounded(value: Any, depth: int = 0) -> Any:
    if depth > 6:
        return "..."
    if isinstance(value, str):
        return value[:20000]
    if isinstance(value, dict):
        return {str(k)[:80]: _bounded(v, depth + 1) for k, v in list(value.items())[:80]}
    if isinstance(value, list):
        return [_bounded(v, depth + 1) for v in value[:80]]
    return value


def firestore_increment(n: int):
    from google.cloud import firestore

    return firestore.Increment(n)
