"""Read-only web search helper for Specialist Workers.

Generated mini-app HTML is still sandboxed and cannot call arbitrary URLs. This
module gives backend workers a narrow, auditable way to fetch current public
search snippets for user-requested memo/body writing.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import ipaddress
import socket
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from app.config import get_settings


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""


class _DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[SearchResult] = []
        self._in_title = False
        self._in_snippet = False
        self._pending_url = ""
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: v or "" for k, v in attrs}
        classes = set((attr.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self._flush_pending()
            self._in_title = True
            self._pending_url = _clean_duck_url(attr.get("href") or "")
            self._title_parts = []
            self._snippet_parts = []
        elif "result__snippet" in classes:
            self._in_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title:
            self._in_title = False
        if self._in_snippet and tag in {"a", "div"}:
            self._in_snippet = False
            self._flush_pending()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        elif self._in_snippet:
            self._snippet_parts.append(data)

    def close(self) -> None:
        super().close()
        self._flush_pending()

    def _flush_pending(self) -> None:
        title = _compact_ws("".join(self._title_parts))
        if not title or not self._pending_url:
            return
        snippet = _compact_ws("".join(self._snippet_parts))
        if not any(r.url == self._pending_url for r in self.results):
            self.results.append(SearchResult(title=title, url=self._pending_url, snippet=snippet))
        self._pending_url = ""
        self._title_parts = []
        self._snippet_parts = []


def web_search(query: str, *, max_results: int = 5) -> list[SearchResult]:
    """Return current public search snippets, or [] when disabled/unavailable."""
    settings = get_settings()
    q = _compact_ws(query)[:300]
    if not settings.web_search_enabled or not q:
        return []
    try:
        with httpx.Client(timeout=httpx.Timeout(connect=5.0, read=12.0, write=5.0, pool=5.0), follow_redirects=True) as client:
            resp = client.get(
                "https://duckduckgo.com/html/",
                params={"q": q, "kl": "jp-jp"},
                headers={"User-Agent": settings.web_search_user_agent},
            )
            resp.raise_for_status()
    except httpx.HTTPError:
        return []
    parser = _DuckDuckGoHTMLParser()
    try:
        parser.feed(resp.text)
        parser.close()
    except Exception:  # noqa: BLE001 - malformed upstream HTML -> no search context
        return []
    return parser.results[: max(1, min(max_results, 10))]


def worker_web_context(text: str, *, max_results: int = 5, fetch_pages: int = 2) -> str:
    """Search/fetch context block shared by Orchestrator and Specialist Workers."""
    if not needs_web_context(text):
        return ""
    query = web_query_from_text(text)
    results = web_search(query, max_results=max_results)
    if not results:
        return (
            "[リアルタイムWeb検索]\n"
            f"検索クエリ: {query}\n"
            "検索結果を取得できませんでした。現在情報が必要な場合は、未確認であることを明記してください。\n"
        )
    fetched: list[str] = []
    for result in results[: max(0, min(fetch_pages, 3))]:
        body = web_fetch(result.url, max_chars=1200)
        if body:
            fetched.append(f"- {result.title}\n  URL: {result.url}\n  抜粋: {body}")
    return (
        "[リアルタイムWeb検索/閲覧コンテキスト]\n"
        f"検索クエリ: {query}\n"
        f"{format_search_results(results)}\n"
        + (("[Web閲覧抜粋]\n" + "\n".join(fetched) + "\n") if fetched else "")
        + "上記は現在の公開Web情報です。生成HTMLから直接fetchせず、この参照情報を要約して設計・回答・state更新に使ってください。\n"
    )


def needs_web_context(text: str) -> bool:
    t = _compact_ws(text)
    return any(w in t for w in (
        "検索", "探して", "調べて", "最新", "現在", "近く", "周辺", "営業時間",
        "ニュース", "公式", "API仕様", "ドキュメント", "事例", "比較", "価格",
        "today", "latest", "current", "near", "search", "web",
    ))


def web_query_from_text(text: str) -> str:
    t = _compact_ws(text)
    for word in ("メモに", "本文に", "説明欄に", "記入して", "入れて", "書いて", "追記して", "追加して", "実装して", "作って"):
        t = t.replace(word, " ")
    t = t.replace("を調べて", " ").replace("を探して", " ").replace("検索して", " ")
    return _compact_ws(t)[:200] or _compact_ws(text)[:200]


def format_search_results(results: list[SearchResult], *, max_chars: int = 2400) -> str:
    lines: list[str] = []
    for i, r in enumerate(results, start=1):
        line = f"{i}. {r.title} - {r.url}"
        if r.snippet:
            line += f"\n   {r.snippet}"
        lines.append(line)
    out = "\n".join(lines)
    return out[:max_chars]


def web_fetch(url: str, *, max_chars: int = 6000) -> str:
    """Fetch a public HTTPS page as plain text for worker context.

    This is deliberately narrow: no credentials, no cookies, no private networks,
    no generated-app access. Returns "" on any failure.
    """
    settings = get_settings()
    if not settings.web_search_enabled:
        return ""
    target = (url or "").strip()
    if not _public_https_url(target):
        return ""
    try:
        with httpx.Client(timeout=httpx.Timeout(connect=5.0, read=12.0, write=5.0, pool=5.0), follow_redirects=False) as client:
            resp = client.get(target, headers={"User-Agent": settings.web_search_user_agent})
            resp.raise_for_status()
    except httpx.HTTPError:
        return ""
    content_type = resp.headers.get("content-type", "")
    if "text/html" not in content_type and "text/plain" not in content_type:
        return ""
    parser = _PlainTextHTMLParser()
    try:
        parser.feed(resp.text)
        parser.close()
    except Exception:  # noqa: BLE001
        return ""
    return _compact_ws(parser.text)[:max_chars]


class _PlainTextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = False
        self._parts: list[str] = []

    @property
    def text(self) -> str:
        return " ".join(self._parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            chunk = _compact_ws(data)
            if chunk:
                self._parts.append(chunk)


def _clean_duck_url(raw: str) -> str:
    value = unescape(raw or "")
    if value.startswith("//"):
        value = "https:" + value
    parsed = urlparse(value)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg", [""])[0]
        if uddg:
            return unquote(uddg)
    return value


def _compact_ws(value: str) -> str:
    return " ".join(unescape(value or "").split())


def _public_https_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host in {"localhost"} or host.endswith(".local"):
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True
