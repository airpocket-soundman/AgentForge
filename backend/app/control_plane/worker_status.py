"""Worker status registry — the lifecycle/status surface for the status monitor.

Each worker (Receptor / Orchestrator / Reviewer / Tester / Specialist Worker)
records its own status when it changes (spec §5). A status carries the in-use
model and a last-updated time so the monitor can show it and a crashed worker
(stuck "active" with no updates) can be reaped.

Status values (spec): active(活動中) / idle(待機中) / stopped(停止中).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.firestore import get_db

_COLLECTION = "workers"
ACTIVE, IDLE, STOPPED = "active", "idle", "stopped"

# An "active" worker whose status hasn't updated within this window is treated as
# crashed/stale and reported as stopped (the reaper). Generous: high-capability
# PRO generation legitimately takes minutes (workers.html §3(b)/§5).
_STALE_SEC = 900


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _age_sec(iso: str | None) -> float:
    if not iso:
        return 0.0
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return 0.0
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return max(0.0, (_now() - then).total_seconds())


def worker_id(worker_type: str, project_id: str) -> str:
    return f"{worker_type}:{project_id}"


def record_status(
    worker_type: str,
    project_id: str,
    status: str,
    model: str | None = None,
    task_id: str | None = None,
    detail: str | None = None,
) -> None:
    """A worker records its own status change (incl. the model in use)."""
    doc = {
        "worker_type": worker_type,
        "project_id": project_id,
        "status": status,
        "task_id": task_id,
        "detail": detail,
        "updated_at": _now_iso(),
    }
    if model is not None:
        doc["model"] = model
    get_db().collection(_COLLECTION).document(worker_id(worker_type, project_id)).set(doc, merge=True)


def start_worker(worker_type: str, project_id: str, model: str | None = None, task_id: str | None = None) -> dict:
    """Start/wake a worker (other workers call this; spec §5). Sets it active."""
    record_status(worker_type, project_id, ACTIVE, model=model, task_id=task_id)
    return {"worker_type": worker_type, "project_id": project_id, "status": ACTIVE}


def stop_worker(worker_type: str, project_id: str) -> dict:
    """Stop a worker (sets it stopped)."""
    record_status(worker_type, project_id, STOPPED)
    return {"worker_type": worker_type, "project_id": project_id, "status": STOPPED}


def _effective_status(rec: dict) -> str:
    """Reap: an 'active' worker with no recent update is really stopped (crashed)."""
    if rec.get("status") == ACTIVE and _age_sec(rec.get("updated_at")) > _STALE_SEC:
        return STOPPED
    return rec.get("status") or STOPPED


def list_workers(project_id: str | None = None) -> list[dict]:
    """All known workers (status + model + freshness), for the status monitor."""
    out: list[dict] = []
    for d in get_db().collection(_COLLECTION).stream():
        rec = d.to_dict() or {}
        if project_id and rec.get("project_id") != project_id:
            continue
        eff = _effective_status(rec)
        out.append({
            "worker_type": rec.get("worker_type"),
            "project_id": rec.get("project_id"),
            "status": eff,
            "stale": eff != rec.get("status"),  # True if reaped from active
            "model": rec.get("model"),
            "task_id": rec.get("task_id"),
            "since_update_sec": int(_age_sec(rec.get("updated_at"))),
            "updated_at": rec.get("updated_at"),
        })
    out.sort(key=lambda w: (w.get("project_id") or "", w.get("worker_type") or ""))
    return out
