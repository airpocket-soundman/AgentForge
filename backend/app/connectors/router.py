"""User-managed external API connectors.

This router is the only path generated apps may use for external services. The
sandboxed HTML calls AF.api("connector.action", params); the shell forwards that
request here. URLs, credentials, and headers remain server-side.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import CurrentUser, current_user
from app.connectors.registry import get_connector, list_connectors, split_action_name
from app.control_plane.registry import _audit
from app.firestore import get_db

router = APIRouter(prefix="/api/connectors", tags=["connectors"])

_USER_CONNECTORS = "user_connectors"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _doc_id(user: CurrentUser, connector_id: str) -> str:
    return f"{user.uid}_{connector_id}"


def _public_connector(connector: dict[str, Any], state: dict[str, Any] | None = None) -> dict[str, Any]:
    state = state or {}
    return {
        "id": connector["id"],
        "label": connector["label"],
        "description": connector.get("description", ""),
        "enabled": bool(connector.get("enabled")),
        "auth_modes": connector.get("auth_modes", []),
        "scopes": connector.get("scopes", []),
        "actions": connector.get("actions", {}),
        "user_status": state.get("status") or "disconnected",
        "account_label": state.get("account_label") or "",
        "granted_scopes": state.get("scopes") or [],
        "credential_status": state.get("credential_status") or "not_configured",
        "updated_at": state.get("updated_at"),
        "last_used_at": state.get("last_used_at"),
    }


def _connection_state(user: CurrentUser, connector_id: str) -> dict[str, Any] | None:
    snap = get_db().collection(_USER_CONNECTORS).document(_doc_id(user, connector_id)).get()
    return snap.to_dict() if snap.exists else None


class ConnectorConnectionIn(BaseModel):
    account_label: str = Field(default="", max_length=120)
    scopes: list[str] = Field(default_factory=list)


class ConnectorInvokeIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    params: dict[str, Any] = Field(default_factory=dict)
    project_id: str = "default"
    feature: str = Field(default="", max_length=80)


@router.get("")
def connectors(user: CurrentUser = Depends(current_user)) -> dict:
    states = {}
    docs = get_db().collection(_USER_CONNECTORS).where("uid", "==", user.uid).stream()
    for doc in docs:
        data = doc.to_dict() or {}
        states[data.get("connector_id")] = data
    return {
        "items": [_public_connector(connector, states.get(connector["id"])) for connector in list_connectors()]
    }


@router.post("/{connector_id}/connection")
def connect(connector_id: str, body: ConnectorConnectionIn, user: CurrentUser = Depends(current_user)) -> dict:
    connector = get_connector(connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="connector not found")
    if not connector.get("enabled"):
        raise HTTPException(status_code=409, detail="このサービスはアプリ管理者がまだ有効化していません")

    allowed_scopes = set(connector.get("scopes") or [])
    scopes = sorted({s for s in body.scopes if s in allowed_scopes}) or ["read"]
    if "read" not in scopes and "read" in allowed_scopes:
        scopes.insert(0, "read")

    doc = {
        "uid": user.uid,
        "email": user.email,
        "connector_id": connector_id,
        "status": "connected",
        "account_label": body.account_label.strip()[:120],
        "scopes": scopes,
        "credential_status": "not_configured",
        "updated_at": _now_iso(),
    }
    get_db().collection(_USER_CONNECTORS).document(_doc_id(user, connector_id)).set(doc, merge=True)
    _audit("connectors.user_connected", f"user_connectors:{user.uid}:{connector_id}", {"connector_id": connector_id})
    return _public_connector(connector, doc)


@router.delete("/{connector_id}/connection")
def disconnect(connector_id: str, user: CurrentUser = Depends(current_user)) -> dict:
    connector = get_connector(connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="connector not found")
    doc = {
        "uid": user.uid,
        "email": user.email,
        "connector_id": connector_id,
        "status": "disconnected",
        "updated_at": _now_iso(),
    }
    get_db().collection(_USER_CONNECTORS).document(_doc_id(user, connector_id)).set(doc, merge=True)
    _audit("connectors.user_disconnected", f"user_connectors:{user.uid}:{connector_id}", {"connector_id": connector_id})
    return _public_connector(connector, doc)


@router.post("/invoke")
def invoke(body: ConnectorInvokeIn, user: CurrentUser = Depends(current_user)) -> dict:
    try:
        connector_id, action_id = split_action_name(body.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    connector = get_connector(connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="connector not found")
    if not connector.get("enabled"):
        raise HTTPException(status_code=409, detail="このコネクタは無効です")
    action = (connector.get("actions") or {}).get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="connector action not found")
    if not action.get("enabled"):
        raise HTTPException(status_code=409, detail="この操作はまだ有効化されていません")

    state = _connection_state(user, connector_id)
    if not state or state.get("status") != "connected":
        raise HTTPException(status_code=403, detail="プロフィールでこの外部サービスの利用を許可してください")

    required_scope = "write" if action.get("side_effect") in {"low", "medium", "high"} else "read"
    if required_scope not in (state.get("scopes") or []):
        raise HTTPException(status_code=403, detail="この操作に必要な権限がありません")

    get_db().collection(_USER_CONNECTORS).document(_doc_id(user, connector_id)).set(
        {"last_used_at": _now_iso()}, merge=True
    )
    _audit(
        "connectors.invoke_requested",
        f"connector:{connector_id}.{action_id}",
        {
            "connector_id": connector_id,
            "action_id": action_id,
            "feature": body.feature,
            "project_id": body.project_id,
            "side_effect": action.get("side_effect"),
        },
    )
    raise HTTPException(
        status_code=501,
        detail="コネクタの安全な許可経路は準備済みですが、この外部API action の実通信アダプタは未実装です",
    )

