"""Generic generated-feature backend: a schema-flexible entity store + the view
manifest endpoint.

ANY AI-generated feature persists and reads its data here without hand-written code
per feature. Gated by the Control Plane (require_feature_active) exactly like the
task feature, so approval still matters.

- generated_views/{project_id}_{feature} : the view_manifest the UI Designer produced
- app_entities/{entity_id}               : {feature, project_id, data, timestamps}
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.auth import CurrentUser, current_user, require_project_access
from app.control_plane.approvals import require_feature_active
from app.firestore import get_db
from app.models.generated import EntityIn, EntityUpdate, StateIn

router = APIRouter(prefix="/api/app", tags=["generated-app:generic"])

_ENTITIES = "app_entities"
_VIEWS = "generated_views"
_STATE = "app_state"


def _state_doc_id(project_id: str, feature: str) -> str:
    return f"{project_id}_{feature}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _view_doc_id(project_id: str, feature: str) -> str:
    return f"{project_id}_{feature}"


@router.get("/view/{feature}")
def get_view(feature: str, project_id: str = "default", user: CurrentUser = Depends(current_user)) -> dict:
    """The active view_manifest for a generated feature (what the renderer draws)."""
    require_project_access(user, project_id)
    require_feature_active(project_id, feature)
    snap = get_db().collection(_VIEWS).document(_view_doc_id(project_id, feature)).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="この機能の view manifest が見つかりません")
    return snap.to_dict()


@router.get("/preview/{feature}")
def preview_view(feature: str, project_id: str = "default", user: CurrentUser = Depends(current_user)) -> dict:
    """The view_manifest for a feature regardless of approval status, so the chat
    can show a PREVIEW of generated code before the user publishes it."""
    require_project_access(user, project_id)
    snap = get_db().collection(_VIEWS).document(_view_doc_id(project_id, feature)).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="プレビュー対象が見つかりません")
    return snap.to_dict()


@router.get("/entities")
def list_entities(feature: str, project_id: str = "default", user: CurrentUser = Depends(current_user)) -> dict:
    require_project_access(user, project_id)
    require_feature_active(project_id, feature)
    docs = (
        get_db()
        .collection(_ENTITIES)
        .where("project_id", "==", project_id)
        .where("feature", "==", feature)
        .stream()
    )
    items = [d.to_dict() for d in docs]
    items.sort(key=lambda x: x.get("created_at", ""))
    return {"items": items}


@router.post("/entities")
def create_entity(body: EntityIn, user: CurrentUser = Depends(current_user)) -> dict:
    require_project_access(user, body.project_id)
    require_feature_active(body.project_id, body.feature)
    entity_id = f"e_{uuid.uuid4().hex[:12]}"
    doc = {
        "entity_id": entity_id,
        "feature": body.feature,
        "project_id": body.project_id,
        "data": body.data,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    get_db().collection(_ENTITIES).document(entity_id).set(doc)
    return doc


@router.patch("/entities/{entity_id}")
def update_entity(entity_id: str, body: EntityUpdate, user: CurrentUser = Depends(current_user)) -> dict:
    ref = get_db().collection(_ENTITIES).document(entity_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="not found")
    cur = snap.to_dict()
    require_project_access(user, cur["project_id"])
    require_feature_active(cur["project_id"], cur["feature"])
    merged = {**cur.get("data", {}), **body.data}
    ref.set({"data": merged, "updated_at": _now_iso()}, merge=True)
    return {**cur, "data": merged, "updated_at": _now_iso()}


@router.get("/state/{feature}")
def get_state(feature: str, project_id: str = "default", user: CurrentUser = Depends(current_user)) -> dict:
    """Whole-app persisted state for a generated app (AF.load() reads this)."""
    require_project_access(user, project_id)
    require_feature_active(project_id, feature)
    snap = get_db().collection(_STATE).document(_state_doc_id(project_id, feature)).get()
    if not snap.exists:
        return {"state": None}
    return {"state": (snap.to_dict() or {}).get("state")}


@router.put("/state/{feature}")
def put_state(feature: str, body: StateIn, user: CurrentUser = Depends(current_user)) -> dict:
    """Persist the whole-app state blob (AF.save() writes this)."""
    require_project_access(user, body.project_id)
    require_feature_active(body.project_id, feature)
    get_db().collection(_STATE).document(_state_doc_id(body.project_id, feature)).set(
        {
            "feature": feature,
            "project_id": body.project_id,
            "state": body.state,
            "updated_at": _now_iso(),
        }
    )
    return {"ok": True}


@router.delete("/entities/{entity_id}")
def delete_entity(entity_id: str, user: CurrentUser = Depends(current_user)) -> dict:
    ref = get_db().collection(_ENTITIES).document(entity_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="not found")
    cur = snap.to_dict()
    require_project_access(user, cur["project_id"])
    require_feature_active(cur["project_id"], cur["feature"])
    ref.delete()
    return {"deleted": entity_id}
