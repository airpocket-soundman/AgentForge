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
    return checks, errors


def verify(manifest: dict, goal: str) -> dict:
    """Verify a generated app runs and meets the request."""
    checks, errors = _static_checks(manifest)

    llm = get_llm()
    # Only ask the model when the artifact is at least structurally loadable.
    if llm.enabled and not errors and (manifest.get("kind") or "app") == "app":
        try:
            html = (manifest.get("html") or "")[:8000]
            prompt = "\n\n".join([
                agents.load("tester"),
                f"ユーザー要求: {goal}",
                "生成アプリの HTML:\n" + html,
                '致命的に「動かない／要求を満たさない」点だけを JSON で返す: {"errors": ["<日本語>", ...]}（無ければ空配列・JSON のみ）',
            ])
            raw = llm.generate(prompt, tier=ModelTier.FLASH).strip()
            if raw.startswith("```"):
                raw = raw.strip("`").split("\n", 1)[-1]
            data = json.loads(raw)
            for e in data.get("errors", []):
                if str(e).strip():
                    errors.append(str(e).strip())
        except Exception:  # noqa: BLE001 — keep deterministic result on LLM/parse failure
            pass

    return {"verdict": "fail" if errors else "pass", "checks": checks, "errors": errors}
