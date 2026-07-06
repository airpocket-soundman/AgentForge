from fastapi import HTTPException

from app.connectors.router import (
    _connector_response,
    _ensure_same_origin,
    _normalize_side_effect,
    _public_connector,
    _render_path,
    _resolve_template,
    _split_action_name,
    _validate_url,
)
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


def test_render_path_rejects_absolute_url_injection():
    # A whole-path parameter (e.g. "/{image_path}") must stay a path segment:
    # absolute / scheme-relative URLs would swap the host after urljoin (SSRF).
    for evil in ("https://evil.example/x", "//evil.example/x", "a\\..\\b"):
        try:
            _render_path("/{image_path}", {"image_path": evil})
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError(f"HTTPException was not raised for {evil!r}")
    # Normal nested CDN paths still render.
    assert _render_path("/{image_path}", {"image_path": "img/avatar/plain/did/abc@jpeg"}) == "/img/avatar/plain/did/abc@jpeg"


def test_ensure_same_origin_blocks_host_and_scheme_change():
    _ensure_same_origin("https://cdn.example.com", "https://cdn.example.com/img/a.jpg")
    for evil in ("https://evil.example/x", "http://cdn.example.com/x"):
        try:
            _ensure_same_origin("https://cdn.example.com", evil)
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError(f"HTTPException was not raised for {evil!r}")


def test_validate_url_allows_https_and_localhost_only():
    assert _validate_url("https://api.example.com/") == "https://api.example.com"
    assert _validate_url("http://localhost:8080") == "http://localhost:8080"
    try:
        _validate_url("http://example.com")
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("HTTPException was not raised")


def test_normalize_side_effect_maps_write_to_medium():
    assert _normalize_side_effect("write") == "medium"
    assert _normalize_side_effect("high") == "high"
    assert _normalize_side_effect("unexpected") == "read"


def test_public_connector_reports_none_auth_with_saved_secret_as_configured():
    public = _public_connector(
        {
            "connector_id": "bluesky_login",
            "auth": {"type": "none", "username": "alice.bsky.social", "password": "app-password"},
        }
    )
    assert public["auth"] == {"type": "none", "configured": True}


def test_resolve_template_can_inject_secret_into_body_without_exposing_it():
    template = {
        "identifier": "$params.identifier",
        "password": "$secret.password",
        "nested": {"token": "$auth.token"},
    }
    resolved = _resolve_template(
        template,
        params={"identifier": "user@example.com"},
        auth={"password": "app-password", "token": "access-token"},
    )
    assert resolved == {
        "identifier": "user@example.com",
        "password": "app-password",
        "nested": {"token": "access-token"},
    }


def test_resolve_template_rejects_missing_secret():
    try:
        _resolve_template({"password": "$secret.password"}, params={}, auth={})
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "password" in exc.detail
    else:
        raise AssertionError("HTTPException was not raised")


def test_connector_response_exposes_upstream_fields_and_data_wrapper():
    response = _connector_response(
        connector_id="login",
        action_id="create_session",
        data={"accessJwt": "jwt", "did": "did:example:123"},
    )
    assert response["ok"] is True
    assert response["connector"] == "login"
    assert response["data"] == {"accessJwt": "jwt", "did": "did:example:123"}
    assert response["accessJwt"] == "jwt"
    assert response["did"] == "did:example:123"


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


def test_reviewer_flags_password_session_without_body_template():
    manifest = {
        "feature": "bluesky_viewer",
        "kind": "app",
        "theme": "default",
        "html": (
            "<!DOCTYPE html><html><head><meta name=\"viewport\"></head><body><script>"
            "AF.defineConnector({connector_id:'login',base_url:'https://bsky.social/xrpc',"
            "auth:{type:'basic',username:'u',password:'p'},"
            "actions:{create_session:{method:'POST',path:'/com.atproto.server.createSession'}}});"
            "AF.api('login.create_session',{identifier:'u'}); window.applyAgentCommand=function(){};"
            "</script></body></html>"
        ),
        "commands": [],
    }
    assert any("body_template" in finding for finding in _static_findings(manifest))


def test_reviewer_flags_password_session_with_basic_auth_even_with_body_template():
    manifest = {
        "feature": "bluesky_viewer",
        "kind": "app",
        "theme": "default",
        "html": (
            "<!DOCTYPE html><html><head><meta name=\"viewport\"></head><body><script>"
            "AF.defineConnector({connector_id:'login',base_url:'https://bsky.social/xrpc',"
            "auth:{type:'basic',username:'u',password:'p'},"
            "actions:{create_session:{method:'POST',path:'/com.atproto.server.createSession',"
            "body_template:{identifier:'$params.identifier',password:'$secret.password'}}}});"
            "AF.api('login.create_session',{identifier:'u'}); window.applyAgentCommand=function(){};"
            "</script></body></html>"
        ),
        "commands": [],
    }
    assert any("basic" in finding for finding in _static_findings(manifest))


def test_reviewer_accepts_password_session_with_body_template_and_no_auth_header():
    manifest = {
        "feature": "bluesky_viewer",
        "kind": "app",
        "theme": "default",
        "html": (
            "<!DOCTYPE html><html><head><meta name=\"viewport\"></head><body><script>"
            "AF.defineConnector({connector_id:'login',base_url:'https://bsky.social/xrpc',"
            "auth:{type:'none',username:'u',password:'p'},"
            "actions:{create_session:{method:'POST',path:'/com.atproto.server.createSession',"
            "body_template:{identifier:'$secret.username',password:'$secret.password'}}}});"
            "AF.api('login.create_session',{}); window.applyAgentCommand=function(){};"
            "</script></body></html>"
        ),
        "commands": [],
    }
    assert not any("body_template" in finding for finding in _static_findings(manifest))
    assert not any("basic" in finding for finding in _static_findings(manifest))


def test_reviewer_flags_inner_html_for_connector_data_without_escape():
    manifest = {
        "feature": "external_feed",
        "kind": "app",
        "theme": "default",
        "html": (
            "<!DOCTYPE html><html><head><meta name=\"viewport\"></head><body><div id=\"feed\"></div><script>"
            "AF.defineConnector({connector_id:'feed',base_url:'https://api.example.com',actions:{list:{method:'GET',path:'/items'}}});"
            "async function render(){const res=await AF.api('feed.list',{});"
            "document.getElementById('feed').innerHTML=(res.items||[]).map(x=>`<p>${String(x.text)}</p>`).join('');}"
            "window.applyAgentCommand=function(){};"
            "</script></body></html>"
        ),
        "commands": [],
    }
    assert any("innerHTML" in finding for finding in _static_findings(manifest))


def test_reviewer_flags_variable_external_src_for_connector_data():
    manifest = {
        "feature": "external_feed",
        "kind": "app",
        "theme": "default",
        "html": (
            "<!DOCTYPE html><html><head><meta name=\"viewport\"></head><body><div id=\"feed\"></div><script>"
            "AF.defineConnector({connector_id:'feed',base_url:'https://api.example.com',actions:{list:{method:'GET',path:'/items'}}});"
            "async function render(){const res=await AF.api('feed.list',{});"
            "const thumb=(res.items||[])[0].thumb; document.getElementById('feed').innerHTML=`<img src=\"${thumb}\">`;}"
            "window.applyAgentCommand=function(){};"
            "</script></body></html>"
        ),
        "commands": [],
    }
    findings = _static_findings(manifest)
    assert any("img/src" in finding for finding in findings)
