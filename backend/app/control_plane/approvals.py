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


def find_latest_pending(project_id: str) -> dict | None:
    """Newest pending approval for a project (for conversational 「反映して」)."""
    pending = list_pending(project_id)
    if not pending:
        return None
    return max(pending, key=lambda d: d.get("created_at", ""))


def disable_active_features(project_id: str) -> list[str]:
    """Soft-disable every active feature of a project (conversational 「戻して」)."""
    snap = _feature_state_ref(project_id).get()
    if not snap.exists:
        return []
    disabled: list[str] = []
    for key, value in snap.to_dict().items():
        if value == "active":
            disable_feature(project_id, key)
            disabled.append(key)
    return disabled


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

    # Standard spec: feature gets a managing worker unless the plan opted out.
    # Also carry the view's chosen theme so the frontend renders it (idea 3 §2.6).
    plan_snap = db.collection("work_plans").document(task_id).get()
    has_worker = True
    theme = "default"
    if plan_snap.exists:
        views = plan_snap.to_dict().get("planned_views", [])
        if views:
            has_worker = any(v.get("has_worker", True) for v in views)
            theme = views[0].get("theme", "default") or "default"

    # Activate the generated view_manifest (for generated features) and carry its
    # title so the dynamic left menu can label it.
    title = {"task": "タスク管理", "pdf_memo": "PDFメモ"}.get(feature, feature)
    gv_ref = db.collection("generated_views").document(f"{project_id}_{feature}")
    gv = gv_ref.get()
    if gv.exists:
        gv_ref.set({"status": "active", "updated_at": _now_iso()}, merge=True)
        gvd = gv.to_dict()
        title = gvd.get("title") or title
        theme = gvd.get("theme", theme) or theme

    _feature_state_ref(project_id).set(
        {
            feature: "active",
            f"{feature}_worker": has_worker,
            f"{feature}_theme": theme,
            f"{feature}_title": title,
            "updated_at": _now_iso(),
        },
        merge=True,
    )

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


def set_worker(project_id: str, feature: str, enabled: bool) -> dict:
    """Turn a feature's managing AI worker on/off (instruction area show/hide)."""
    _feature_state_ref(project_id).set(
        {f"{feature}_worker": enabled, "updated_at": _now_iso()}, merge=True
    )
    _audit("feature.worker_toggled", f"{project_id}:{feature}", {"enabled": enabled})
    return {"project_id": project_id, "feature": feature, "worker_enabled": enabled}
