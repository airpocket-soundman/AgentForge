"""Safety Harness unit tests (pure deterministic path)."""

from app.safety_harness import service


_HTML = (
    "<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>"
    "<button>clear</button>"
    "<script>AF.load().then(function(){});AF.save({items:[]});"
    "window.applyAgentCommand=function(name,args){};</script>"
    "</body></html>"
)


def _manifest(**over):
    m = {
        "kind": "app",
        "feature": "safe_app",
        "title": "安全なアプリ",
        "theme": "default",
        "html": _HTML,
        "commands": [{"name": "clear", "description": "clear", "inputSchema": {"type": "object"}}],
        "worker_state_mode": "hybrid",
        "state_schema": {"type": "object", "properties": {"items": {"type": "array"}}},
        "worker_eval_cases": [{"input": "全部消して", "expected": "confirm destructive action"}],
        "clarification_policy": "対象が曖昧なら確認する",
        "dangerous_action_policy": "削除や初期化は確認する",
    }
    m.update(over)
    return m


def test_safety_harness_passes_clean_manifest():
    result = service.evaluate(
        _manifest(),
        tester_result={"verdict": "pass"},
        reviewer_result={"verdict": "ok"},
        persist=False,
    )
    assert result["verdict"] == "pass"
    assert result["findings"] == []


def test_safety_harness_blocks_forbidden_runtime_api():
    html = _HTML.replace("window.applyAgentCommand", "window.open('/x');window.applyAgentCommand")
    result = service.evaluate(
        _manifest(html=html),
        tester_result={"verdict": "pass"},
        reviewer_result={"verdict": "ok"},
        persist=False,
    )
    assert result["verdict"] == "fail"
    assert any("window.open" in f for f in result["findings"])


def test_safety_harness_combines_tester_and_reviewer_verdicts():
    result = service.evaluate(
        _manifest(),
        tester_result={"verdict": "fail"},
        reviewer_result={"verdict": "ok"},
        persist=False,
    )
    assert result["verdict"] == "fail"
    assert "Tester gate failed" in result["findings"]

