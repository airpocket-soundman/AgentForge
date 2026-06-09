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
from app.models.generated import ChartSpec, FieldSpec, ViewManifest

_ALLOWED_TYPES = {"text", "textarea", "number", "date", "checkbox"}
_ALLOWED_THEMES = {"default", "warm", "forest", "ocean"}
_ALLOWED_CHARTS = {"bar", "line", "pie", "doughnut"}

_SCHEMA = """出力はJSONのみ（前後の説明やコードフェンスは不要）:
{
  "feature": "<英小文字スラッグ。例: gantt, inventory, recipe>",
  "title": "<日本語の機能名>",
  "theme": "default|warm|forest|ocean",
  "fields": [{"key": "<snake_case>", "label": "<日本語ラベル>", "type": "text|textarea|number|date|checkbox"}],
  "list_columns": ["<fieldのkey>", "..."],
  "charts": [{"type": "bar|line|pie|doughnut", "title": "<日本語>", "category": "<分類に使うfieldのkey>", "value": "<数値fieldのkey>"}]
}
制約:
- fields は 2〜6 個。編集可能な要素は決定的CRUD APIに保存される前提で設計する。
- 標準コンポーネント（フォーム＋一覧＋チャート）で表現する。生CSS/HTML/JSは出力しない。
- 可視化が有用なら charts を入れる（value は number 型のfield、category は分類軸のfield）。不要なら空配列。
- 見た目テーマは内容に最も近いものを選ぶ（指定が曖昧なら default）。"""


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

            fields = [
                FieldSpec(key=str(f["key"]), label=str(f.get("label") or f["key"]), type=f.get("type", "text"))
                for f in data.get("fields", [])
                if f.get("key") and f.get("type", "text") in _ALLOWED_TYPES
            ] or _default_fields()
            keys = {f.key for f in fields}
            feature = re.sub(r"[^a-z0-9_]+", "", str(data.get("feature", "")).lower()) or _slug(goal)
            theme = data.get("theme", "default")
            cols = [c for c in data.get("list_columns", []) if c in keys] or [f.key for f in fields[:3]]
            charts = [
                ChartSpec(type=c.get("type", "bar"), title=str(c.get("title", "")), category=c["category"], value=c["value"])
                for c in data.get("charts", [])
                if c.get("type", "bar") in _ALLOWED_CHARTS and c.get("category") in keys and c.get("value") in keys
            ]
            return ViewManifest(
                feature=feature,
                title=(str(data.get("title") or goal))[:60],
                theme=theme if theme in _ALLOWED_THEMES else "default",
                fields=fields,
                list_columns=cols,
                charts=charts,
                generated_by=llm.name,
            )
        except Exception:  # noqa: BLE001 — any LLM/parse failure -> deterministic fallback
            pass

    return ViewManifest(
        feature=_slug(goal),
        title=goal[:60],
        theme="default",
        fields=_default_fields(),
        list_columns=["title", "note"],
        generated_by="stub",
    )
