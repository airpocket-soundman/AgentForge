"""Backend Web search/fetch tool behavior."""

from app.orchestrator import service as orchestrator_service
from app.tools import web_search


def test_worker_web_context_searches_and_fetches_public_pages(monkeypatch):
    monkeypatch.setattr(
        web_search,
        "web_search",
        lambda query, max_results=5: [
            web_search.SearchResult("公式情報", "https://example.com/info", "公開情報の説明"),
        ],
    )
    monkeypatch.setattr(web_search, "web_fetch", lambda url, max_chars=1200: "本文の抜粋")

    context = web_search.worker_web_context("仙台駅 近く 食事処を探して")

    assert "リアルタイムWeb検索/閲覧コンテキスト" in context
    assert "公式情報" in context
    assert "本文の抜粋" in context
    assert "生成HTMLから直接fetchせず" in context


def test_worker_web_context_skips_when_current_info_not_needed(monkeypatch):
    called = False

    def fake_search(query, max_results=5):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(web_search, "web_search", fake_search)

    assert web_search.worker_web_context("赤いボタンを追加して") == ""
    assert called is False


def test_public_https_url_blocks_non_public_targets():
    assert web_search._public_https_url("http://example.com") is False
    assert web_search._public_https_url("https://localhost/admin") is False
    assert web_search._public_https_url("https://127.0.0.1/admin") is False


def test_orchestrator_plan_prompt_includes_shared_web_context(monkeypatch):
    from app import agents

    monkeypatch.setattr(web_search, "worker_web_context", lambda goal: "[WEB] current context")
    monkeypatch.setattr(agents, "load", lambda name: f"{name} prompt")
    monkeypatch.setattr(agents, "policy", lambda: "policy prompt")

    prompt = orchestrator_service._build_plan_prompt("最新情報を調べるアプリ")

    assert "[Orchestrator Web閲覧権限]" in prompt
    assert "[WEB] current context" in prompt
    assert "生成HTMLに fetch / 外部URL直アクセスを入れてはいけない" in prompt
