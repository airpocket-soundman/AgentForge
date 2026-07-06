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


def test_safety_harness_blocks_connector_secret_in_state_schema():
    result = service.evaluate(
        _manifest(
            html=_HTML.replace("AF.load()", "AF.defineConnector({});AF.load()"),
            state_schema={
                "type": "object",
                "properties": {
                    "connection": {
                        "type": "object",
                        "properties": {"password": {"type": "string"}, "baseUrl": {"type": "string"}},
                    }
                },
            },
        ),
        tester_result={"verdict": "pass"},
        reviewer_result={"verdict": "ok"},
        persist=False,
    )
    assert result["verdict"] == "fail"
    assert any("state_schema" in f and "password" in f for f in result["findings"])


def test_safety_harness_requires_body_template_for_password_session_flow():
    html = (
        "<!DOCTYPE html><html><body><script>"
        "AF.defineConnector({connector_id:'login',base_url:'https://bsky.social/xrpc',"
        "auth:{type:'basic',username:'u',password:'p'},"
        "actions:{create_session:{method:'POST',path:'/com.atproto.server.createSession'}}});"
        "AF.api('login.create_session',{identifier:'u'});window.applyAgentCommand=function(){};"
        "</script></body></html>"
    )
    result = service.evaluate(
        _manifest(html=html, worker_state_mode="commands", state_schema={}, commands=[]),
        tester_result={"verdict": "pass"},
        reviewer_result={"verdict": "ok"},
        persist=False,
    )
    assert result["verdict"] == "fail"
    assert any("body_template" in f for f in result["findings"])


def test_safety_harness_blocks_connector_inner_html_without_escape():
    html = (
        "<!DOCTYPE html><html><body><div id='feed'></div><script>"
        "AF.defineConnector({connector_id:'feed',base_url:'https://api.example.com',actions:{list:{method:'GET',path:'/items'}}});"
        "async function render(){const res=await AF.api('feed.list',{});"
        "document.getElementById('feed').innerHTML=`<p>${String(res.text)}</p>`;}"
        "window.applyAgentCommand=function(){};"
        "</script></body></html>"
    )
    result = service.evaluate(
        _manifest(html=html, worker_state_mode="commands", state_schema={}, commands=[]),
        tester_result={"verdict": "pass"},
        reviewer_result={"verdict": "ok"},
        persist=False,
    )
    assert result["verdict"] == "fail"
    assert any("innerHTML" in f for f in result["findings"])


def test_safety_harness_blocks_variable_external_src_from_connector():
    html = (
        "<!DOCTYPE html><html><body><div id='feed'></div><script>"
        "AF.defineConnector({connector_id:'feed',base_url:'https://api.example.com',actions:{list:{method:'GET',path:'/items'}}});"
        "async function render(){const res=await AF.api('feed.list',{});"
        "const thumb=res.thumb; document.getElementById('feed').innerHTML=`<img src=\"${thumb}\">`;}"
        "window.applyAgentCommand=function(){};"
        "</script></body></html>"
    )
    result = service.evaluate(
        _manifest(html=html, worker_state_mode="commands", state_schema={}, commands=[]),
        tester_result={"verdict": "pass"},
        reviewer_result={"verdict": "ok"},
        persist=False,
    )
    assert result["verdict"] == "fail"
    assert any("img/src" in f for f in result["findings"])
