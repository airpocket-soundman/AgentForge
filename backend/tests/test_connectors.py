from app.connectors.registry import get_connector, list_connectors, split_action_name
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

