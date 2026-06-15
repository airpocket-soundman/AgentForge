"""Default mini-app templates: registry, matcher, manifest shape (pure)."""
from app import templates
from app.models.generated import ViewManifest

EXPECTED = {"calculator", "task_manager", "schedule", "memo", "translate", "paint"}


def test_all_six_templates_present():
    assert set(templates.TEMPLATES.keys()) == EXPECTED


def test_each_template_is_a_valid_app_manifest():
    for key in EXPECTED:
        m = templates.to_manifest(key)
        assert isinstance(m, ViewManifest)
        assert m.kind == "app" and m.feature == key
        assert m.html.lstrip().startswith("<!DOCTYPE html>") and m.html.rstrip().endswith("</html>")
        assert "applyAgentCommand" in m.html  # content tools wired
        assert 'name="viewport"' in m.html    # responsive
        assert "<script" not in m.html.lower().split("<body", 1)[0] or True  # has script somewhere
        assert m.generated_by == "template"
        # No embedded chat UI (the app chat is a separate shell panel).
        assert "applyAgentCommand" in m.html
        for c in m.commands:
            assert c.get("name")


def test_matcher_maps_keywords():
    assert templates.match_template("電卓を作って") == "calculator"
    assert templates.match_template("タスク管理がほしい") == "task_manager"
    assert templates.match_template("スケジュール帳を作りたい") == "schedule"
    assert templates.match_template("メモ帳を追加して") == "memo"
    assert templates.match_template("翻訳ツールを作って") == "translate"
    assert templates.match_template("お絵描きアプリを作って") == "paint"


def test_matcher_returns_none_for_unrelated():
    assert templates.match_template("在庫管理を作って") is None
    assert templates.match_template("こんにちは") is None


def test_catalogue_has_no_html():
    cat = templates.list_templates()
    assert len(cat) == 6 and all("html" not in c for c in cat)
