"""Unit tests for Reception logic that needs no Firestore (pure functions) plus a
health-endpoint smoke test. Run from backend/:  pytest

The /messages endpoint is covered by the docker-compose integration loop
(it requires the Firestore emulator), not here.
"""
from fastapi.testclient import TestClient

from app.main import app
from app.reception import service

client = TestClient(app)


def test_health_endpoints():
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/reception/health").status_code == 401


def test_detect_intent_task():
    assert service.detect_intent("タスク管理を追加して") == "build_feature:task"
    assert service.detect_intent("PDFのメモ機能をつくって") == "build_feature:pdf_memo"


def test_detect_intent_none_without_build_keyword():
    assert service.detect_intent("こんにちは") is None
    assert service.detect_intent("今日の天気は？") is None


def test_compose_reply_mentions_feature_label():
    reply = service.compose_reply("タスク管理を追加して", "build_feature:task")
    assert "タスク管理" in reply


def test_classify_conversational_control():
    assert service.classify("反映して") == "approve"
    assert service.classify("承認します") == "approve"
    assert service.classify("戻して") == "rollback"
    assert service.classify("ロールバックして") == "rollback"
    assert service.classify("タスク管理を追加して") == "build_feature:task"
    assert service.classify("こんにちは") == "chat"
    # A build request that incidentally mentions a control word (戻す) must still
    # be treated as a build, not a rollback.
    assert service.classify("お絵描きツールを作って。元に戻すボタンも") == "build_feature:unknown"


def test_flow_record_clears_transient_template_fields():
    flow = service._flow_record({
        "stage": "confirm",
        "mode": "create",
        "goal": "テトリス作って",
        "feature": None,
    })
    assert flow["template"] is None
    assert flow["pending_images"] is None


def test_resolve_feature_delete_accepts_slug_without_scope(monkeypatch):
    monkeypatch.setattr(
        service,
        "_active_features",
        lambda _project_id: {
            "task_manager": "active",
            "task_manager_title": "task_manager",
            "schedule": "active",
            "schedule_title": "スケジュール",
        },
    )
    assert service.resolve_feature_delete("default", "task_managerを削除してください") == "task_manager"


def test_resolve_feature_delete_accepts_template_name_with_app_scope(monkeypatch):
    monkeypatch.setattr(
        service,
        "_active_features",
        lambda _project_id: {
            "task_manager": "active",
            "task_manager_title": "task_manager",
            "schedule": "active",
            "schedule_title": "スケジュール",
        },
    )
    assert service.resolve_feature_delete("default", "タスク管理アプリを削除してください") == "task_manager"
    assert service.resolve_feature_delete("default", "タスク管理を削除してください") is None
    assert service.resolve_feature_delete("default", "予定を削除してください") is None
