"""Deploy-time gate tests (Tester + Reviewer), deterministic static path.

Test env = no LLM (stub, enabled=False), so only the deterministic checks run —
no network, fully reproducible.
"""
from app.workers import reviewer, tester

_GOOD_HTML = (
    "<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'></head>"
    "<body><canvas id='c'></canvas><button id='b'>clear</button>"
    "<script>window.applyAgentCommand=function(n,a){};</script></body></html>"
)


def _manifest(**over) -> dict:
    m = {
        "kind": "app",
        "feature": "paint",
        "title": "お絵描き",
        "theme": "default",
        "html": _GOOD_HTML,
        "commands": [{"name": "clear", "description": "全消去", "inputSchema": {"type": "object"}}],
        "generated_by": "stub",
    }
    m.update(over)
    return m


# --- Reviewer ---------------------------------------------------------------

def test_reviewer_passes_clean_app():
    r = reviewer.review(_manifest(), "お絵描きツール")
    assert r["verdict"] == "ok"
    assert r["findings"] == []


def test_reviewer_flags_localstorage():
    html = _GOOD_HTML.replace("window.applyAgentCommand", "localStorage.setItem('x',1);window.applyAgentCommand")
    r = reviewer.review(_manifest(html=html), "お絵描き")
    assert r["verdict"] == "needs_revision"
    assert any("localStorage" in f for f in r["findings"])


def test_reviewer_flags_fetch_and_bad_theme_and_slug():
    html = _GOOD_HTML.replace("window.applyAgentCommand", "fetch('/x');window.applyAgentCommand")
    r = reviewer.review(_manifest(html=html, theme="neon", feature="お絵描き"), "お絵描き")
    assert r["verdict"] == "needs_revision"
    joined = " ".join(r["findings"])
    assert "fetch" in joined and "theme" in joined and "スラッグ" in joined


def test_reviewer_flags_commands_without_handler():
    html = "<!DOCTYPE html><html><body><div>hi</div></body></html>"  # no applyAgentCommand
    r = reviewer.review(_manifest(html=html), "お絵描き")
    assert any("applyAgentCommand" in f for f in r["findings"])


def test_reviewer_requires_persistence_for_games():
    r = reviewer.review(_manifest(feature="tetris", title="テトリス", commands=[]), "テトリスを作って")
    assert r["verdict"] == "needs_revision"
    assert any("AF.load" in f and "AF.save" in f for f in r["findings"])


def test_reviewer_accepts_game_persistence_bridge():
    html = _GOOD_HTML.replace(
        "window.applyAgentCommand",
        "AF.load().then(function(){});AF.save({board:[]});window.applyAgentCommand",
    )
    r = reviewer.review(_manifest(feature="tetris", title="テトリス", html=html, commands=[]), "テトリスを作って")
    assert not any("途中状態" in f for f in r["findings"])


# --- Tester -----------------------------------------------------------------

def test_tester_passes_runnable_app():
    t = tester.verify(_manifest(), "お絵描きツール")
    assert t["verdict"] == "pass"
    assert t["errors"] == []
    assert t["checks"]


def test_tester_fails_non_html():
    t = tester.verify(_manifest(html="申し訳ありません、生成できませんでした。"), "電卓")
    assert t["verdict"] == "fail"
    assert t["errors"]


def test_tester_fails_commands_without_handler():
    html = "<!DOCTYPE html><html><body><button>x</button><script>var a=1;</script></body></html>"
    t = tester.verify(_manifest(html=html), "お絵描き")
    assert t["verdict"] == "fail"
    assert any("applyAgentCommand" in e for e in t["errors"])


def test_tester_requires_persistence_for_games():
    t = tester.verify(_manifest(feature="tetris", title="テトリス", commands=[]), "テトリスを作って")
    assert t["verdict"] == "fail"
    assert any("AF.load" in e and "AF.save" in e for e in t["errors"])
