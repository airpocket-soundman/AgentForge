"""Static connector catalogue for generated apps.

The catalogue defines what generated mini-apps may ask for. User credentials and
per-user permission live separately in Firestore; generated HTML never supplies
URLs, headers, or tokens.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


Connector = dict[str, Any]


CONNECTORS: dict[str, Connector] = {
    "bluesky": {
        "id": "bluesky",
        "label": "Bluesky",
        "description": "タイムライン、プロフィール、スレッドを扱うSNSコネクタ。",
        "enabled": True,
        "auth_modes": ["app_password", "oauth_future"],
        "credential_fields": [
            {"key": "identifier", "label": "Handle / email", "type": "text", "required": True},
            {"key": "app_password", "label": "App Password", "type": "password", "required": True},
        ],
        "scopes": ["read", "write"],
        "actions": {
            "get_profile": {"side_effect": "read", "enabled": True, "params_schema": {"handle": "string?"}},
            "get_timeline": {"side_effect": "read", "enabled": True, "params_schema": {"limit": "integer?", "cursor": "string?"}},
            "get_thread": {"side_effect": "read", "enabled": True, "params_schema": {"uri": "string"}},
            "create_post": {"side_effect": "medium", "enabled": False, "params_schema": {"text": "string"}},
        },
    },
    "github": {
        "id": "github",
        "label": "GitHub",
        "description": "Issue、Pull Request、コメントを扱う開発コネクタ。",
        "enabled": True,
        "auth_modes": ["personal_access_token", "oauth_future"],
        "credential_fields": [
            {"key": "token", "label": "Personal Access Token", "type": "password", "required": True},
        ],
        "scopes": ["read", "write"],
        "actions": {
            "list_issues": {"side_effect": "read", "enabled": True, "params_schema": {"repo": "string", "state": "string?"}},
            "get_issue": {"side_effect": "read", "enabled": True, "params_schema": {"repo": "string", "number": "integer"}},
            "create_comment": {"side_effect": "medium", "enabled": False, "params_schema": {"repo": "string", "number": "integer", "body": "string"}},
        },
    },
    "notion": {
        "id": "notion",
        "label": "Notion",
        "description": "データベース、ページ、タスク表を扱うコネクタ。",
        "enabled": True,
        "auth_modes": ["integration_token", "oauth_future"],
        "credential_fields": [
            {"key": "token", "label": "Integration Token", "type": "password", "required": True},
        ],
        "scopes": ["read", "write"],
        "actions": {
            "query_database": {"side_effect": "read", "enabled": True, "params_schema": {"database_id": "string", "filter": "object?"}},
            "get_page": {"side_effect": "read", "enabled": True, "params_schema": {"page_id": "string"}},
            "update_page": {"side_effect": "medium", "enabled": False, "params_schema": {"page_id": "string", "properties": "object"}},
        },
    },
    "x": {
        "id": "x",
        "label": "X",
        "description": "投稿検索やタイムライン表示用。API料金と制限が強いため初期状態は無効。",
        "enabled": False,
        "auth_modes": ["oauth_future"],
        "scopes": ["read"],
        "actions": {
            "search_posts": {"side_effect": "read", "enabled": False, "params_schema": {"query": "string"}},
            "get_user_posts": {"side_effect": "read", "enabled": False, "params_schema": {"username": "string"}},
        },
    },
    "slack": {
        "id": "slack",
        "label": "Slack",
        "description": "チャンネル、スレッド、メッセージを扱うコネクタ。初期状態は無効。",
        "enabled": False,
        "auth_modes": ["oauth_future"],
        "scopes": ["read", "write"],
        "actions": {
            "list_threads": {"side_effect": "read", "enabled": False, "params_schema": {"channel_id": "string"}},
            "post_message": {"side_effect": "medium", "enabled": False, "params_schema": {"channel_id": "string", "text": "string"}},
        },
    },
    "discord": {
        "id": "discord",
        "label": "Discord",
        "description": "Bot権限内のスレッド/メッセージ閲覧用。ユーザーアカウント自動操作は対象外。",
        "enabled": False,
        "auth_modes": ["bot_token_future", "oauth_future"],
        "scopes": ["read", "write"],
        "actions": {
            "list_threads": {"side_effect": "read", "enabled": False, "params_schema": {"channel_id": "string"}},
            "get_messages": {"side_effect": "read", "enabled": False, "params_schema": {"channel_id": "string"}},
        },
    },
    "google_sheets": {
        "id": "google_sheets",
        "label": "Google Sheets",
        "description": "シートの行読み取り/追記用。OAuth実装後に有効化する。",
        "enabled": False,
        "auth_modes": ["oauth_future"],
        "scopes": ["read", "write"],
        "actions": {
            "read_range": {"side_effect": "read", "enabled": False, "params_schema": {"spreadsheet_id": "string", "range": "string"}},
            "append_row": {"side_effect": "medium", "enabled": False, "params_schema": {"spreadsheet_id": "string", "range": "string", "values": "array"}},
        },
    },
    "google_calendar": {
        "id": "google_calendar",
        "label": "Google Calendar",
        "description": "予定閲覧/作成用。OAuth実装後に有効化する。",
        "enabled": False,
        "auth_modes": ["oauth_future"],
        "scopes": ["read", "write"],
        "actions": {
            "list_events": {"side_effect": "read", "enabled": False, "params_schema": {"calendar_id": "string?", "time_min": "string?"}},
            "create_event": {"side_effect": "medium", "enabled": False, "params_schema": {"calendar_id": "string?", "event": "object"}},
        },
    },
    "airtable": {
        "id": "airtable",
        "label": "Airtable",
        "description": "Airtableベースのレコード閲覧/更新用。初期状態は無効。",
        "enabled": False,
        "auth_modes": ["token_future", "oauth_future"],
        "scopes": ["read", "write"],
        "actions": {
            "list_records": {"side_effect": "read", "enabled": False, "params_schema": {"base_id": "string", "table": "string"}},
            "update_record": {"side_effect": "medium", "enabled": False, "params_schema": {"base_id": "string", "table": "string", "record_id": "string", "fields": "object"}},
        },
    },
}


def list_connectors() -> list[Connector]:
    return [deepcopy(CONNECTORS[k]) for k in sorted(CONNECTORS)]


def get_connector(connector_id: str) -> Connector | None:
    item = CONNECTORS.get(connector_id)
    return deepcopy(item) if item else None


def split_action_name(name: str) -> tuple[str, str]:
    left, dot, right = (name or "").partition(".")
    if not dot or not left or not right:
        raise ValueError("action name must be '<connector>.<action>'")
    return left, right
