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

from app.audit_context import set_actor_context
from app.config import get_settings


@dataclass
class CurrentUser:
    uid: str
    email: str
    is_admin: bool
    is_guest: bool = False

    @property
    def project_id(self) -> str:
        if not self.is_guest:
            return "default"
        safe_uid = re.sub(r"[^a-zA-Z0-9_-]+", "_", self.uid).strip("_") or "guest"
        return f"guest_{safe_uid[:80]}"


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


def guest_access_enabled() -> bool:
    """Runtime guest access switch. Firestore overrides env when explicitly set."""
    s = get_settings()
    try:
        from app.firestore import get_db

        snap = get_db().collection("admin_config").document("feature_flags").get()
        if snap.exists:
            data = snap.to_dict() or {}
            if "guest_access_enabled" in data:
                return bool(data.get("guest_access_enabled"))
    except Exception:  # noqa: BLE001 — Firestore unavailable -> fall back to env
        pass
    return bool(s.guest_access_enabled)


def _is_local_mode() -> bool:
    return get_settings().is_local


def _guest_user_from_headers(guest_id: str | None, guest_name: str | None) -> CurrentUser | None:
    if not guest_access_enabled():
        return None
    raw_id = (guest_id or "").strip()
    raw_name = (guest_name or "").strip()
    if not raw_id or not raw_name:
        return None
    safe_uid = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw_id).strip("_")[:80]
    safe_name = re.sub(r"[\r\n\t]+", " ", raw_name).strip()[:40]
    if not safe_uid or not safe_name:
        return None
    return CurrentUser(uid=safe_uid, email=f"{safe_name} (guest)", is_admin=False, is_guest=True)


def _with_audit_actor(user: CurrentUser) -> CurrentUser:
    set_actor_context(
        uid=user.uid,
        email=user.email,
        is_admin=user.is_admin,
        is_guest=user.is_guest,
    )
    return user


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
    x_agentforge_guest_id: str | None = Header(default=None, alias="X-AgentForge-Guest-Id"),
    x_agentforge_guest_name: str | None = Header(default=None, alias="X-AgentForge-Guest-Name"),
) -> CurrentUser:
    """Resolve the caller. Raises 401 (no/invalid token) / 403 (not allowlisted)."""
    if _is_local_mode():
        return _with_audit_actor(CurrentUser(uid="local", email="local@dev", is_admin=True))

    s = get_settings()
    if not authorization:
        guest = _guest_user_from_headers(x_agentforge_guest_id, x_agentforge_guest_name)
        if guest:
            return _with_audit_actor(guest)
        raise HTTPException(status_code=401, detail="ログインが必要です")

    claims = _verify(authorization)
    email = (claims.get("email") or "").lower()
    uid = claims.get("user_id") or claims.get("sub") or email or "anon"
    is_admin = email in admin_emails()
    if not is_admin:
        allowed = set(_split(s.allowed_emails)) | set(stored_allowlist())
        if email not in allowed:
            if guest_access_enabled():
                return _with_audit_actor(CurrentUser(uid=uid, email=email, is_admin=False, is_guest=True))
            raise HTTPException(status_code=403, detail="このアカウントはアクセスを許可されていません")
    return _with_audit_actor(CurrentUser(uid=uid, email=email, is_admin=is_admin))


def require_admin(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="管理者のみがアクセスできます")
    return user


def require_project_access(user: CurrentUser, project_id: str) -> None:
    """Guests are locked to their own project scope; allowed users keep legacy default."""
    if user.is_guest and project_id != user.project_id:
        raise HTTPException(status_code=403, detail="このゲスト環境にはアクセスできません")


# Backward-compatible guard name used by main.py / routers (return value ignored).
require_allowed_user = current_user
