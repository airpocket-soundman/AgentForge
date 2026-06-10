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
    if commands and "applyAgentCommand" not in html:
        findings.append("commands を宣言しているが window.applyAgentCommand が未実装（操作が効かない）")
    return findings


def review(manifest: dict, goal: str) -> dict:
    """Review a generated manifest. Deterministic checks + LLM pass."""
    findings = _static_findings(manifest)

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
            prompt = "\n\n".join([
                agents.load("reviewer"),
                agents.policy(),
                f"ユーザー要求: {goal}",
                "生成物(JSON):\n" + json.dumps(slim, ensure_ascii=False),
                '規約違反・問題点だけを JSON で返す: {"findings": ["<日本語>", ...]}（無ければ空配列・JSON のみ）',
            ])
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
