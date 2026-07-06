"""App-scoped user-defined external API connectors.

Generated apps may define connectors for their own feature via AF.defineConnector
and call only registered actions via AF.api("connector.action", params). This is
not an arbitrary proxy: base URLs, paths, methods, and auth are fixed at
definition time and scoped to the current user/project/feature.
"""
from __future__ import annotations

import base64
import re
from datetime import datetime, timezone
from string import Formatter
from typing import Any
from urllib.parse import urljoin, urlsplit

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
_ALLOWED_SIDE_EFFECTS = {"read", "low", "medium", "high"}
_TEMPLATE_REF_RE = re.compile(r"^\$(params|auth|secret)\.([A-Za-z0-9_]+)$")
_SECRET_FIELDS = {"token", "username", "password", "header_name", "header_value"}
_MAX_IMAGE_BYTES = 1_500_000


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
    configured = bool(
        auth
        and (
            auth.get("type") != "none"
            or auth.get("token")
            or auth.get("username")
            or auth.get("password")
            or auth.get("header_value")
        )
    )
    public["auth"] = {"type": auth.get("type") or "none", "configured": configured}
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


def _ensure_same_origin(base_url: str, url: str) -> None:
    """Reject a resolved URL that left the connector's declared origin.

    Defense in depth against SSRF: even if a path parameter smuggles an absolute
    URL past rendering, the backend must never proxy to an arbitrary host."""
    base_parts, url_parts = urlsplit(base_url), urlsplit(url)
    if url_parts.scheme != base_parts.scheme or url_parts.netloc != base_parts.netloc:
        raise HTTPException(status_code=400, detail="path が base_url の外を指しています")


def _normalize_side_effect(value: str) -> str:
    side_effect = (value or "read").strip().lower()
    if side_effect == "write":
        return "medium"
    return side_effect if side_effect in _ALLOWED_SIDE_EFFECTS else "read"


def _action_params(path: str) -> set[str]:
    return {field for _, field, _, _ in Formatter().parse(path or "") if field}


def _render_path(path: str, params: dict[str, Any]) -> str:
    needed = _action_params(path)
    missing = [key for key in needed if params.get(key) in (None, "")]
    if missing:
        raise HTTPException(status_code=400, detail=f"path parameter が不足しています: {', '.join(missing)}")
    safe = {key: str(params[key]).strip() for key in needed}
    for key, value in safe.items():
        # A path parameter must stay a path segment: an absolute URL ("https://…")
        # or scheme-relative ("//host/…") value would make urljoin leave base_url
        # (SSRF), and a backslash can smuggle separators past later checks.
        if "://" in value or value.startswith("//") or "\\" in value:
            raise HTTPException(status_code=400, detail=f"path parameter が不正です: {key}")
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
    query_template: dict[str, Any] = Field(default_factory=dict)
    body_template: dict[str, Any] = Field(default_factory=dict)


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


def _resolve_template_value(value: Any, *, params: dict[str, Any], auth: dict[str, Any]) -> Any:
    """Resolve a connector action template without exposing secrets to the app.

    Supported placeholders are whole-string references:
    - $params.name: value supplied by the app at invoke time
    - $auth.password / $secret.password: secret stored in connector auth

    Literal strings and nested dict/list structures are preserved.
    """
    if isinstance(value, str):
        match = _TEMPLATE_REF_RE.fullmatch(value.strip())
        if not match:
            return value
        scope, key = match.groups()
        if scope == "params":
            if key not in params:
                raise HTTPException(status_code=400, detail=f"template parameter が不足しています: {key}")
            return params[key]
        if key not in _SECRET_FIELDS:
            raise HTTPException(status_code=400, detail=f"template secret が不正です: {key}")
        secret = auth.get(key)
        if secret in (None, ""):
            raise HTTPException(status_code=400, detail=f"connector secret が未設定です: {key}")
        return secret
    if isinstance(value, list):
        return [_resolve_template_value(v, params=params, auth=auth) for v in value]
    if isinstance(value, dict):
        return {str(k): _resolve_template_value(v, params=params, auth=auth) for k, v in value.items()}
    return value


def _resolve_template(template: Any, *, params: dict[str, Any], auth: dict[str, Any]) -> dict[str, Any]:
    if not template:
        return {}
    if not isinstance(template, dict):
        raise HTTPException(status_code=400, detail="connector template は object である必要があります")
    resolved = _resolve_template_value(template, params=params, auth=auth)
    if not isinstance(resolved, dict):
        raise HTTPException(status_code=400, detail="connector template は object に解決される必要があります")
    return resolved


def _connector_response(*, connector_id: str, action_id: str, data: Any) -> dict[str, Any]:
    """Return connector metadata plus the upstream payload in a generated-app-friendly shape.

    Generated apps often expect `const res = await AF.api(...); res.accessJwt`.
    Existing code also expects the explicit wrapper `res.data`. Keep both forms.
    """
    response = {"ok": True, "connector": connector_id, "action": action_id, "data": data}
    if isinstance(data, dict):
        response.update({str(k): v for k, v in data.items() if k not in response})
    return response


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
            "side_effect": _normalize_side_effect(action.side_effect),
            "description": action.description,
            "query_template": action.query_template,
            "body_template": action.body_template,
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
    _ensure_same_origin(base_url, url)
    path_keys = _action_params(str(action.get("path") or ""))
    remaining = {k: v for k, v in body.params.items() if k not in path_keys}
    auth_doc = connector.get("auth") if isinstance(connector.get("auth"), dict) else {}
    headers, auth = _auth_kwargs(auth_doc)
    request_kwargs: dict[str, Any] = {"headers": headers}
    if auth is not None:
        request_kwargs["auth"] = auth
    if method == "GET":
        query_template = action.get("query_template") or {}
        request_kwargs["params"] = _resolve_template(query_template, params=body.params, auth=auth_doc) if query_template else remaining
    else:
        body_template = action.get("body_template") or {}
        payload = _resolve_template(body_template, params=body.params, auth=auth_doc) if body_template else remaining
        if payload:
            request_kwargs["json"] = payload
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
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type.startswith("image/"):
                content = response.content
                if len(content) > _MAX_IMAGE_BYTES:
                    raise HTTPException(status_code=502, detail="image response too large")
                data = {
                    "content_type": content_type,
                    "data_url": f"data:{content_type};base64,{base64.b64encode(content).decode('ascii')}",
                }
            else:
                try:
                    data = response.json()
                except ValueError:
                    data = response.text
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300] or f"HTTP {exc.response.status_code}"
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _connector_doc(user, project_id, feature, connector_id).set({"last_used_at": _now_iso()}, merge=True)
    return _connector_response(connector_id=connector_id, action_id=action_id, data=data)
