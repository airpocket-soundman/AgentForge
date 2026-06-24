"""Admin module: identity (/api/me) + admin-only config (allowlist, feature flags).

Isolated from user data: admin endpoints require the (separate) admin allowlist.
The user allowlist and feature flags live in Firestore `admin_config/*` so the
owner can edit them at runtime from the admin page.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import (
    CurrentUser,
    admin_emails,
    current_user,
    effective_allowed_emails,
    guest_access_enabled,
    require_admin,
    stored_allowlist,
)
from app.config import get_settings
from app.control_plane.registry import _audit
from app.firestore import get_db

router = APIRouter(prefix="/api", tags=["admin"])

# Feature flags the admin can toggle.
_FLAG_DEFAULTS: dict[str, bool] = {"byok_visible": False, "guest_access_enabled": False}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_feature_flags() -> dict:
    try:
        snap = get_db().collection("admin_config").document("feature_flags").get()
        data = snap.to_dict() if snap.exists else {}
    except Exception:  # noqa: BLE001 — Firestore unavailable -> defaults
        data = {}
    flags = {**_FLAG_DEFAULTS, **{k: bool(v) for k, v in (data or {}).items() if k in _FLAG_DEFAULTS}}
    flags["guest_access_enabled"] = guest_access_enabled()
    return flags


class AllowlistIn(BaseModel):
    emails: list[str] = []


class FeatureFlagsIn(BaseModel):
    byok_visible: bool | None = None
    guest_access_enabled: bool | None = None


@router.get("/public/config")
def public_config() -> dict:
    """Unauthenticated browser bootstrap settings."""
    return {"guest_access_enabled": guest_access_enabled(), "auth_required": not get_settings().is_local}


@router.get("/me")
def me(user: CurrentUser = Depends(current_user)) -> dict:
    """Who am I + what features are on (drives the SPA's conditional UI)."""
    return {
        "uid": user.uid,
        "email": user.email,
        "is_admin": user.is_admin,
        "is_guest": user.is_guest,
        "project_id": user.project_id,
        "feature_flags": get_feature_flags(),
    }


@router.get("/admin/config")
def admin_config(_: CurrentUser = Depends(require_admin)) -> dict:
    return {
        "allowlist_editable": stored_allowlist(),       # Firestore part (editable)
        "allowlist_effective": effective_allowed_emails(),  # env ∪ admin ∪ stored
        "admin_emails": admin_emails(),                 # read-only (env)
        "feature_flags": get_feature_flags(),
    }


@router.post("/admin/allowlist")
def set_allowlist(body: AllowlistIn, _: CurrentUser = Depends(require_admin)) -> dict:
    emails = sorted({e.strip().lower() for e in body.emails if e.strip()})
    get_db().collection("admin_config").document("allowlist").set(
        {"emails": emails, "updated_at": _now_iso()}
    )
    _audit("admin.allowlist_updated", "admin_config:allowlist", {"emails": emails, "count": len(emails)})
    return {"emails": emails}


@router.post("/admin/feature-flags")
def set_feature_flags(body: FeatureFlagsIn, _: CurrentUser = Depends(require_admin)) -> dict:
    update = {k: bool(v) for k, v in body.model_dump().items() if k in _FLAG_DEFAULTS and v is not None}
    if update:
        update["updated_at"] = _now_iso()
        get_db().collection("admin_config").document("feature_flags").set(update, merge=True)
        _audit("admin.feature_flags_updated", "admin_config:feature_flags", {"flags": update})
    return get_feature_flags()
