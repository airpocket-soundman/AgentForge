"""Route-registration + Firestore-free health tests for Phase 4 modules.

The full approval -> active -> CRUD -> rollback flow is verified by the
docker-compose integration loop (it needs the Firestore emulator).
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_control_plane_health():
    assert client.get("/api/control-plane/health").json()["module"] == "control_plane"


def test_expected_routes_registered():
    paths = {r.path for r in app.routes}
    assert "/api/reception/messages" in paths
    assert "/api/orchestrator/plan" in paths
    assert "/api/control-plane/approvals/{approval_id}/approve" in paths
    assert "/api/control-plane/features/{project_id}/{feature}/disable" in paths
    assert "/api/app/tasks" in paths
