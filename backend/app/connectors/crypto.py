"""Encryption helpers for user-managed connector credentials."""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class CredentialCryptoError(Exception):
    """Raised when credentials cannot be encrypted or decrypted safely."""


def _fernet() -> Fernet:
    secret = (get_settings().connector_credentials_key or "").strip()
    if not secret:
        raise CredentialCryptoError("CONNECTOR_CREDENTIALS_KEY が未設定です")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_credentials(credentials: dict[str, Any]) -> dict[str, str]:
    payload = json.dumps(credentials, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "scheme": "fernet:v1",
        "ciphertext": _fernet().encrypt(payload).decode("ascii"),
    }


def decrypt_credentials(encrypted: dict[str, Any]) -> dict[str, Any]:
    if encrypted.get("scheme") != "fernet:v1":
        raise CredentialCryptoError("未対応の認証情報暗号化形式です")
    ciphertext = str(encrypted.get("ciphertext") or "")
    if not ciphertext:
        raise CredentialCryptoError("認証情報の暗号文が空です")
    try:
        payload = _fernet().decrypt(ciphertext.encode("ascii"))
        decoded = json.loads(payload.decode("utf-8"))
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise CredentialCryptoError("認証情報を復号できません") from exc
    if not isinstance(decoded, dict):
        raise CredentialCryptoError("認証情報の形式が不正です")
    return decoded


def extract_credentials(state: dict[str, Any] | None) -> dict[str, Any]:
    """Return decrypted credentials, with legacy plaintext read compatibility."""
    if not state:
        return {}
    encrypted = state.get("encrypted_credential")
    if isinstance(encrypted, dict):
        return decrypt_credentials(encrypted)
    legacy = state.get("credential")
    return legacy if isinstance(legacy, dict) else {}
