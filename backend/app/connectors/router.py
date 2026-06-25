"""App-scoped user-defined external API connectors.

Generated apps may define connectors for their own feature via AF.defineConnector
and call only registered actions via AF.api("connector.action", params). This is
not an arbitrary proxy: base URLs, paths, methods, and auth are fixed at
definition time and scoped to the current user/project/feature.
"""
from __future__ import annotations

from datetime import datetime, timezone
from string import Formatter
from typing import Any
from urllib.parse import urljoin

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import CurrentUser, current_user
from app.control_plane.registry import _audit
from app.firestore import get_db

router = APIRouter(prefix="/api/connectors", tags=["connectors"])

_APP_CONNECTORS = "app_connectors"
_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_ALLOWED_AUTH_TYPES = {"none", "bearer", "api_key_header", "basic", "custom_header"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(value: str, label: str) -> str:
    normalized = (value or "").strip()
    if not normalized or len(normalized) > 80:
        raise HTTPException(status_code=400, detail=f"{label} が不正です")
    if not all(c.islower() or c.isdigit() or c in {"_", "-"} for c in normalized):
        raise HTTPException(status_code=400, detail=f"{label} は英小文字・数字・_・- のみ使えます")
    return normalized


def _doc_id(user: CurrentUser, project_id: str, feature: str, connector_id: str) -> str:
    return f"{user.uid}|{project_id}|{feature}|{connector_id}"


def _connector_doc(user: CurrentUser, project_id: str, feature: str, connector_id: str):
    return get_db().collection(_APP_CONNECTORS).document(_doc_id(user, project_id, feature, connector_id))


def _public_connector(doc: dict[str, Any]) -> dict[str, Any]:
    public = {k: v for k, v in doc.items() if k != "auth"}
    auth = doc.get("auth") if isinstance(doc.get("auth"), dict) else {}
    public["auth"] = {"type": auth.get("type") or "none", "configured": bool(auth and auth.get("type") != "none")}
    return public


def _split_action_name(name: str) -> tuple[str, str]:
    left, dot, right = (name or "").partition(".")
    if not dot or not left or not right:
        raise HTTPException(status_code=400, detail="action name must be '<connector>.<action>'")
    return _safe_id(left, "connector_id"), _safe_id(right, "action_id")


def _validate_url(base_url: str) -> str:
    value = (base_url or "").strip().rstrip("/")
    if not (value.startswith("https://") or value.startswith("http://localhost") or value.startswith("http://127.0.0.1")):
        raise HTTPException(status_code=400, detail="base_url は https://、localhost、127.0.0.1 のみ許可します")
    return value


def _action_params(path: str) -> set[str]:
    return {field for _, field, _, _ in Formatter().parse(path or "") if field}


def _render_path(path: str, params: dict[str, Any]) -> str:
    needed = _action_params(path)
    missing = [key for key in needed if params.get(key) in (None, "")]
    if missing:
        raise HTTPException(status_code=400, detail=f"path parameter が不足しています: {', '.join(missing)}")
    safe = {key: str(params[key]).strip() for key in needed}
    rendered = path.format(**safe)
    if not rendered.startswith("/"):
        rendered = "/" + rendered
    if ".." in rendered:
        raise HTTPException(status_code=400, detail="path に '..' は使えません")
    return rendered


class ConnectorActionDef(BaseModel):
    method: str = Field(default="GET", max_length=10)
    path: str = Field(min_length=1, max_length=300)
    side_effect: str = Field(default="read", max_length=20)
    description: str = Field(default="", max_length=300)


class ConnectorAuthDef(BaseModel):
    type: str = Field(default="none", max_length=30)
    token: str = Field(default="", max_length=4000)
    username: str = Field(default="", max_length=300)
    password: str = Field(default="", max_length=4000)
    header_name: str = Field(default="", max_length=120)
    header_value: str = Field(default="", max_length=4000)


class ConnectorDefineIn(BaseModel):
    connector_id: str = Field(min_length=1, max_length=80)
    label: str = Field(default="", max_length=120)
    base_url: str = Field(min_length=1, max_length=300)
    auth: ConnectorAuthDef = Field(default_factory=ConnectorAuthDef)
    actions: dict[str, ConnectorActionDef] = Field(default_factory=dict)
    project_id: str = "default"
    feature: str = Field(default="", max_length=80)


class ConnectorInvokeIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    params: dict[str, Any] = Field(default_factory=dict)
    project_id: str = "default"
    feature: str = Field(min_length=1, max_length=80)


@router.post("/define")
def define_connector(body: ConnectorDefineIn, user: CurrentUser = Depends(current_user)) -> dict:
    feature = _safe_id(body.feature, "feature")
    project_id = _safe_id(body.project_id, "project_id")
    connector_id = _safe_id(body.connector_id, "connector_id")
    if not body.actions:
        raise HTTPException(status_code=400, detail="actions を1件以上定義してください")
    actions: dict[str, dict[str, Any]] = {}
    for raw_action_id, action in body.actions.items():
        action_id = _safe_id(raw_action_id, "action_id")
        method = action.method.upper()
        if method not in _ALLOWED_METHODS:
            raise HTTPException(status_code=400, detail=f"{action_id}: method が不正です")
        if not action.path.startswith("/"):
            raise HTTPException(status_code=400, detail=f"{action_id}: path は / から始めてください")
        actions[action_id] = {
            "method": method,
            "path": action.path,
            "side_effect": action.side_effect if action.side_effect in {"read", "low", "medium", "high"} else "read",
            "description": action.description,
        }
    auth = body.auth.model_dump()
    if auth["type"] not in _ALLOWED_AUTH_TYPES:
        raise HTTPException(status_code=400, detail="auth.type が不正です")
    if auth["type"] in {"api_key_header", "custom_header"} and not auth.get("header_name"):
        raise HTTPException(status_code=400, detail="header_name が必要です")
    doc = {
        "uid": user.uid,
        "email": user.email,
        "connector_id": connector_id,
        "project_id": project_id,
        "feature": feature,
        "label": body.label.strip()[:120] or connector_id,
        "base_url": _validate_url(body.base_url),
        "auth": auth,
        "actions": actions,
        "updated_at": _now_iso(),
    }
    _connector_doc(user, project_id, feature, connector_id).set(doc, merge=True)
    _audit("connectors.defined", f"connector:{feature}:{connector_id}", {"feature": feature, "connector_id": connector_id})
    return {"ok": True, "connector": _public_connector(doc)}


@router.get("")
def list_feature_connectors(
    project_id: str = "default",
    feature: str = "",
    user: CurrentUser = Depends(current_user),
) -> dict:
    feature = _safe_id(feature, "feature")
    project_id = _safe_id(project_id, "project_id")
    docs = get_db().collection(_APP_CONNECTORS).where("uid", "==", user.uid).stream()
    items = []
    for doc in docs:
        data = doc.to_dict() or {}
        if data.get("project_id") == project_id and data.get("feature") == feature:
            items.append(_public_connector(data))
    return {"items": items}


@router.delete("/{connector_id}")
def delete_connector(
    connector_id: str,
    project_id: str = "default",
    feature: str = "",
    user: CurrentUser = Depends(current_user),
) -> dict:
    connector_id = _safe_id(connector_id, "connector_id")
    feature = _safe_id(feature, "feature")
    project_id = _safe_id(project_id, "project_id")
    _connector_doc(user, project_id, feature, connector_id).delete()
    _audit("connectors.deleted", f"connector:{feature}:{connector_id}", {"feature": feature, "connector_id": connector_id})
    return {"ok": True}


def _auth_kwargs(auth: dict[str, Any]) -> tuple[dict[str, str], httpx.Auth | None]:
    auth_type = auth.get("type") or "none"
    headers: dict[str, str] = {}
    if auth_type == "bearer" and auth.get("token"):
        headers["Authorization"] = f"Bearer {auth['token']}"
    elif auth_type == "api_key_header" and auth.get("header_name") and auth.get("header_value"):
        headers[str(auth["header_name"])] = str(auth["header_value"])
    elif auth_type == "custom_header" and auth.get("header_name") and auth.get("header_value"):
        headers[str(auth["header_name"])] = str(auth["header_value"])
    elif auth_type == "basic":
        return headers, httpx.BasicAuth(str(auth.get("username") or ""), str(auth.get("password") or ""))
    return headers, None


@router.post("/invoke")
def invoke(body: ConnectorInvokeIn, user: CurrentUser = Depends(current_user)) -> dict:
    connector_id, action_id = _split_action_name(body.name)
    feature = _safe_id(body.feature, "feature")
    project_id = _safe_id(body.project_id, "project_id")
    snap = _connector_doc(user, project_id, feature, connector_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="connector not found")
    connector = snap.to_dict() or {}
    action = (connector.get("actions") or {}).get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="connector action not found")
    method = str(action.get("method") or "GET").upper()
    path = _render_path(str(action.get("path") or ""), body.params)
    base_url = str(connector.get("base_url") or "")
    url = urljoin(base_url + "/", path.lstrip("/"))
    path_keys = _action_params(str(action.get("path") or ""))
    remaining = {k: v for k, v in body.params.items() if k not in path_keys}
    headers, auth = _auth_kwargs(connector.get("auth") if isinstance(connector.get("auth"), dict) else {})
    request_kwargs: dict[str, Any] = {"headers": headers}
    if auth is not None:
        request_kwargs["auth"] = auth
    if method == "GET":
        request_kwargs["params"] = remaining
    elif remaining:
        request_kwargs["json"] = remaining
    _audit(
        "connectors.invoke_requested",
        f"connector:{feature}:{connector_id}.{action_id}",
        {
            "connector_id": connector_id,
            "action_id": action_id,
            "base_url": base_url,
            "feature": body.feature,
            "project_id": body.project_id,
            "side_effect": action.get("side_effect"),
        },
    )
    try:
        with httpx.Client(timeout=20) as client:
            response = client.request(method, url, **request_kwargs)
            response.raise_for_status()
            try:
                data: Any = response.json()
            except ValueError:
                data = response.text
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300] or f"HTTP {exc.response.status_code}"
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _connector_doc(user, project_id, feature, connector_id).set({"last_used_at": _now_iso()}, merge=True)
    return {"ok": True, "connector": connector_id, "action": action_id, "data": data}
