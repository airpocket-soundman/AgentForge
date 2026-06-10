"""Control Plane HTTP surface — approval gate and feature lifecycle."""
from fastapi import APIRouter

from app.control_plane import approvals, guard, monitor, registry
from app.models.tasks import WorkerToggleIn

router = APIRouter(prefix="/api/control-plane", tags=["control-plane"])


@router.get("/health")
def control_plane_health() -> dict:
    return {"status": "ok", "module": "control_plane"}


@router.get("/approvals")
def list_approvals(project_id: str | None = None) -> dict:
    return {"pending": approvals.list_pending(project_id)}


@router.post("/approvals/{approval_id}/approve")
def approve(approval_id: str) -> dict:
    return approvals.approve(approval_id)


@router.post("/approvals/{approval_id}/reject")
def reject(approval_id: str) -> dict:
    return approvals.reject(approval_id)


@router.get("/features/{project_id}")
def feature_states(project_id: str) -> dict:
    from app.firestore import get_db

    snap = get_db().collection("feature_states").document(project_id).get()
    return snap.to_dict() if snap.exists else {}


@router.post("/features/{project_id}/{feature}/disable")
def disable_feature(project_id: str, feature: str) -> dict:
    """Rollback: soft-disable (never delete) a feature."""
    return approvals.disable_feature(project_id, feature)


@router.post("/features/{project_id}/{feature}/worker")
def set_worker(project_id: str, feature: str, body: WorkerToggleIn) -> dict:
    """Show/hide a feature's managing AI worker (instruction area)."""
    return approvals.set_worker(project_id, feature, body.enabled)


@router.get("/workers")
def workers(project_id: str = "default") -> dict:
    """Status monitor: background workers running right now + this project's run usage."""
    return {"workers": monitor.running_workers(), "usage": guard.usage(project_id)}


@router.post("/stop-all")
def stop_all() -> dict:
    """Stop ALL running background workers across sessions (release every locked chat)."""
    return monitor.stop_all()


@router.get("/history/{project_id}")
def history(project_id: str, limit: int = 100) -> dict:
    """User-facing change history: who/what/when/why, newest first (from audit_logs)."""
    return {"project_id": project_id, "history": registry.list_history(project_id, limit)}


@router.get("/versions/{project_id}/{feature}")
def versions(project_id: str, feature: str) -> dict:
    """Published version stack for a feature (rollback targets), oldest→newest."""
    vs = registry.list_versions(project_id, feature)
    # Don't ship full HTML in the list view; just metadata.
    meta = [{"seq": v.get("seq"), "action": v.get("action"), "created_at": v.get("created_at"),
             "title": (v.get("manifest") or {}).get("title")} for v in vs]
    return {"project_id": project_id, "feature": feature, "versions": meta}


@router.post("/reset")
def reset() -> dict:
    """DEV ONLY: wipe all app data and return to the initial main-chat-only state."""
    return registry.reset_all()
