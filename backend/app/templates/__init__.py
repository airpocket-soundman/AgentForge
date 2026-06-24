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

from . import calculator, household_budget, memo, paint, schedule, task_manager, translate

_MODULES = [calculator, task_manager, schedule, memo, household_budget, translate, paint]

# feature slug -> manifest dict
TEMPLATES: dict[str, dict] = {m.MANIFEST["feature"]: m.MANIFEST for m in _MODULES}

# Keyword → template key. Matched case-insensitively as a substring of the goal.
# Keep keywords SPECIFIC (e.g. 「電卓」 not 「計算」) to avoid hijacking custom asks.
_KEYWORDS: dict[str, tuple[str, ...]] = {
    "calculator": ("電卓", "でんたく", "calculator", "calc"),
    "task_manager": ("タスク", "todo", "to-do", "やること", "やる事", "task"),
    "schedule": ("スケジュール", "予定", "カレンダー", "schedule", "calendar"),
    "memo": ("メモ", "memo", "ノート", "notepad", "note"),
    "household_budget": ("家計簿", "かけいぼ", "支出管理", "収支", "出費", "expense", "budget"),
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


def _default_eval_cases(m: dict) -> list[dict]:
    examples = [e for e in (m.get("worker_examples") or []) if isinstance(e, dict)]
    cases: list[dict] = []
    for ex in examples[:6]:
        user = str(ex.get("user") or ex.get("input") or "").strip()
        if not user:
            continue
        command = ex.get("command")
        cases.append(
            {
                "input": user,
                "expected_behavior": "execute_command" if command else "reply_or_clarify",
                "expected_state_diff": "",
                "expected_message_contains": str(ex.get("reply") or ex.get("expected") or ""),
            }
        )
    if not cases and m.get("commands"):
        first = m["commands"][0]
        cases.append(
            {
                "input": str(first.get("description") or first.get("name") or "操作して"),
                "expected_behavior": "execute_command",
                "expected_state_diff": "",
                "expected_message_contains": "",
            }
        )
    return cases


def to_manifest(key: str) -> ViewManifest | None:
    """Build a ViewManifest from a template (generated_by='template')."""
    m = TEMPLATES.get(key)
    if not m:
        return None
    return ViewManifest(
        feature=m["feature"], title=m["title"], description=m["description"],
        kind="app", theme=m["theme"], html=m["html"], commands=m["commands"],
        worker_instructions=m.get("worker_instructions", ""),
        worker_examples=m.get("worker_examples", []),
        worker_eval_cases=m.get("worker_eval_cases") or _default_eval_cases(m),
        clarification_policy=m.get("clarification_policy", "対象・数量・日時・金額などが曖昧な場合は、実行前に短く聞き返す。"),
        dangerous_action_policy=m.get("dangerous_action_policy", "一括削除、初期化、復元困難な変更は、実行前に確認する。"),
        worker_state_mode=m.get("worker_state_mode", "commands"),
        state_schema=m.get("state_schema", {}),
        generated_by="template",
    )
