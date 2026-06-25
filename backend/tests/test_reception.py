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


def test_connection_failure_investigation_stays_with_receptor():
    text = "Blueskyアプリで接続に失敗するので原因を確認してください"
    assert service.is_receptor_direct_question(text)
    assert service.classify(text) == "chat"


def test_general_app_spec_consultation_stays_with_receptor():
    text = "SNSアプリの世間一般の仕様やUI事例について相談したい"
    assert service.is_receptor_direct_question(text)
    assert service.classify(text) == "chat"


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


def test_handle_request_restrict_feature_blocks_other_app_edit(monkeypatch):
    from app.orchestrator import service as orchestrator

    monkeypatch.setattr(
        orchestrator,
        "classify_request",
        lambda *_args, **_kwargs: {"action": "edit", "feature": "other_app", "context_note": ""},
    )

    res = service.handle_request("default", "別アプリを直して", hint_feature="my_app", restrict_feature="my_app")

    assert res["action"] == "out_of_scope"
    assert res["feature"] == "other_app"
    assert res["restricted_to"] == "my_app"


def test_handle_request_restrict_feature_blocks_new_app_create(monkeypatch):
    from app.orchestrator import service as orchestrator

    monkeypatch.setattr(
        orchestrator,
        "classify_request",
        lambda *_args, **_kwargs: {"action": "create", "feature": "", "context_note": ""},
    )

    res = service.handle_request("default", "新しいアプリを作って", hint_feature="my_app", restrict_feature="my_app")

    assert res["action"] == "out_of_scope"
    assert res["restricted_to"] == "my_app"
