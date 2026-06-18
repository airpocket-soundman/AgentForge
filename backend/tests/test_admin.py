"""Auth/admin tests (Firestore-free). Prod-default is closed without a token."""
from fastapi.testclient import TestClient

from app.auth import _split, admin_emails
from app.config import get_settings
from app.main import app

client = TestClient(app)


def test_me_requires_login_by_default():
    r = client.get("/api/me")
    assert r.status_code == 401


def test_admin_config_requires_admin():
    assert client.get("/api/admin/config").status_code == 401


def test_guest_header_requires_feature_flag(monkeypatch):
    monkeypatch.setenv("GUEST_ACCESS_ENABLED", "false")
    get_settings.cache_clear()
    assert client.get("/api/me", headers={"X-AgentForge-Guest": "1"}).status_code == 401
    get_settings.cache_clear()


def test_guest_header_allows_non_admin_user(monkeypatch):
    monkeypatch.setenv("GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("GUEST_EMAIL", "judge@example.com")
    get_settings.cache_clear()
    r = client.get("/api/me", headers={"X-AgentForge-Guest": "1"})
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "judge@example.com"
    assert data["is_admin"] is False
    assert client.get("/api/admin/config", headers={"X-AgentForge-Guest": "1"}).status_code == 403
    get_settings.cache_clear()


def test_admin_routes_registered():
    paths = {r.path for r in app.routes}
    assert {
        "/api/me",
        "/api/admin/config",
        "/api/admin/allowlist",
        "/api/admin/feature-flags",
    } <= paths


def test_admin_emails_default_and_split():
    assert "yamashita.3154@gmail.com" in admin_emails()
    assert _split("a@b.com; c@d.com  e@f.com") == ["a@b.com", "c@d.com", "e@f.com"]
