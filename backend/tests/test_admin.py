"""Auth/admin tests (Firestore-free). Prod-default is closed without a token."""
from fastapi.testclient import TestClient

from app.auth import _split, admin_emails
from app.main import app

client = TestClient(app)


def test_me_requires_login_by_default():
    r = client.get("/api/me")
    assert r.status_code == 401


def test_admin_config_requires_admin():
    assert client.get("/api/admin/config").status_code == 401


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
