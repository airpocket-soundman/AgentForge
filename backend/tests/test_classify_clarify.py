"""Receptor judgement: feasibility questions stay in chat (clarify) and are NOT
dispatched to the Orchestrator; only concrete, actionable asks dispatch.
Tests the deterministic stub (no LLM/Firestore)."""
from app.orchestrator.service import _classify_stub

ACTIVES = {"task": "タスク管理"}


def test_feasibility_question_is_chat_even_with_feature_and_edit_word():
    # "変更できますか？" is a question, not "変更して" — must NOT dispatch as edit.
    r = _classify_stub("タスク管理の機能変更できますか？", ACTIVES, None)
    assert r["action"] == "chat"


def test_plain_capability_question_is_chat():
    assert _classify_stub("どんなことができますか？", {}, None)["action"] == "chat"
    assert _classify_stub("使い方を教えて", ACTIVES, None)["action"] == "chat"


def test_concrete_edit_dispatches():
    r = _classify_stub("タスク管理に期限の色分けを追加して", ACTIVES, None)
    assert r["action"] == "edit" and r["feature"] == "task"


def test_concrete_create_dispatches():
    assert _classify_stub("ストップウォッチを作って", {}, None)["action"] == "create"


def test_bare_feature_mention_without_instruction_is_not_edit():
    # Mentioning the feature name alone shouldn't trigger a build.
    assert _classify_stub("タスク管理について", ACTIVES, None)["action"] == "chat"
