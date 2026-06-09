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
    assert client.get("/api/reception/health").json()["module"] == "reception"


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
