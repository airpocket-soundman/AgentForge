"""Approval & lifecycle control — the human gate that promotes pending → active,
safe rollback, and explicit feature deletion with data purge.

This is where the "AIに強権限を渡さない" design becomes concrete: agents only
register pending intent; this module performs the privileged state change, and
only in response to an explicit user action. Every transition is audited.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.control_plane import registry
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
            _soft_disable_feature(project_id, key, reason="rollback")
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

    # Guard: never publish an unfinished (stub) generation, even if one was left
    # pending (e.g. created while the LLM was unreachable). Only working apps publish.
    _ts = db.collection("task_runs").document(task_id).get()
    _feat = (_ts.to_dict() or {}).get("feature", "unknown") if _ts.exists else "unknown"
    _gv = db.collection("generated_views").document(f"{project_id}_{_feat}").get()
    if _gv.exists and (_gv.to_dict() or {}).get("generated_by") == "stub":
        raise HTTPException(status_code=409, detail="生成が未完成（仮ページ）のため公開できません。作り直してください。")
    from app.safety_harness import service as safety_harness

    safety_harness.assert_publishable(
        project_id=project_id,
        feature=_feat,
        task_id=task_id,
        approval_id=approval_id,
    )

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
    gvd = None
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

    # Snapshot the now-published state for 巻き戻し, and mark it the latest change.
    if gvd is not None:
        registry.snapshot_version(project_id, feature, gvd, "publish")
    registry.set_last_changed(project_id, feature)

    appr_ref.set({"status": "approved", "decided_at": _now_iso()}, merge=True)
    _audit("approval.approved", approval_id, {"task_id": task_id, "feature": feature}, project_id=project_id)
    return {"approval_id": approval_id, "status": "approved", "feature": feature, "project_id": project_id}


def publish_edit(project_id: str, feature: str, manifest: dict) -> dict:
    """Publish an edited feature: overwrite the live (active) view_manifest with the
    regenerated one, keeping the feature active. The human gate here is the user's
    preview + 「反映して」 — no new pending approval is needed for an in-place edit."""
    if (manifest or {}).get("generated_by") == "stub":
        raise HTTPException(status_code=409, detail="修正版が未完成（仮ページ）のため公開できません。作り直してください。")
    from app.safety_harness import service as safety_harness

    safety_harness.assert_publishable(
        project_id=project_id,
        feature=feature,
        task_id=(manifest or {}).get("safety_harness", {}).get("task_id"),
        candidate=manifest,
    )
    db = get_db()
    db.collection("generated_views").document(f"{project_id}_{feature}").set(
        {
            **manifest,
            "project_id": project_id,
            "status": "active",
            "updated_at": _now_iso(),
        },
        merge=True,
    )
    _feature_state_ref(project_id).set(
        {
            feature: "active",
            f"{feature}_title": manifest.get("title") or feature,
            f"{feature}_theme": manifest.get("theme", "default") or "default",
            "updated_at": _now_iso(),
        },
        merge=True,
    )
    registry.snapshot_version(project_id, feature, manifest, "edit")
    registry.set_last_changed(project_id, feature)
    _audit("generated_view.edited", f"{project_id}:{feature}", {"title": manifest.get("title")}, project_id=project_id)
    return {"project_id": project_id, "feature": feature, "status": "active"}


def plan_rollback(versions: list) -> tuple[dict | None, str]:
    """Pure decision for 巻き戻し (linear, no branching). Given the version stack,
    return (restored_manifest, result) where result is one of:
      "none"      — no versions to roll back
      "disabled"  — only one version (undo creation → disable, restore nothing)
      "restored"  — restore the previous version's manifest
    The caller pops the current (top) version regardless."""
    if not versions:
        return None, "none"
    remaining = versions[:-1]
    if not remaining:
        return None, "disabled"
    return remaining[-1].get("manifest"), "restored"


def rollback_feature(project_id: str, feature: str) -> dict:
    """巻き戻し: undo the most recent publish of a feature by restoring the previous
    version (linear, no branching). If only one version exists, undoing the creation
    soft-disables the feature. Falls back to soft-disable when no version history."""
    versions = registry.list_versions(project_id, feature)
    if not versions:
        return {**_soft_disable_feature(project_id, feature, reason="rollback_no_versions"), "rolled_back_to": None}

    registry.pop_version(project_id, feature)  # drop the current (top) version
    remaining = versions[:-1]
    db = get_db()
    gv_ref = db.collection("generated_views").document(f"{project_id}_{feature}")

    if not remaining:  # undoing the very first version = "this feature never existed"
        gv_ref.set({"status": "disabled", "updated_at": _now_iso()}, merge=True)
        _feature_state_ref(project_id).set({feature: "disabled", "updated_at": _now_iso()}, merge=True)
        _audit("feature.rolled_back", f"{project_id}:{feature}",
               {"result": "creation_undone"}, project_id=project_id)
        return {"project_id": project_id, "feature": feature, "status": "disabled", "rolled_back_to": None}

    prev = remaining[-1]["manifest"]
    gv_ref.set({**prev, "project_id": project_id, "status": "active", "updated_at": _now_iso()}, merge=True)
    _feature_state_ref(project_id).set(
        {
            feature: "active",
            f"{feature}_title": prev.get("title") or feature,
            f"{feature}_theme": prev.get("theme", "default") or "default",
            "updated_at": _now_iso(),
        },
        merge=True,
    )
    _audit("feature.rolled_back", f"{project_id}:{feature}",
           {"to_seq": remaining[-1]["seq"]}, project_id=project_id)
    return {"project_id": project_id, "feature": feature, "status": "active", "rolled_back_to": remaining[-1]["seq"]}


def reject(approval_id: str) -> dict:
    appr_ref = get_db().collection("approval_requests").document(approval_id)
    appr = appr_ref.get()
    if not appr.exists:
        raise HTTPException(status_code=404, detail="approval_request が見つかりません")
    appr_ref.set({"status": "rejected", "decided_at": _now_iso()}, merge=True)
    _audit("approval.rejected", approval_id, {})
    return {"approval_id": approval_id, "status": "rejected"}


def _delete_stream(query) -> int:
    """Delete query results in small batches and return the deleted document count."""
    db = get_db()
    count = 0
    batch = db.batch()
    pending = 0
    for doc in query.stream():
        batch.delete(doc.reference)
        count += 1
        pending += 1
        if pending >= 400:
            batch.commit()
            batch = db.batch()
            pending = 0
    if pending:
        batch.commit()
    return count


def _purge_feature_data(project_id: str, feature: str) -> dict[str, int]:
    """Delete all app-scoped data for an explicit feature deletion.

    Audit logs are intentionally retained as the tamper-resistant record of who
    deleted what and when. Rollback uses _soft_disable_feature instead.
    """
    db = get_db()
    deleted: dict[str, int] = {}
    doc_id = f"{project_id}_{feature}"
    for collection in ("generated_views", "app_state", "feature_versions", "feature_requirements"):
        ref = db.collection(collection).document(doc_id)
        existed = ref.get().exists
        if existed:
            ref.delete()
        deleted[collection] = 1 if existed else 0

    deleted["feature_chats"] = _delete_stream(
        db.collection("feature_chats")
        .where(filter=FieldFilter("project_id", "==", project_id))
        .where(filter=FieldFilter("feature", "==", feature))
    )
    deleted["app_entities"] = _delete_stream(
        db.collection("app_entities")
        .where(filter=FieldFilter("project_id", "==", project_id))
        .where(filter=FieldFilter("feature", "==", feature))
    )

    # Legacy fixed task API data. Generated default task_manager uses app_state,
    # but keep this here so deleting the legacy "task" feature is also complete.
    deleted["app_tasks"] = 0
    if feature == "task":
        deleted["app_tasks"] = _delete_stream(
            db.collection("app_tasks").where(filter=FieldFilter("project_id", "==", project_id))
        )

    state_ref = _feature_state_ref(project_id)
    state = state_ref.get()
    if state.exists:
        data = state.to_dict() or {}
        fields = {
            feature: firestore.DELETE_FIELD,
            f"{feature}_title": firestore.DELETE_FIELD,
            f"{feature}_theme": firestore.DELETE_FIELD,
            f"{feature}_worker": firestore.DELETE_FIELD,
            "updated_at": _now_iso(),
        }
        if data.get("last_changed_feature") == feature:
            fields["last_changed_feature"] = firestore.DELETE_FIELD
        state_ref.update(fields)
        deleted["feature_state_fields"] = sum(1 for k in fields if k != "updated_at")
    else:
        deleted["feature_state_fields"] = 0
    return deleted


def _soft_disable_feature(project_id: str, feature: str, reason: str) -> dict:
    """Rollback-only: hide a feature without deleting data or version history."""
    _feature_state_ref(project_id).set({feature: "disabled", "updated_at": _now_iso()}, merge=True)
    _audit("feature.disabled", f"{project_id}:{feature}", {"reason": reason}, project_id=project_id)
    return {"project_id": project_id, "feature": feature, "status": "disabled"}


def archive_feature(project_id: str, feature: str) -> dict:
    """User-chosen reversible deletion: hide the app but keep app-scoped data."""
    return _soft_disable_feature(project_id, feature, reason="user_reversible_delete")


def disable_feature(project_id: str, feature: str) -> dict:
    """Explicit app deletion: remove the app and all app-scoped data.

    This is intentionally different from rollback, which is reversible and keeps
    version/data snapshots.
    """
    deleted = _purge_feature_data(project_id, feature)
    _audit("feature.deleted", f"{project_id}:{feature}", {"deleted": deleted}, project_id=project_id)
    return {"project_id": project_id, "feature": feature, "status": "deleted", "deleted": deleted}


def set_worker(project_id: str, feature: str, enabled: bool) -> dict:
    """Turn a feature's managing AI worker on/off (instruction area show/hide)."""
    _feature_state_ref(project_id).set(
        {f"{feature}_worker": enabled, "updated_at": _now_iso()}, merge=True
    )
    _audit("feature.worker_toggled", f"{project_id}:{feature}", {"enabled": enabled})
    return {"project_id": project_id, "feature": feature, "worker_enabled": enabled}
