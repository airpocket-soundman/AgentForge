"""Tester worker — deploy-time gate (dynamic "does it actually run / meet intent").

Runs inside the production-equivalent Docker stack (Firestore emulator + backend,
LLM provider swapped to claude). Phase 1 verification = structural load checks +
an LLM judgment (FLASH) of "does it run and satisfy the request". Headless-browser
execution can be layered on later; the environment here already mirrors prod.

Returns {"verdict": "pass"|"fail", "checks": [str], "errors": [str]}.
"""
from __future__ import annotations

import json
import re

from app import agents
from app.llm.gateway import ModelTier, get_llm

_STRUCT_RE = re.compile(
    r"<(?:html|body|canvas|svg|button|form|table|main|section|div|input|h[1-6]|ul|ol|p)\b", re.I
)

_PERSISTENCE_KEYWORDS = (
    "保存", "復元", "途中", "リロード", "画面遷移", "メモ", "タスク", "todo", "フォーム", "設定",
    "ゲーム", "テトリス", "tetris", "盤面", "スコア", "レベル", "ライン", "手番",
    "クイズ", "進捗", "家計簿", "日記", "予定", "スケジュール",
)


def _requires_persistence(goal: str, criteria: list[str] | None) -> bool:
    hay = "\n".join([goal or "", "\n".join(criteria or [])]).lower()
    return any(k.lower() in hay for k in _PERSISTENCE_KEYWORDS)


def _static_checks(manifest: dict) -> tuple[list[str], list[str]]:
    """Deterministic load/structure checks. Returns (checks_passed, errors)."""
    checks: list[str] = []
    errors: list[str] = []

    if (manifest.get("kind") or "app") != "app":
        return ["データ型ビュー: 動作検証はスキップ"], errors

    html = manifest.get("html") or ""
    low = html.lower()
    if "<!doctype html" in low or "<html" in low:
        checks.append("完結した HTML 文書として読み込める")
    else:
        errors.append("完結した HTML 文書でない（<!DOCTYPE html> から始まっていない）")
    if "</" in html and _STRUCT_RE.search(html):
        checks.append("UI 要素（構造タグ）がある")
    else:
        errors.append("UI 要素が見当たらず、画面が表示されない可能性")
    if "<script" in low:
        checks.append("スクリプトを含む")
    else:
        errors.append("スクリプトが無く、操作が動作しない可能性")

    commands = manifest.get("commands") or []
    if commands:
        if "applyAgentCommand" in html:
            checks.append(f"操作ツール {len(commands)} 個・applyAgentCommand 実装あり")
        else:
            errors.append("commands を宣言しているが applyAgentCommand 未実装（操作が効かない）")
    if commands or manifest.get("worker_state_mode") in {"state", "hybrid"}:
        eval_cases = manifest.get("worker_eval_cases") or []
        if eval_cases:
            checks.append(f"専門ワーカー評価ケース {len(eval_cases)} 件")
        else:
            errors.append("専門ワーカーの自然言語判断を検証する worker_eval_cases が無い")
    return checks, errors


def verify(manifest: dict, goal: str, criteria: list[str] | None = None) -> dict:
    """Verify a generated app runs and meets the request.

    `criteria` (the design plan's user-approved acceptance list) makes the
    judgment itemized: each criterion is verified individually and reported as
    ✅/❌ — instead of one opaque overall verdict."""
    checks, errors = _static_checks(manifest)
    criteria_results: list[dict] = []
    if (manifest.get("kind") or "app") == "app" and _requires_persistence(goal, criteria):
        html = manifest.get("html") or ""
        if "AF.load" in html and "AF.save" in html:
            checks.append("途中状態を AF.load()/AF.save() で保存・復元する実装がある")
        else:
            errors.append("画面遷移・リロード後に途中状態を復元する AF.load()/AF.save() 実装が無い")

    llm = get_llm()
    # Only ask the model when the artifact is at least structurally loadable.
    if llm.enabled and not errors and (manifest.get("kind") or "app") == "app":
        try:
            html = manifest.get("html") or ""  # send full html (avoid false "truncated" reads)
            if len(html) > 100000:
                html = html[:100000] + "\n<!-- …(以下はサイズ上限で省略。末尾の閉じタグ有無で『途中で切れている』と判断しないこと) -->"
            parts = [
                agents.load("tester"),
                f"ユーザー要求: {goal}",
                "生成アプリの HTML:\n" + html,
            ]
            if criteria:
                parts.append(
                    "受け入れ条件（ユーザーが承認した検証項目。1つずつコードに照らして判定すること）:\n"
                    + "\n".join(f"{i+1}. {c}" for i, c in enumerate(criteria))
                )
                parts.append(
                    'JSON のみで返す: {"errors": ["<致命的に動かない点>", ...], '
                    '"criteria": [{"text": "<条件>", "ok": true|false, "note": "<短い根拠>"}]}\n'
                    "criteria は受け入れ条件と同数・同順で返す。"
                )
            else:
                parts.append('致命的に「動かない／要求を満たさない」点だけを JSON で返す: {"errors": ["<日本語>", ...]}（無ければ空配列・JSON のみ）')
            raw = llm.generate("\n\n".join(parts), tier=ModelTier.FLASH).strip()
            if raw.startswith("```"):
                raw = raw.strip("`").split("\n", 1)[-1]
            data = json.loads(raw)
            for e in data.get("errors", []):
                if str(e).strip():
                    errors.append(str(e).strip())
            for c in data.get("criteria", []) or []:
                if isinstance(c, dict) and str(c.get("text", "")).strip():
                    item = {"text": str(c["text"]).strip()[:120], "ok": bool(c.get("ok")),
                            "note": str(c.get("note", "")).strip()[:120]}
                    criteria_results.append(item)
                    if not item["ok"]:  # an unmet approved criterion is a failure
                        errors.append(f"受け入れ条件NG: {item['text']}" + (f"（{item['note']}）" if item["note"] else ""))
        except Exception:  # noqa: BLE001 — keep deterministic result on LLM/parse failure
            pass

    return {"verdict": "fail" if errors else "pass", "checks": checks,
            "errors": errors, "criteria": criteria_results}
