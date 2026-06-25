from fastapi import HTTPException

from app.connectors.router import _render_path, _split_action_name, _validate_url
from app.workers.reviewer import _static_findings


def test_split_action_name():
    assert _split_action_name("my_api.list_items") == ("my_api", "list_items")


def test_render_path_requires_params():
    assert _render_path("/repos/{owner}/{repo}/issues", {"owner": "acme", "repo": "demo"}) == "/repos/acme/demo/issues"
    try:
        _render_path("/repos/{owner}/{repo}", {"owner": "acme"})
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "repo" in exc.detail
    else:
        raise AssertionError("HTTPException was not raised")


def test_validate_url_allows_https_and_localhost_only():
    assert _validate_url("https://api.example.com/") == "https://api.example.com"
    assert _validate_url("http://localhost:8080") == "http://localhost:8080"
    try:
        _validate_url("http://example.com")
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("HTTPException was not raised")


def test_reviewer_allows_connector_bridge_but_rejects_fetch():
    manifest = {
        "feature": "custom_api_viewer",
        "kind": "app",
        "theme": "default",
        "html": (
            "<!DOCTYPE html><html><head><meta name=\"viewport\"></head><body><script>"
            "AF.defineConnector({connector_id:'my_api',base_url:'https://api.example.com',actions:{list:{method:'GET',path:'/items'}}});"
            "AF.api('my_api.list',{limit:30}); window.applyAgentCommand=function(){};"
            "</script></body></html>"
        ),
        "commands": [],
    }
    assert not _static_findings(manifest)

    manifest["html"] = manifest["html"].replace("AF.api('my_api.list',{limit:30});", "fetch('https://example.com');")
    assert any("fetch" in finding for finding in _static_findings(manifest))
