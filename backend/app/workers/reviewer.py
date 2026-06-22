"""Reviewer worker — deploy-time gate (static / code-convention review).

Judges a generated mini-app manifest against the code conventions
(docs/pages/code-conventions.html ≡ agents/policy.md / ui_designer.md). Combines
deterministic checks (cheap, reliable) with an LLM pass (FLASH) for the rest.

Returns {"verdict": "ok"|"needs_revision", "findings": [str]}.
When no LLM is reachable, only the deterministic checks run (still useful).
"""
from __future__ import annotations

import json
import re

from app import agents
from app.llm.gateway import ModelTier, get_llm

_ALLOWED_THEMES = {"default", "warm", "forest", "ocean"}

_PERSISTENCE_KEYWORDS = (
    "保存", "復元", "途中", "履歴", "メモ", "タスク", "todo", "フォーム", "設定",
    "ゲーム", "テトリス", "tetris", "盤面", "スコア", "レベル", "ライン", "手番",
    "クイズ", "進捗", "家計簿", "日記", "予定", "スケジュール",
)


def _requires_persistence(goal: str, design_plan: dict | None, requirements: list[str] | None) -> bool:
    """Whether the requested app has user/session state that must survive navigation."""
    if design_plan and design_plan.get("persistence") is True:
        return True
    hay = "\n".join(
        [
            goal or "",
            json.dumps(design_plan or {}, ensure_ascii=False),
            "\n".join(requirements or []),
        ]
    ).lower()
    return any(k.lower() in hay for k in _PERSISTENCE_KEYWORDS)


def _static_findings(manifest: dict) -> list[str]:
    """Deterministic convention checks (no LLM)."""
    findings: list[str] = []
    feature = str(manifest.get("feature") or "")
    if not re.fullmatch(r"[a-z0-9_]+", feature):
        findings.append(f"feature スラッグが英小文字（[a-z0-9_]）でない: '{feature}'")

    if (manifest.get("kind") or "app") != "app":
        return findings

    html = manifest.get("html") or ""
    if "localStorage" in html or "sessionStorage" in html:
        findings.append("禁止 API: localStorage/sessionStorage を使用（保存は AF.load/AF.save を使う）")
    if "document.cookie" in html:
        findings.append("禁止: cookie を使用")
    if re.search(r"\bfetch\s*\(", html) or "XMLHttpRequest" in html:
        findings.append("禁止: 外部通信（fetch / XMLHttpRequest）を使用")
    if re.search(r"""(?:src|href)\s*=\s*["']https?://""", html, re.I):
        findings.append("禁止: 外部 CDN / 外部リソースの読み込み（自己完結にする）")

    theme = manifest.get("theme")
    if theme not in _ALLOWED_THEMES:
        findings.append(f"theme が規定外: '{theme}'（default/warm/forest/ocean のみ）")

    commands = manifest.get("commands") or []
    state_mode = str(manifest.get("worker_state_mode") or "commands")
    state_schema = manifest.get("state_schema") or {}
    if state_mode not in {"commands", "state", "hybrid"}:
        findings.append(f"worker_state_mode が規定外: '{state_mode}'（commands/state/hybrid のみ）")
    if state_mode in {"state", "hybrid"}:
        if not isinstance(state_schema, dict) or not state_schema:
            findings.append("worker_state_mode が state/hybrid なのに state_schema が無い（専門ワーカーが未知アプリの状態を安全に編集できない）")
        if "AF.load" not in html or "AF.save" not in html:
            findings.append("worker_state_mode が state/hybrid なのに HTML が AF.load()/AF.save() の状態保存に結びついていない")
        if not str(manifest.get("worker_instructions") or "").strip():
            findings.append("worker_state_mode が state/hybrid なのに worker_instructions が無い")
        if not manifest.get("worker_examples"):
            findings.append("worker_state_mode が state/hybrid なのに worker_examples が無い")
    if commands and "applyAgentCommand" not in html:
        findings.append("commands を宣言しているが window.applyAgentCommand が未実装（操作が効かない）")
    if commands and not str(manifest.get("worker_instructions") or "").strip():
        findings.append(
            "commands があるのに worker_instructions が無い"
            "（専門ワーカーが自然言語の意図、APIの使い分け、聞き返し方を判断しにくい）"
        )
    if commands and not manifest.get("worker_examples"):
        findings.append(
            "commands があるのに worker_examples が無い"
            "（ユーザーが言いそうな操作指示とAPI対応例を生成過程に含める必要がある）"
        )
    return findings


def review(manifest: dict, goal: str, design_plan: dict | None = None,
           requirements: list[str] | None = None) -> dict:
    """Review a generated manifest: conventions (static + LLM) AND fit to the
    user's need — the approved design plan / the feature's pinned requirements."""
    findings = _static_findings(manifest)
    if (manifest.get("kind") or "app") == "app" and _requires_persistence(goal, design_plan, requirements):
        html = manifest.get("html") or ""
        if "AF.load" not in html or "AF.save" not in html:
            findings.append(
                "状態を持つミニアプリなのに AF.load()/AF.save() によるサーバ側保存が無い"
                "（画面遷移・リロード後に途中状態を復元できない）"
            )

    llm = get_llm()
    if llm.enabled:
        try:
            # Send the FULL html so the reviewer judges the real artifact. (Slicing
            # it caused false "HTML が途中で切れている" findings on larger apps.) If an
            # app is pathologically large, cap it but mark the cut so the reviewer
            # doesn't mistake our truncation for a broken (unterminated) document.
            html = manifest.get("html")
            if isinstance(html, str) and len(html) > 100000:
                html = html[:100000] + "\n<!-- …(以下はサイズ上限で省略。末尾の閉じタグ有無で『途中で切れている』と判断しないこと) -->"
            slim = {**manifest, "html": html} if isinstance(manifest.get("html"), str) else dict(manifest)
            parts = [
                agents.load("reviewer"),
                agents.policy(),
                f"ユーザー要求: {goal}",
            ]
            if design_plan:
                parts.append("ユーザーが承認した設計案（実装はこれに一致すべき）:\n"
                             + json.dumps(design_plan, ensure_ascii=False))
            if requirements:
                parts.append("確定要求台帳（公開済みの確定事項。壊していたら指摘）:\n"
                             + "\n".join(f"・{r}" for r in requirements[:30]))
            parts += [
                "生成物(JSON):\n" + json.dumps(slim, ensure_ascii=False),
                '規約違反・設計/要求との不一致だけを JSON で返す: {"findings": ["<日本語>", ...]}（無ければ空配列・JSON のみ）',
            ]
            prompt = "\n\n".join(parts)
            raw = llm.generate(prompt, tier=ModelTier.FLASH).strip()
            if raw.startswith("```"):
                raw = raw.strip("`").split("\n", 1)[-1]
            data = json.loads(raw)
            for f in data.get("findings", []):
                if str(f).strip():
                    findings.append(str(f).strip())
        except Exception:  # noqa: BLE001 — LLM/parse failure: keep deterministic findings
            pass

    return {"verdict": "needs_revision" if findings else "ok", "findings": findings}
