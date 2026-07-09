"""Unit tests for Reception logic that needs no Firestore (pure functions) plus a
health-endpoint smoke test. Run from backend/:  pytest

The /messages endpoint is covered by the docker-compose integration loop
(it requires the Firestore emulator), not here.
"""
from fastapi.testclient import TestClient
from contextlib import nullcontext
from types import SimpleNamespace

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


def test_default_template_create_key_catches_schedule_before_llm():
    assert service.default_template_create_key("スケジュールを作って") == "schedule"
    assert service.default_template_create_key("予定表を作って") == "schedule"
    assert service.default_template_create_key("家計簿がほしい") == "household_budget"
    assert service.default_template_create_key("スケジュールはデフォルトではありませんか") is None
    assert service.default_template_create_key("デフォルトではなくスケジュールを一から作って") is None


def test_keyword_pre_gates_removed_from_reception():
    """Question/investigation routing is the LLM classifier's job (with context),
    not a Receptor-side word list. The light `classify` keeps only explicit
    control commands deterministic; everything else flows to classify_request."""
    assert not hasattr(service, "is_receptor_direct_question")
    assert not hasattr(service, "is_investigation_request")
    assert not hasattr(service, "mentions_active_feature")
    # These non-control texts still reach the background classifier (chat intent
    # for the light classifier means "no deterministic control command").
    assert service.classify("Blueskyアプリで接続に失敗するので原因を確認してください") == "chat"
    assert service.classify("SNSアプリの世間一般の仕様やUI事例について相談したい") == "chat"


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


def test_flow_record_needs_regeneration_defaults_false_and_resets():
    # Default: a fresh plan/confirm never carries the flag.
    flow = service._flow_record({"stage": "plan", "goal": "g", "plan": {}})
    assert flow["needs_regeneration"] is False
    assert flow["gate_feedbacks"] == []
    # Set explicitly only by the gate-failed codegen path.
    flow = service._flow_record({"stage": "plan", "needs_regeneration": True, "gate_feedbacks": ["[規約] x"]})
    assert flow["needs_regeneration"] is True
    assert flow["gate_feedbacks"] == ["[規約] x"]


def test_gate_feedback_history_deduplicates_and_combines():
    merged = service._merge_gate_feedbacks(["[規約] x", "[動作] y"], "[規約] x")
    assert merged == ["[規約] x", "[動作] y"]
    merged = service._merge_gate_feedbacks(merged, "[安全] z")
    combined = service._combined_gate_feedback(merged)
    assert combined is not None
    assert "[過去の未通過フィードバック]" in combined
    assert "[動作] y" in combined
    assert "[安全] z" in combined


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


def test_resolve_feature_deletes_returns_multiple_targets(monkeypatch):
    monkeypatch.setattr(
        service,
        "_active_features",
        lambda _project_id: {
            "retouch": "active",
            "retouch_title": "レタッチスタジオ",
            "paint": "active",
            "paint_title": "ペイント",
            "schedule": "active",
            "schedule_title": "スケジュール",
        },
    )

    targets = service.resolve_feature_deletes("default", "レタッチスタジオとペイントを削除して")

    assert targets == ["retouch", "paint"]
    assert service.resolve_feature_delete("default", "レタッチスタジオとペイントを削除して") == "retouch"


def test_delete_flow_record_keeps_multiple_targets():
    flow = service._flow_record({
        "stage": "confirm",
        "mode": "delete",
        "feature": "retouch",
        "features": ["retouch", "paint"],
    })

    assert flow["feature"] == "retouch"
    assert flow["features"] == ["retouch", "paint"]


def test_delete_confirmation_is_exact_match_only():
    assert service.delete_confirmed("削除する")
    assert service.delete_confirmed("完全に削除")
    assert service.delete_confirmed("はい")
    assert not service.delete_confirmed("データを残す")
    assert not service.delete_confirmed("巻き戻し可能")
    # Substrings must never confirm a destructive action.
    assert not service.delete_confirmed("全部残しておいて")
    assert not service.delete_confirmed("完全に削除しないで")
    assert not service.delete_confirmed("データも残せますか")


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


def test_deploy_template_repairs_failed_gate_before_registering(monkeypatch):
    class FakeManifest:
        feature = "bluesky"
        title = "Bluesky"
        theme = "ocean"
        description = "default bluesky"

        def __init__(self, repaired: bool = False):
            self.repaired = repaired

        def model_dump(self, mode="json"):
            return {
                "feature": self.feature,
                "title": self.title,
                "theme": self.theme,
                "description": self.description,
                "html": "repaired" if self.repaired else "broken",
            }

    class FakeDoc:
        exists = False

        def to_dict(self):
            return {}

    class FakeCollection:
        def document(self, _name):
            return SimpleNamespace(get=lambda: FakeDoc())

    class FakeDb:
        def collection(self, _name):
            return FakeCollection()

    gate_calls = []

    def fake_run_gates(_conversation_id, _goal, manifest, _corr, **_kwargs):
        gate_calls.append(manifest["html"])
        if manifest["html"] == "broken":
            return False, {
                "tester": {"verdict": "pass", "errors": []},
                "reviewer": {"verdict": "needs_revision", "findings": ["fix me"]},
                "safety": {"verdict": "fail", "findings": ["unsafe"]},
            }
        return True, {
            "tester": {"verdict": "pass", "errors": []},
            "reviewer": {"verdict": "ok", "findings": []},
            "safety": {"verdict": "pass", "findings": []},
        }

    registered = {}

    monkeypatch.setattr(service, "get_db", lambda: FakeDb())
    monkeypatch.setattr(service, "append_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_set_flow", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_set_build", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_progress", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_llm_heartbeat", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(service, "_run_gates", fake_run_gates)
    monkeypatch.setattr(service.worker_status, "record_status", lambda *_args, **_kwargs: None)

    from app import templates
    from app.llm import gateway
    from app.orchestrator import service as orchestrator
    from app.workers import ui_designer

    monkeypatch.setattr(templates, "to_manifest", lambda _key: FakeManifest(False))
    monkeypatch.setattr(gateway, "get_llm", lambda: SimpleNamespace(enabled=True))
    monkeypatch.setattr(ui_designer, "design_patch", lambda *_args, **_kwargs: FakeManifest(True))

    def fake_register_app(_req, manifest, **_kwargs):
        registered["html"] = manifest.model_dump()["html"]
        return SimpleNamespace(plan=SimpleNamespace(feature="bluesky"), approval_id="approval_1")

    monkeypatch.setattr(orchestrator, "register_app", fake_register_app)

    res = service.deploy_template("p", "bluesky", "blueskyアプリを作って")

    assert res["building"] is False
    assert registered["html"] == "repaired"
    assert gate_calls == ["broken", "repaired"]
