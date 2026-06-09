"""UI Designer worker — REAL build-time worker.

Turns a feature goal into an actual `view_manifest` by calling the LLM through the
gateway (claude-cli locally / Gemini in prod). The Generated View Renderer renders
this manifest, so the screen is genuinely produced by the agent — not hard-coded.
Falls back to a generic manifest when no LLM is reachable so the pipeline completes.
"""
from __future__ import annotations

import hashlib
import json
import re

from app import agents
from app.llm.gateway import ModelTier, get_llm
from app.models.generated import (
    CalendarSpec,
    ChartSpec,
    FieldSpec,
    GanttSpec,
    StatSpec,
    ViewManifest,
)

_ALLOWED_TYPES = {"text", "textarea", "number", "date", "checkbox", "markdown"}
_ALLOWED_THEMES = {"default", "warm", "forest", "ocean"}
_ALLOWED_CHARTS = {"bar", "line", "pie", "doughnut"}
_ALLOWED_AGG = {"sum", "count", "avg"}

_SCHEMA = """まず種別(kind)を判断し、JSONのみ出力（前後の説明やコードフェンス不要）。

■ 記録・一覧・集計・予定管理など「データ管理系」なら kind="data":
{
  "kind": "data",
  "feature": "<英小文字スラッグ>",
  "title": "<日本語の機能名>",
  "description": "<1〜2文の平易な説明>",
  "theme": "default|warm|forest|ocean",
  "fields": [{"key": "<snake_case>", "label": "<日本語>", "type": "text|textarea|number|date|checkbox|markdown"}],
  "list_columns": ["<fieldのkey>"],
  "stats": [{"label": "<日本語>", "value": "<数値fieldのkey>", "agg": "sum|count|avg"}],
  "charts": [{"type": "bar|line|pie|doughnut", "title": "<日本語>", "category": "<fieldのkey>", "value": "<数値fieldのkey>"}],
  "gantt": {"label": "<fieldのkey>", "start": "<date型key>", "end": "<date型key>"},
  "calendar": {"date": "<date型key>", "title": "<fieldのkey>"}
}

■ お絵描き・電卓・ゲーム・特殊UIなど「インタラクティブ/独自実装」なら kind="app":
{
  "kind": "app",
  "feature": "<英小文字スラッグ>",
  "title": "<日本語の機能名>",
  "description": "<1〜2文の説明>",
  "theme": "default",
  "html": "<完結した単一HTML文書。<style>と<script>を内包し、外部リソース無しで動く。要求された機能を実際に実装する（例: canvasお絵描き、計算ロジック等）。サンドボックス実行のため localStorage/cookie/外部通信/別ウィンドウは使えない（状態はメモリ内）。bodyはmargin:0でビューポートいっぱいに>"
}

判断指針:
- 記録・一覧・管理・集計が主目的 → data。可視化(charts/gantt/calendar)は主目的に直結する時だけ（日付/数値があるだけで足さない）。dataモードでは生HTML/CSS/JSを書かず部品宣言のみ。
- 描く・計算する・遊ぶ・操作するなどインタラクティブが主目的 → app。実際に動く self-contained な HTML/JS/CSS を書く。
- markdown型は長文メモ向け。stats.value/charts.value は number型field。gantt/calendar の日付は date型field。
- スラッグは英小文字。テーマは内容に近いもの（曖昧なら default）。"""


def _slug(goal: str) -> str:
    return "gen_" + hashlib.sha1(goal.encode("utf-8")).hexdigest()[:8]


def _default_fields() -> list[FieldSpec]:
    return [
        FieldSpec(key="title", label="名称", type="text"),
        FieldSpec(key="note", label="メモ", type="textarea"),
    ]


def design(goal: str) -> ViewManifest:
    """Design a real view_manifest for the requested feature."""
    llm = get_llm()
    if llm.enabled:
        try:
            prompt = "\n\n".join(
                [
                    agents.load("ui_designer"),
                    agents.policy(),
                    f"次の機能の画面（view_manifest）を設計してください。\nユーザー要求: {goal}",
                    _SCHEMA,
                ]
            )
            raw = llm.generate(prompt, tier=ModelTier.PRO).strip()
            if raw.startswith("```"):
                raw = raw.strip("`").split("\n", 1)[-1]
            data = json.loads(raw)
            kind = str(data.get("kind", "data")).lower()
            feature = re.sub(r"[^a-z0-9_]+", "", str(data.get("feature", "")).lower()) or _slug(goal)
            title = (str(data.get("title") or goal))[:60]
            description = str(data.get("description", ""))[:200]
            theme = data.get("theme", "default")
            theme = theme if theme in _ALLOWED_THEMES else "default"

            # app mode: the worker wrote real HTML/JS/CSS for an interactive tool,
            # rendered in a sandboxed iframe. This is genuine code generation.
            if kind == "app" and isinstance(data.get("html"), str) and "<" in data["html"]:
                return ViewManifest(
                    kind="app", feature=feature, title=title, description=description,
                    theme=theme, html=data["html"], generated_by=llm.name,
                )

            # data mode: structured standard components.
            fields = [
                FieldSpec(key=str(f["key"]), label=str(f.get("label") or f["key"]), type=f.get("type", "text"))
                for f in data.get("fields", [])
                if f.get("key") and f.get("type", "text") in _ALLOWED_TYPES
            ] or _default_fields()
            keys = {f.key for f in fields}
            cols = [c for c in data.get("list_columns", []) if c in keys] or [f.key for f in fields[:3]]
            date_keys = {f.key for f in fields if f.type == "date"}
            charts = [
                ChartSpec(type=c.get("type", "bar"), title=str(c.get("title", "")), category=c["category"], value=c["value"])
                for c in data.get("charts", [])
                if c.get("type", "bar") in _ALLOWED_CHARTS and c.get("category") in keys and c.get("value") in keys
            ]
            stats = [
                StatSpec(label=str(s["label"]), value=s["value"], agg=s.get("agg", "sum"))
                for s in data.get("stats", [])
                if s.get("label") and s.get("value") in keys and s.get("agg", "sum") in _ALLOWED_AGG
            ]
            g = data.get("gantt")
            gantt = (
                GanttSpec(label=g["label"], start=g["start"], end=g["end"])
                if isinstance(g, dict) and g.get("label") in keys and g.get("start") in date_keys and g.get("end") in date_keys
                else None
            )
            cal = data.get("calendar")
            calendar = (
                CalendarSpec(date=cal["date"], title=cal["title"])
                if isinstance(cal, dict) and cal.get("date") in date_keys and cal.get("title") in keys
                else None
            )
            return ViewManifest(
                kind="data",
                feature=feature,
                title=title,
                description=description,
                theme=theme,
                fields=fields,
                list_columns=cols,
                stats=stats,
                charts=charts,
                gantt=gantt,
                calendar=calendar,
                generated_by=llm.name,
            )
        except Exception:  # noqa: BLE001 — any LLM/parse failure -> deterministic fallback
            pass

    return ViewManifest(
        feature=_slug(goal),
        title=goal[:60],
        description=f"「{goal[:40]}」に関する項目を記録・一覧管理する画面です。",
        theme="default",
        fields=_default_fields(),
        list_columns=["title", "note"],
        generated_by="stub",
    )
