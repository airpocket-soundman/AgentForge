"""Approval & lifecycle control — the human gate that promotes pending → active,
and the safe rollback that disables (never deletes) a feature.

This is where the "AIに強権限を渡さない" design becomes concrete: agents only
register pending intent; this module performs the privileged state change, and
only in response to an explicit user action. Every transition is audited.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from app.control_plane.registry import _audit
from app.firestore import get_db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _feature_state_ref(project_id: str):
    return get_db().collection("feature_states").document(project_id)


def is_feature_active(project_id: str, feature: str) -> bool:
    snap = _feature_state_ref(project_id).get()
    return bool(snap.exists and snap.to_dict().get(feature) == "active")


def require_feature_active(project_id: str, feature: str) -> None:
    if not is_feature_active(project_id, feature):
        raise HTTPException(
            status_code=409,
            detail=f"この機能（{feature}）はまだ承認・有効化されていません。チャットで「反映して」と承認してください。",
        )


def list_pending(project_id: str | None = None) -> list[dict]:
    col = get_db().collection("approval_requests")
    query = col.where("status", "==", "pending_user_approval")
    if project_id:
        query = query.where("project_id", "==", project_id)
    return [d.to_dict() for d in query.stream()]


def _set_registry_status(collection: str, ids: list[str], status: str) -> None:
    col = get_db().collection(collection)
    for doc_id in ids:
        col.document(doc_id).set({"status": status, "updated_at": _now_iso()}, merge=True)


def approve(approval_id: str) -> dict:
    db = get_db()
    appr_ref = db.collection("approval_requests").document(approval_id)
    appr = appr_ref.get()
    if not appr.exists:
        raise HTTPException(status_code=404, detail="approval_request が見つかりません")
    data = appr.to_dict()
    if data.get("status") != "pending_user_approval":
        raise HTTPException(status_code=409, detail=f"既に処理済みです（status={data.get('status')}）")

    project_id = data["project_id"]
    task_id = data["task_id"]

    # Promote the registered artifacts: pending -> active.
    _set_registry_status("api_registry", data.get("target_apis", []), "active")
    _set_registry_status("ui_view_registry", data.get("target_views", []), "active")

    # Flip the per-project feature flag the generated API gates on.
    feature = "unknown"
    task_snap = db.collection("task_runs").document(task_id).get()
    if task_snap.exists:
        feature = task_snap.to_dict().get("feature", "unknown")
        db.collection("task_runs").document(task_id).set(
            {"status": "active", "current_step": "active", "updated_at": _now_iso()}, merge=True
        )
    _feature_state_ref(project_id).set({feature: "active", "updated_at": _now_iso()}, merge=True)

    appr_ref.set({"status": "approved", "decided_at": _now_iso()}, merge=True)
    _audit("approval.approved", approval_id, {"task_id": task_id, "feature": feature})
    return {"approval_id": approval_id, "status": "approved", "feature": feature, "project_id": project_id}


def reject(approval_id: str) -> dict:
    appr_ref = get_db().collection("approval_requests").document(approval_id)
    appr = appr_ref.get()
    if not appr.exists:
        raise HTTPException(status_code=404, detail="approval_request が見つかりません")
    appr_ref.set({"status": "rejected", "decided_at": _now_iso()}, merge=True)
    _audit("approval.rejected", approval_id, {})
    return {"approval_id": approval_id, "status": "rejected"}


def disable_feature(project_id: str, feature: str) -> dict:
    """Rollback: soft-disable a feature (never delete). Mirrors the '戻して' demo."""
    _feature_state_ref(project_id).set({feature: "disabled", "updated_at": _now_iso()}, merge=True)
    _audit("feature.disabled", f"{project_id}:{feature}", {"reason": "user_rollback"})
    return {"project_id": project_id, "feature": feature, "status": "disabled"}
