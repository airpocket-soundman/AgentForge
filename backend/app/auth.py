"""Access control: verify the caller's Firebase ID token and enforce an email
allowlist.

Enforcement is OFF when ALLOWED_EMAILS is empty (local dev / open). In prod, set
ALLOWED_EMAILS so only listed accounts can use the app — others get 403 even after
a successful Google sign-in (Firebase login itself can't be prevented, but the API
and UI deny access).
"""
from fastapi import Header, HTTPException

from app.config import get_settings


def require_allowed_user(authorization: str | None = Header(default=None)) -> str | None:
    settings = get_settings()
    allowed = settings.allowed_email_list
    if not allowed:
        return None  # enforcement disabled (no allowlist configured)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="ログインが必要です")
    token = authorization.split(" ", 1)[1].strip()

    try:
        from google.auth.transport import requests as ga_requests
        from google.oauth2 import id_token

        claims = id_token.verify_firebase_token(
            token, ga_requests.Request(), audience=settings.google_cloud_project
        )
    except Exception:  # noqa: BLE001 — any verification failure -> unauthorized
        raise HTTPException(status_code=401, detail="認証トークンが無効です")

    email = (claims or {}).get("email", "").lower()
    if not email or email not in allowed:
        raise HTTPException(status_code=403, detail="このアカウントはアクセスを許可されていません")
    return email
