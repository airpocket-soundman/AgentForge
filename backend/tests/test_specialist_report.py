"""Specialist Worker posts a 'what I did' report line (pure)."""
from app.generated_app.features import _chat_doc_id, _context_id, _work_report


def test_tool_command_report():
    m = _work_report({"name": "add_item", "arguments": {"text": "牛乳", "qty": 2}}, [])
    assert m and m.role == "system" and "add_item" in m.text and "🔧" in m.text


def test_data_change_report_counts_ops():
    m = _work_report(None, [{"op": "create"}, {"op": "create"}, {"op": "update"}])
    assert m and "作成2件" in m.text and "更新1件" in m.text


def test_data_change_report_generic_when_no_op():
    m = _work_report(None, [{"task_id": "t1"}, {"task_id": "t2"}])
    assert m and "2件" in m.text


def test_no_report_for_pure_chat():
    assert _work_report(None, []) is None
    assert _work_report({}, None) is None


def test_worker_context_doc_id_is_feature_and_context_scoped():
    assert _context_id("settings") == "settings"
    assert _context_id("詳細 123") == "123"
    assert _chat_doc_id("p1", "paint", "settings") == "p1_paint_settings"
    assert _chat_doc_id("p1", "paint", "") == "p1_paint_default"
