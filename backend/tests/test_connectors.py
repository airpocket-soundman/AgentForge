from app.connectors.registry import get_connector, list_connectors, split_action_name
from app.connectors.adapters import ConnectorError, invoke_connector
from app.workers.reviewer import _static_findings


def test_connector_defaults_match_admin_policy():
    items = {c["id"]: c for c in list_connectors()}
    assert items["bluesky"]["enabled"] is True
    assert items["github"]["enabled"] is True
    assert items["notion"]["enabled"] is True
    for disabled in ["x", "slack", "discord", "google_sheets", "google_calendar", "airtable"]:
        assert items[disabled]["enabled"] is False


def test_split_action_name():
    assert split_action_name("bluesky.get_timeline") == ("bluesky", "get_timeline")


def test_get_connector_returns_copy():
    item = get_connector("bluesky")
    assert item is not None
    item["enabled"] = False
    assert get_connector("bluesky")["enabled"] is True
    assert get_connector("bluesky")["credential_fields"][0]["key"] == "identifier"


def test_reviewer_allows_af_api_but_rejects_fetch():
    manifest = {
        "feature": "social_viewer",
        "kind": "app",
        "theme": "default",
        "html": "<!DOCTYPE html><html><head><meta name=\"viewport\"></head><body><script>AF.api('bluesky.get_timeline',{limit:30}); window.applyAgentCommand=function(){};</script></body></html>",
        "commands": [],
    }
    assert not _static_findings(manifest)

    manifest["html"] = manifest["html"].replace("AF.api('bluesky.get_timeline',{limit:30});", "fetch('https://example.com');")
    assert any("fetch" in finding for finding in _static_findings(manifest))


def test_github_adapter_lists_issues(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return [{"number": 1, "title": "issue"}]

    class FakeClient:
        def __init__(self, timeout):
            assert timeout == 20

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers=None, params=None):
            calls.append((url, headers, params))
            return FakeResponse()

    monkeypatch.setattr("app.connectors.adapters.httpx.Client", FakeClient)
    result = invoke_connector("github", "list_issues", {"repo": "owner/repo", "state": "all"}, {"token": "ghp_x"})
    assert result["ok"] is True
    assert result["data"]["items"][0]["number"] == 1
    assert calls[0][0] == "https://api.github.com/repos/owner/repo/issues"
    assert calls[0][1]["Authorization"] == "Bearer ghp_x"
    assert calls[0][2]["state"] == "all"


def test_github_adapter_rejects_bad_repo():
    try:
        invoke_connector("github", "list_issues", {"repo": "https://github.com/owner/repo"}, {"token": "ghp_x"})
    except ConnectorError as exc:
        assert exc.status_code == 400
        assert "owner/name" in exc.message
    else:
        raise AssertionError("ConnectorError was not raised")
