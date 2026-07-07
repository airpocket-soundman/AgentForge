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


def test_guest_requires_feature_flag(monkeypatch):
    monkeypatch.setenv("GUEST_ACCESS_ENABLED", "false")
    monkeypatch.setenv("ALLOWED_EMAILS", "")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.auth._verify",
        lambda _authorization: {"email": "judge@example.com", "user_id": "judge-uid"},
    )
    r = client.get("/api/me", headers={"Authorization": "Bearer test"})
    assert r.status_code == 403
    get_settings.cache_clear()


def test_guest_mode_allows_google_user_with_separate_project(monkeypatch):
    monkeypatch.setenv("GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("ALLOWED_EMAILS", "")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.auth._verify",
        lambda _authorization: {"email": "judge@example.com", "user_id": "judge-uid"},
    )
    r = client.get("/api/me", headers={"Authorization": "Bearer test"})
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "judge@example.com"
    assert data["is_admin"] is False
    assert data["is_guest"] is True
    assert data["project_id"] == "guest_judge-uid"
    assert client.get("/api/admin/config", headers={"Authorization": "Bearer test"}).status_code == 403
    get_settings.cache_clear()


def test_guest_mode_allows_named_guest_without_google(monkeypatch):
    monkeypatch.setenv("GUEST_ACCESS_ENABLED", "true")
    get_settings.cache_clear()
    r = client.get(
        "/api/me",
        headers={
            "X-AgentForge-Guest-Id": "judge_sample",
            "X-AgentForge-Guest-Name": "Judge A",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "Judge A (guest)"
    assert data["is_admin"] is False
    assert data["is_guest"] is True
    assert data["project_id"] == "guest_judge_sample"
    assert client.get(
        "/api/admin/config",
        headers={
            "X-AgentForge-Guest-Id": "judge_sample",
            "X-AgentForge-Guest-Name": "Judge A",
        },
    ).status_code == 403
    get_settings.cache_clear()


def test_admin_routes_registered():
    paths = {r.path for r in app.routes}
    assert {
        "/api/me",
        "/api/public/config",
        "/api/admin/config",
        "/api/admin/allowlist",
        "/api/admin/feature-flags",
    } <= paths


def test_admin_emails_default_and_split():
    assert "yamashita.3154@gmail.com" in admin_emails()
    assert _split("a@b.com; c@d.com  e@f.com") == ["a@b.com", "c@d.com", "e@f.com"]
