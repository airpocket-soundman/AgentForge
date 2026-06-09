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


@router.post("/reset")
def reset() -> dict:
    """DEV ONLY: wipe all app data and return to the initial main-chat-only state."""
    return registry.reset_all()
