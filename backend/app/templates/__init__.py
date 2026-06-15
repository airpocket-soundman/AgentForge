"""Default mini-app templates.

Beginners start faster by IMPROVING a working default than by building from
scratch. These are NOT pre-registered — they're deployed on demand: when a user
asks for one (e.g. 「電卓を作って」), the Receptor offers the matching default,
deploys it as a preview the user publishes (「反映して」), and the user then
improves it through the normal edit pipeline.

Each MANIFEST is a kind="app" ViewManifest (self-contained HTML + MCP-style
commands) that already follows the code conventions (AF.load/save, responsive,
no embedded chat, applyAgentCommand). A deploy is deterministic (no LLM).
"""
from __future__ import annotations

from app.models.generated import ViewManifest

from . import calculator, memo, paint, schedule, task_manager, translate

_MODULES = [calculator, task_manager, schedule, memo, translate, paint]

# feature slug -> manifest dict
TEMPLATES: dict[str, dict] = {m.MANIFEST["feature"]: m.MANIFEST for m in _MODULES}

# Keyword → template key. Matched case-insensitively as a substring of the goal.
# Keep keywords SPECIFIC (e.g. 「電卓」 not 「計算」) to avoid hijacking custom asks.
_KEYWORDS: dict[str, tuple[str, ...]] = {
    "calculator": ("電卓", "でんたく", "calculator", "calc"),
    "task_manager": ("タスク", "todo", "to-do", "やること", "やる事", "task"),
    "schedule": ("スケジュール", "予定", "カレンダー", "schedule", "calendar"),
    "memo": ("メモ", "memo", "ノート", "notepad", "note"),
    "translate": ("翻訳", "translate", "translation", "ほんやく"),
    "paint": ("ペイント", "お絵描き", "おえかき", "お絵かき", "落書き", "paint", "drawing", "draw"),
}


def list_templates() -> list[dict]:
    """Lightweight catalogue (no html) for UI / discovery."""
    return [{"feature": m["feature"], "title": m["title"], "description": m["description"],
             "theme": m["theme"]} for m in TEMPLATES.values()]


def catalogue_text() -> str:
    """One-line-per-template summary for injecting into Orchestrator prompts, so the
    designer KNOWS which proven defaults exist and can build on them."""
    return "\n".join(f"- {m['feature']}（{m['title']}）: {m['description']}" for m in TEMPLATES.values())


def match_template(goal: str) -> str | None:
    """Return the template key whose keywords appear in `goal`, else None."""
    t = (goal or "").lower()
    for key, words in _KEYWORDS.items():
        if any(w.lower() in t for w in words):
            return key
    return None


def get_template(key: str) -> dict | None:
    return TEMPLATES.get(key)


def to_manifest(key: str) -> ViewManifest | None:
    """Build a ViewManifest from a template (generated_by='template')."""
    m = TEMPLATES.get(key)
    if not m:
        return None
    return ViewManifest(
        feature=m["feature"], title=m["title"], description=m["description"],
        kind="app", theme=m["theme"], html=m["html"], commands=m["commands"],
        generated_by="template",
    )
