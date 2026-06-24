"""Control Plane HTTP surface — approval gate and feature lifecycle."""
from fastapi import APIRouter, Depends, HTTPException

from app.auth import CurrentUser, current_user, require_project_access
from app.config import get_settings
from app.control_plane import approvals, guard, monitor, registry, worker_bus, worker_status
from app.models.tasks import WorkerToggleIn

router = APIRouter(prefix="/api/control-plane", tags=["control-plane"])


@router.get("/health")
def control_plane_health() -> dict:
    return {"status": "ok", "module": "control_plane"}


@router.get("/approvals")
def list_approvals(project_id: str | None = None, user: CurrentUser = Depends(current_user)) -> dict:
    if user.is_guest and project_id is None:
        project_id = user.project_id
    if project_id:
        require_project_access(user, project_id)
    return {"pending": approvals.list_pending(project_id)}


@router.post("/approvals/{approval_id}/approve")
def approve(approval_id: str, user: CurrentUser = Depends(current_user)) -> dict:
    if user.is_guest:
        from app.firestore import get_db

        snap = get_db().collection("approval_requests").document(approval_id).get()
        if snap.exists:
            require_project_access(user, (snap.to_dict() or {}).get("project_id", ""))
    return approvals.approve(approval_id)


@router.post("/approvals/{approval_id}/reject")
def reject(approval_id: str, user: CurrentUser = Depends(current_user)) -> dict:
    if user.is_guest:
        from app.firestore import get_db

        snap = get_db().collection("approval_requests").document(approval_id).get()
        if snap.exists:
            require_project_access(user, (snap.to_dict() or {}).get("project_id", ""))
    return approvals.reject(approval_id)


@router.get("/features/{project_id}")
def feature_states(project_id: str, user: CurrentUser = Depends(current_user)) -> dict:
    require_project_access(user, project_id)
    from app.firestore import get_db

    snap = get_db().collection("feature_states").document(project_id).get()
    return snap.to_dict() if snap.exists else {}


@router.post("/features/{project_id}/{feature}/disable")
def disable_feature(project_id: str, feature: str, user: CurrentUser = Depends(current_user)) -> dict:
    """Explicit app deletion: remove a feature and all app-scoped data."""
    require_project_access(user, project_id)
    return approvals.disable_feature(project_id, feature)


@router.post("/features/{project_id}/{feature}/rollback")
def rollback_feature(project_id: str, feature: str, user: CurrentUser = Depends(current_user)) -> dict:
    """Rollback one feature to its previous published version, or disable if it was newly created."""
    require_project_access(user, project_id)
    return approvals.rollback_feature(project_id, feature)


@router.post("/features/{project_id}/{feature}/worker")
def set_worker(project_id: str, feature: str, body: WorkerToggleIn, user: CurrentUser = Depends(current_user)) -> dict:
    """Show/hide a feature's managing AI worker (instruction area)."""
    require_project_access(user, project_id)
    return approvals.set_worker(project_id, feature, body.enabled)


@router.get("/workers")
def workers(project_id: str = "default", user: CurrentUser = Depends(current_user)) -> dict:
    """Status monitor: the worker registry (type/status/model/freshness), the live
    background builds, and this project's run usage."""
    require_project_access(user, project_id)
    return {
        "registry": worker_status.list_workers(project_id),
        "workers": [w for w in monitor.running_workers() if w.get("project_id") == project_id],
        "usage": guard.usage(project_id),
    }


@router.post("/worker/{worker_type}/start")
def worker_start(worker_type: str, project_id: str = "default", user: CurrentUser = Depends(current_user)) -> dict:
    """Start/wake a worker (spec §5: other workers start/stop one another)."""
    require_project_access(user, project_id)
    return worker_status.start_worker(worker_type, project_id)


@router.post("/worker/{worker_type}/stop")
def worker_stop(worker_type: str, project_id: str = "default", user: CurrentUser = Depends(current_user)) -> dict:
    """Stop a worker."""
    require_project_access(user, project_id)
    return worker_status.stop_worker(worker_type, project_id)


@router.get("/runs")
def runs(project_id: str = "default", limit: int = 20, user: CurrentUser = Depends(current_user)) -> dict:
    """Developer view: recent pipeline runs (goal / span / last status)."""
    require_project_access(user, project_id)
    from app.harness import service as harness

    structured = harness.list_runs(project_id, limit)
    if structured:
        runs_out = []
        for r in structured:
            runs_out.append(
                {
                    "task_id": r.get("run_id"),
                    "run_id": r.get("run_id"),
                    "project_id": r.get("project_id"),
                    "goal": r.get("request_text"),
                    "intent": r.get("request_type"),
                    "first_ts": r.get("started_at"),
                    "last_ts": r.get("updated_at"),
                    "events": r.get("event_count") or 0,
                    "last_status": r.get("status"),
                    "running": r.get("status") == "running",
                    "current_stage": r.get("current_stage"),
                    "last_event": r.get("last_event"),
                }
            )
        return {"runs": runs_out}
    return {"runs": worker_bus.list_runs(project_id, limit)}


@router.get("/templates")
def templates_catalogue() -> dict:
    """Default mini-app templates available to deploy on request (no html)."""
    from app import templates

    return {"templates": templates.list_templates()}


@router.get("/pipeline-status/{project_id}")
def pipeline_status(project_id: str, user: CurrentUser = Depends(current_user)) -> dict:
    """Pipeline-status API the Receptor uses to answer 状況照会: current stage, live
    build diagnosis, executor liveness, latest run outcome, and the next action."""
    require_project_access(user, project_id)
    from app.reception import service as reception_service

    return reception_service.pipeline_status(project_id)


@router.get("/messages/{task_id}")
def messages(task_id: str) -> dict:
    """MCP-like request/report thread for a work item (correlation/traceability)."""
    msgs = worker_bus.thread(task_id)
    if msgs:
        return {"task_id": task_id, "messages": msgs}
    from app.harness import service as harness

    events = [
        {
            "kind": "event",
            "ts": e.get("created_at"),
            "event": e.get("stage"),
            "text": e.get("message"),
            "status": e.get("status"),
            "worker": e.get("worker"),
        }
        for e in harness.get_events(task_id)
    ]
    return {"task_id": task_id, "messages": events}


@router.post("/stop-all")
def stop_all(user: CurrentUser = Depends(current_user)) -> dict:
    """Stop ALL running background workers across sessions (release every locked chat)."""
    if user.is_guest:
        return monitor.stop_project(user.project_id)
    return monitor.stop_all()


@router.get("/history/{project_id}")
def history(project_id: str, limit: int = 100, user: CurrentUser = Depends(current_user)) -> dict:
    """User-facing change history: who/what/when/why, newest first (from audit_logs)."""
    require_project_access(user, project_id)
    return {"project_id": project_id, "history": registry.list_history(project_id, limit)}


@router.get("/versions/{project_id}/{feature}")
def versions(project_id: str, feature: str, user: CurrentUser = Depends(current_user)) -> dict:
    """Published version stack for a feature (rollback targets), oldest→newest."""
    require_project_access(user, project_id)
    vs = registry.list_versions(project_id, feature)
    # Don't ship full HTML in the list view; just metadata.
    meta = [{"seq": v.get("seq"), "action": v.get("action"), "created_at": v.get("created_at"),
             "title": (v.get("manifest") or {}).get("title")} for v in vs]
    return {"project_id": project_id, "feature": feature, "versions": meta}


@router.post("/reset")
def reset(user: CurrentUser = Depends(current_user)) -> dict:
    """DEV/admin only: wipe all app data and return to the initial main-chat-only state."""
    if not get_settings().is_local and not user.is_admin:
        raise HTTPException(status_code=403, detail="初期化はローカル開発または管理者のみ実行できます")
    return registry.reset_all()
