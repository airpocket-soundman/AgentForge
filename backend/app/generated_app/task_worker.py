"""Per-task worker agent: a small conversation that organizes a single task.

Uses Gemini Flash (cheap, per the model-routing policy) to reply to the user and
maintain a structured "organized summary" of the task. Falls back to a stub when
no API key is reachable, so the UI is exercisable offline.
"""
from __future__ import annotations

import json

from app.llm.gemini import ModelTier, get_gemini

_PROMPT = """あなたはタスク管理アプリの「ワーカーエージェント」です。
1つのタスクについてユーザーと対話し、内容を整理します。
これまでの会話と新しい発言をふまえ、JSONのみで返答してください（前後に説明やコードフェンス不要）。

タスク: {title}
現在の整理メモ: {summary}
直近の会話:
{history}
ユーザーの新しい発言: {text}

出力スキーマ:
{{
  "reply": "<ユーザーへの短い返答（日本語）>",
  "summary": "<タスク内容を整理した箇条書き（日本語, 改行区切り）。目的/やること/期日/メモ等>"
}}
"""


def respond(task: dict, user_text: str) -> tuple[str, str]:
    """Return (reply_text, organized_summary)."""
    current_summary = task.get("summary") or ""
    gemini = get_gemini()

    if not gemini.enabled:
        reply = f"（ワーカーエージェント・スタブ）「{task['title']}」について承りました。"
        summary = current_summary or f"- {task['title']}\n- メモ: {user_text}"
        return reply, summary

    history_lines = "\n".join(
        f"{m.get('role')}: {m.get('text')}" for m in task.get("messages", [])[-8:]
    )
    prompt = _PROMPT.format(
        title=task.get("title", ""),
        summary=current_summary or "(なし)",
        history=history_lines or "(なし)",
        text=user_text,
    )
    try:
        raw = gemini.generate(prompt, tier=ModelTier.FLASH).strip()
        if raw.startswith("```"):
            raw = raw.strip("`").split("\n", 1)[-1]
        data = json.loads(raw)
        return str(data.get("reply", "")).strip(), str(data.get("summary", current_summary)).strip()
    except Exception:  # noqa: BLE001 — any LLM/parse failure -> safe fallback
        return "（整理中に問題が発生しました。もう一度お試しください）", current_summary
