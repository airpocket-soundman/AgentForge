"""Safety Harness — unified safety gate for generated mini-app artifacts.

This module is intentionally deterministic. Reviewer and Tester can include LLM
judgment, but Safety Harness is the final mechanical gate that decides whether a
candidate is safe enough to become preview/publishable.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

_FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\blocalStorage\b|\bsessionStorage\b", "禁止 API: localStorage/sessionStorage（保存は AF.load/AF.save）"),
    (r"\bdocument\.cookie\b", "禁止 API: document.cookie"),
    (r"\bfetch\s*\(", "禁止 API: fetch"),
    (r"\bXMLHttpRequest\b", "禁止 API: XMLHttpRequest"),
    (r"\bWebSocket\s*\(", "禁止 API: WebSocket"),
    (r"\bEventSource\s*\(", "禁止 API: EventSource"),
    (r"\bnavigator\.sendBeacon\s*\(", "禁止 API: navigator.sendBeacon"),
    (r"\bwindow\.open\s*\(", "禁止 API: window.open"),
    (r"\beval\s*\(", "禁止 API: eval"),
    (r"\bnew\s+Function\s*\(", "禁止 API: new Function"),
    (r"\bimportScripts\s*\(", "禁止 API: importScripts"),
)

_EXTERNAL_RESOURCE_RE = re.compile(r"""(?:src|href|action)\s*=\s*["']https?://""", re.I)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_verdict_ok(value: Any, ok_value: str) -> bool:
    return isinstance(value, dict) and value.get("verdict") == ok_value


def inspect_manifest(manifest: dict) -> tuple[list[str], list[str]]:
    """Return (checks, findings) for deterministic safety-only checks."""
    checks: list[str] = []
    findings: list[str] = []

    if (manifest.get("kind") or "app") != "app":
        checks.append("非 HTML アプリ: sandbox HTML 検査は対象外")
        return checks, findings

    html = str(manifest.get("html") or "")
    low = html.lower()
    if "<!doctype html" in low and "</html>" in low:
        checks.append("完結 HTML")
    else:
        findings.append("完結した HTML 文書ではない")

    if "<script" in low:
        checks.append("script は iframe sandbox 内でのみ実行")
    else:
        findings.append("script が無く、アプリ操作が実装されていない可能性")

    for pattern, message in _FORBIDDEN_PATTERNS:
        if re.search(pattern, html, re.I):
            findings.append(message)

    if _EXTERNAL_RESOURCE_RE.search(html):
        findings.append("禁止: 外部 URL を src/href/action で読み込んでいる")
    else:
        checks.append("外部リソース参照なし")

    if "target=\"_blank\"" in low or "target='_blank'" in low:
        findings.append("禁止: 別ウィンドウ遷移 target=_blank")

    commands = manifest.get("commands") or []
    state_mode = manifest.get("worker_state_mode") or "commands"
    if commands:
        if "applyAgentCommand" in html:
            checks.append("commands と applyAgentCommand の操作面あり")
        else:
            findings.append("commands があるが applyAgentCommand が無い")

    if state_mode in {"state", "hybrid"}:
        if manifest.get("state_schema"):
            checks.append(f"state_schema あり（{state_mode}）")
        else:
            findings.append(f"worker_state_mode={state_mode} だが state_schema が無い")
        if "AF.load" in html and "AF.save" in html:
            checks.append("AF.load/AF.save による保存復元あり")
        else:
            findings.append(f"worker_state_mode={state_mode} だが AF.load/AF.save に結びついていない")

    if commands or state_mode in {"state", "hybrid"}:
        if manifest.get("worker_eval_cases"):
            checks.append("worker_eval_cases あり")
        else:
            findings.append("worker_eval_cases が無い")
        if str(manifest.get("clarification_policy") or "").strip():
            checks.append("clarification_policy あり")
        else:
            findings.append("clarification_policy が無い")
        if str(manifest.get("dangerous_action_policy") or "").strip():
            checks.append("dangerous_action_policy あり")
        else:
            findings.append("dangerous_action_policy が無い")

    return checks, findings


def evaluate(
    manifest: dict,
    *,
    project_id: str | None = None,
    task_id: str | None = None,
    approval_id: str | None = None,
    goal: str = "",
    tester_result: dict | None = None,
    reviewer_result: dict | None = None,
    persist: bool = True,
) -> dict:
    """Combine deterministic checks + Tester/Reviewer results into one verdict."""
    checks, findings = inspect_manifest(manifest)
    if tester_result is not None:
        if _as_verdict_ok(tester_result, "pass"):
            checks.append("Tester gate pass")
        else:
            findings.append("Tester gate failed")
    if reviewer_result is not None:
        if _as_verdict_ok(reviewer_result, "ok"):
            checks.append("Reviewer gate ok")
        else:
            findings.append("Reviewer gate needs_revision")

    result = {
        "verdict": "fail" if findings else "pass",
        "checks": checks,
        "findings": findings,
        "project_id": project_id,
        "task_id": task_id,
        "approval_id": approval_id,
        "feature": manifest.get("feature"),
        "title": manifest.get("title"),
        "goal": goal[:500],
        "created_at": _now_iso(),
    }
    if persist and (project_id or task_id or approval_id):
        save_result(result)
    return result


def save_result(result: dict) -> str:
    """Persist a Safety Harness verdict for publish-time enforcement."""
    from app.firestore import get_db

    doc_id = (
        result.get("approval_id")
        or result.get("task_id")
        or f"{result.get('project_id', 'unknown')}_{result.get('feature', 'unknown')}_{uuid.uuid4().hex[:8]}"
    )
    payload = {**result, "safety_check_id": doc_id, "updated_at": _now_iso()}
    get_db().collection("safety_checks").document(doc_id).set(payload, merge=True)
    return str(doc_id)


def merge_into_generated_view(project_id: str, feature: str, result: dict) -> None:
    """Store the verdict next to the preview candidate that will be published."""
    from app.firestore import get_db

    get_db().collection("generated_views").document(f"{project_id}_{feature}").set(
        {
            "safety_harness": result,
            "safety_verdict": result.get("verdict"),
            "safety_checked_at": _now_iso(),
        },
        merge=True,
    )


def assert_publishable(
    *,
    project_id: str,
    feature: str,
    task_id: str | None = None,
    approval_id: str | None = None,
    candidate: dict | None = None,
) -> None:
    """Raise HTTPException if a candidate has not passed Safety Harness."""
    from fastapi import HTTPException
    from app.firestore import get_db

    candidates: list[dict] = []
    if candidate:
        candidates.append(candidate.get("safety_harness") or {})

    gv = get_db().collection("generated_views").document(f"{project_id}_{feature}").get()
    if gv.exists:
        data = gv.to_dict() or {}
        candidates.append(data.get("safety_harness") or {})
        if data.get("safety_verdict"):
            candidates.append({"verdict": data.get("safety_verdict")})

    for doc_id in (approval_id, task_id):
        if doc_id:
            snap = get_db().collection("safety_checks").document(doc_id).get()
            if snap.exists:
                candidates.append(snap.to_dict() or {})

    if any(c.get("verdict") == "pass" for c in candidates):
        return
    raise HTTPException(status_code=409, detail="Safety Harness 未通過のため公開できません。再生成してください。")
