"""Specialist Worker posts a 'what I did' report line (pure)."""
from app.generated_app.features import _work_report


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
