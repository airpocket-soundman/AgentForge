"""Access control: identity, user allowlist, and the (separate) admin role.

Two isolated whitelists:
- USER allowlist  = env ALLOWED_EMAILS  ∪  Firestore admin_config/allowlist
  (the admin page edits the Firestore part at runtime). Gates app usage.
- ADMIN allowlist = env ADMIN_EMAILS (default: the owner only). Gates the admin
  page + allowlist/feature-flag editing. Admins are always allowed into the app.

Modes:
- Local dev (app_env=local): open. Identity = ("local", admin=True) so everything,
  including the admin page, is reachable without auth.
- Prod: closed by default. A verified Firebase ID token is required, and the
  caller must be on the user allowlist or admin list.
- Optional contest/demo guest access can be enabled by env. Guests are users,
  never admins, and still go through the normal app routers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from app.config import get_settings


@dataclass
class CurrentUser:
    uid: str
    email: str
    is_admin: bool


def _split(raw: str) -> list[str]:
    return [e.strip().lower() for e in re.split(r"[;,\s]+", raw or "") if e.strip()]


def admin_emails() -> list[str]:
    return _split(get_settings().admin_emails)


def stored_allowlist() -> list[str]:
    """Admin-editable user allowlist (Firestore admin_config/allowlist). [] on error."""
    try:
        from app.firestore import get_db

        snap = get_db().collection("admin_config").document("allowlist").get()
        if snap.exists:
            return [str(e).strip().lower() for e in (snap.to_dict().get("emails") or [])]
    except Exception:  # noqa: BLE001 — Firestore unavailable -> fall back to env/admin
        pass
    return []


def effective_allowed_emails() -> list[str]:
    s = get_settings()
    return sorted(set(_split(s.allowed_emails)) | set(admin_emails()) | set(stored_allowlist()))


def _is_local_mode() -> bool:
    return get_settings().is_local


def _verify(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="ログインが必要です")
    token = authorization.split(" ", 1)[1].strip()
    try:
        from google.auth.transport import requests as ga_requests
        from google.oauth2 import id_token

        claims = id_token.verify_firebase_token(
            token, ga_requests.Request(), audience=get_settings().google_cloud_project
        )
    except Exception:  # noqa: BLE001 — any verification failure -> unauthorized
        raise HTTPException(status_code=401, detail="認証トークンが無効です")
    if not claims:
        raise HTTPException(status_code=401, detail="認証トークンが無効です")
    return claims


def current_user(
    authorization: str | None = Header(default=None),
    guest_header: str | None = Header(default=None, alias="X-AgentForge-Guest"),
) -> CurrentUser:
    """Resolve the caller. Raises 401 (no/invalid token) / 403 (not allowlisted)."""
    if _is_local_mode():
        return CurrentUser(uid="local", email="local@dev", is_admin=True)

    s = get_settings()
    if s.guest_access_enabled and (guest_header or "").strip().lower() == "1":
        return CurrentUser(uid="guest", email=s.guest_email.lower(), is_admin=False)

    if not authorization:
        raise HTTPException(status_code=401, detail="ログインが必要です")

    claims = _verify(authorization)
    email = (claims.get("email") or "").lower()
    uid = claims.get("user_id") or claims.get("sub") or email or "anon"
    is_admin = email in admin_emails()
    if not is_admin:
        allowed = set(_split(s.allowed_emails)) | set(stored_allowlist())
        if email not in allowed:
            raise HTTPException(status_code=403, detail="このアカウントはアクセスを許可されていません")
    return CurrentUser(uid=uid, email=email, is_admin=is_admin)


def require_admin(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="管理者のみがアクセスできます")
    return user


# Backward-compatible guard name used by main.py / routers (return value ignored).
require_allowed_user = current_user
