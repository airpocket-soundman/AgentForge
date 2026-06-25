"""Server-side external API adapters for user-approved connectors."""
from __future__ import annotations

import re
from typing import Any

import httpx


class ConnectorError(Exception):
    """Safe error surfaced to the connector router."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _limit(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, n))


def _required_text(values: dict[str, Any], key: str, label: str | None = None) -> str:
    value = str(values.get(key) or "").strip()
    if not value:
        raise ConnectorError(400, f"{label or key} が未設定です")
    return value


def _json_response(response: httpx.Response) -> Any:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            body = exc.response.json()
            detail = str(body.get("message") or body.get("error") or body.get("error_description") or "")
        except Exception:  # noqa: BLE001 - external APIs return mixed error bodies.
            detail = exc.response.text[:200]
        message = detail or f"外部APIが HTTP {exc.response.status_code} を返しました"
        raise ConnectorError(502, message) from exc
    try:
        return response.json()
    except ValueError as exc:
        raise ConnectorError(502, "外部APIの応答をJSONとして読めませんでした") from exc


def invoke_connector(
    connector_id: str,
    action_id: str,
    params: dict[str, Any],
    credential: dict[str, Any],
) -> dict[str, Any]:
    with httpx.Client(timeout=20) as client:
        if connector_id == "bluesky":
            data = _invoke_bluesky(client, action_id, params, credential)
        elif connector_id == "github":
            data = _invoke_github(client, action_id, params, credential)
        elif connector_id == "notion":
            data = _invoke_notion(client, action_id, params, credential)
        else:
            raise ConnectorError(501, "このコネクタの実通信アダプタは未実装です")
    return {"ok": True, "connector": connector_id, "action": action_id, "data": data}


def _invoke_bluesky(
    client: httpx.Client,
    action_id: str,
    params: dict[str, Any],
    credential: dict[str, Any],
) -> Any:
    identifier = _required_text(credential, "identifier", "Bluesky handle/email")
    password = _required_text(credential, "app_password", "Bluesky App Password")
    session = _json_response(
        client.post(
            "https://bsky.social/xrpc/com.atproto.server.createSession",
            json={"identifier": identifier, "password": password},
        )
    )
    token = _required_text(session, "accessJwt", "Bluesky access token")
    headers = {"Authorization": f"Bearer {token}"}
    if action_id == "get_timeline":
        response = client.get(
            "https://bsky.social/xrpc/app.bsky.feed.getTimeline",
            headers=headers,
            params={"limit": _limit(params.get("limit"), 30, 1, 100), "cursor": params.get("cursor") or None},
        )
        return _json_response(response)
    if action_id == "get_profile":
        actor = str(params.get("handle") or identifier).strip()
        response = client.get(
            "https://bsky.social/xrpc/app.bsky.actor.getProfile",
            headers=headers,
            params={"actor": actor},
        )
        return _json_response(response)
    if action_id == "get_thread":
        uri = _required_text(params, "uri")
        response = client.get(
            "https://bsky.social/xrpc/app.bsky.feed.getPostThread",
            headers=headers,
            params={"uri": uri, "depth": _limit(params.get("depth"), 4, 0, 20)},
        )
        return _json_response(response)
    raise ConnectorError(404, "Bluesky action not found")


def _invoke_github(
    client: httpx.Client,
    action_id: str,
    params: dict[str, Any],
    credential: dict[str, Any],
) -> Any:
    token = _required_text(credential, "token", "GitHub token")
    repo = _required_text(params, "repo")
    if not _REPO_RE.match(repo):
        raise ConnectorError(400, "repo は owner/name 形式で指定してください")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    base = f"https://api.github.com/repos/{repo}"
    if action_id == "list_issues":
        state = str(params.get("state") or "open")
        response = client.get(
            f"{base}/issues",
            headers=headers,
            params={"state": state, "per_page": _limit(params.get("per_page"), 30, 1, 100)},
        )
        return {"items": _json_response(response)}
    if action_id == "get_issue":
        number = _limit(params.get("number"), 0, 1, 999999999)
        response = client.get(f"{base}/issues/{number}", headers=headers)
        return {"item": _json_response(response)}
    raise ConnectorError(404, "GitHub action not found")


def _invoke_notion(
    client: httpx.Client,
    action_id: str,
    params: dict[str, Any],
    credential: dict[str, Any],
) -> Any:
    token = _required_text(credential, "token", "Notion token")
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    if action_id == "query_database":
        database_id = _required_text(params, "database_id")
        body: dict[str, Any] = {"page_size": _limit(params.get("page_size"), 25, 1, 100)}
        if isinstance(params.get("filter"), dict):
            body["filter"] = params["filter"]
        if isinstance(params.get("sorts"), list):
            body["sorts"] = params["sorts"]
        response = client.post(f"https://api.notion.com/v1/databases/{database_id}/query", headers=headers, json=body)
        return _json_response(response)
    if action_id == "get_page":
        page_id = _required_text(params, "page_id")
        response = client.get(f"https://api.notion.com/v1/pages/{page_id}", headers=headers)
        return _json_response(response)
    raise ConnectorError(404, "Notion action not found")
