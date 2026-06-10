"""Reception business logic, separated from the HTTP layer so it can be unit
tested and later swapped to call Gemini Flash (Phase 2).

The Reception worker is deliberately FAST: on a build request it kicks the heavy
Orchestrator/UI-Designer work onto a background thread (the "main worker") and
returns immediately. Progress, the final summary, and the pending approval are
written to the conversation doc in Firestore, so the chat can be restored (and
keeps advancing) even if the user navigates to another screen or reloads — the
browser polls `conversation_state()` rather than holding the work in component
state.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

from app.firestore import get_db
from app.models.generated import DesignPlan
from app.models.reception import ChatMessage

# Conversation documents live under: conversations/{conversation_id}
#   conversations/{id}.messages : ordered list of {role, text, created_at}
# The browser subscribes to this doc for live updates (no backend polling).
_COLLECTION = "conversations"

# Keywords that signal an "app building" request the Orchestrator will own (P2).
_BUILD_KEYWORDS = ("追加", "作って", "つくって", "ほしい", "欲しい", "add", "create", "build")
_FEATURE_KEYWORDS = {
    "task": ("タスク", "todo", "task"),
    "pdf_memo": ("pdf", "メモ", "memo", "要約"),
}
# Conversational control commands (the spec's demo: 「反映して」承認 / 「戻して」rollback).
_APPROVE_KEYWORDS = ("反映", "承認", "approve", "apply")
_ROLLBACK_KEYWORDS = ("戻し", "戻す", "ロールバック", "rollback", "取り消", "無効化")

_FEATURE_LABELS = {"task": "タスク管理", "pdf_memo": "PDFメモ", "unknown": "ご要望の機能"}


def feature_label(feature: str) -> str:
    return _FEATURE_LABELS.get(feature, feature)


def feature_title(project_id: str, feature: str) -> str:
    """User-facing name of a feature: its stored title (e.g. 「電卓」) over the slug."""
    snap = get_db().collection("feature_states").document(project_id).get()
    states = (snap.to_dict() or {}) if snap.exists else {}
    return states.get(f"{feature}_title") or feature_label(feature)


def classify(text: str) -> str:
    """Coarse intent for Reception routing.

    A build request takes priority: a long feature description may incidentally
    contain control words (e.g. 「元に戻す」 inside a paint-tool spec), so we must
    NOT treat it as rollback. approve/rollback are standalone control commands.
    """
    intent = detect_intent(text)
    if intent:
        return intent
    if any(k in text for k in _APPROVE_KEYWORDS):
        return "approve"
    if any(k in text for k in _ROLLBACK_KEYWORDS):
        return "rollback"
    return "chat"


def conversation_id_for(project_id: str) -> str:
    """One rolling conversation per project for the MVP."""
    return f"conv_{project_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_MAX_ATTACH_TEXT = 20000
_MAX_IMAGES = 4


def split_attachments(attachments) -> tuple[str, list[dict]]:
    """Split chat attachments into (inline text block, image list for vision).

    Text/data files are inlined into the request so any provider reads them;
    images are returned as {mime, data(base64)} for the multimodal LLM path.
    """
    text_blocks: list[str] = []
    images: list[dict] = []
    for a in attachments or []:
        kind = getattr(a, "kind", "text")
        content = getattr(a, "content", "") or ""
        if kind == "image" and content:
            if len(images) < _MAX_IMAGES:
                images.append({"mime": getattr(a, "mime", "") or "image/png", "data": content})
        elif content:
            name = getattr(a, "name", "") or "file"
            text_blocks.append(f"\n\n[添付ファイル: {name}]\n{content[:_MAX_ATTACH_TEXT]}")
    return "".join(text_blocks), images


# Background-build status kept on the conversation doc so the chat survives
# navigation/reload (the browser polls instead of holding it in component state).
_BUILD_DESIGNING = "designing"
_BUILD_DONE = "done"
_BUILD_ERROR = "error"


def _set_build(conversation_id: str, **fields) -> None:
    fields.setdefault("updated_at", _now_iso())
    get_db().collection(_COLLECTION).document(conversation_id).set(
        {"build": fields}, merge=True
    )


# Heavy code generation (codegen/editing) runs on the PRO tier; lighter steps
# (planning/revising) on FLASH. Record which model is in use so the status
# monitor can show it (spec: status includes the model in use).
def _model_for_phase(phase: str) -> str:
    from app.llm.gateway import ModelTier, model_label

    tier = ModelTier.PRO if phase in ("codegen", "editing") else ModelTier.FLASH
    return model_label(tier)


# --- Two-stage flow state (stored on the conversation doc) ------------------
# stage: "idle" -> "plan" (proposal under review) -> "built" (code ready to publish)
# The user reviews/revises the PLAN in natural language; only on approval is code
# generated; a final 「反映して」 publishes (activates) it.
_STAGE_IDLE = "idle"
_STAGE_PLAN = "plan"
_STAGE_BUILT = "built"

# Short confirmations that approve the CURRENT proposal (kept short so a detailed
# revision like "色を増やして作って" is treated as feedback, not approval).
#
# Bare ASCII tokens like "ok"/"go" are matched ONLY as the whole message — as a
# substring they fire on unrelated words ("looks br-ok-en", "OK、でも色変えて"),
# which at the built stage would publish without the user actually approving.
_PLAN_OK_EXACT = {
    "ok", "okです", "okお願い", "おk", "オーケー", "go", "ゴー",
    "はい", "うん", "yes", "y", "了解", "りょうかい", "お願い", "おねがい",
}
# Unambiguous commit instructions, matched as a substring.
_PLAN_OK_PHRASES = (
    "これで作", "これでお願い", "これでいい", "これで良", "これでok", "これでオーケー",
    "作成して", "実装して", "承認", "公開して", "進めて", "これでいこ", "これで進",
)
# Likewise: a standalone cancel vs. an instruction that merely contains "やめ" as a
# substring (e.g. "やめ時がわかるタイマーを作って" must NOT abort the flow).
_CANCEL_EXACT = {
    "キャンセル", "やめる", "やめて", "やめます", "やめ", "中止", "中止して",
    "破棄", "破棄して", "取りやめ", "cancel", "やっぱやめ", "やっぱりやめる",
}
_CANCEL_PHRASES = (
    "キャンセル", "中止して", "中止に", "破棄して", "取りやめ", "やめたい",
    "やめにして", "やめましょう", "やめよう", "やっぱりやめ",
)


def _normalize_short(text: str) -> str:
    return text.strip().lower().rstrip("。．.!！?？、,　 ")


def is_plan_ok(text: str) -> bool:
    t = _normalize_short(text)
    if t in _PLAN_OK_EXACT:
        return True
    return len(t) <= 20 and any(k in t for k in _PLAN_OK_PHRASES)


def is_cancel(text: str) -> bool:
    t = _normalize_short(text)
    if t in _CANCEL_EXACT:
        return True
    return len(t) <= 20 and any(k in t for k in _CANCEL_PHRASES)


def get_flow(project_id: str) -> dict:
    snap = get_db().collection(_COLLECTION).document(conversation_id_for(project_id)).get()
    data = (snap.to_dict() or {}) if snap.exists else {}
    return data.get("flow") or {"stage": _STAGE_IDLE}


def _set_flow(conversation_id: str, **fields) -> None:
    # Write the full flow object each time so stale keys from a prior stage are
    # overwritten (Firestore deep-merges nested maps otherwise).
    flow = {
        "stage": fields.get("stage", _STAGE_IDLE),
        "mode": fields.get("mode", "create"),  # "create" | "edit"
        "goal": fields.get("goal"),
        "plan": fields.get("plan"),
        "feature": fields.get("feature"),
        "approval_id": fields.get("approval_id"),
        "candidate": fields.get("candidate"),  # generated ViewManifest dict (preview source)
        "updated_at": _now_iso(),
    }
    get_db().collection(_COLLECTION).document(conversation_id).set({"flow": flow}, merge=True)


def clear_flow(project_id: str) -> None:
    _set_flow(conversation_id_for(project_id), stage=_STAGE_IDLE)


# --- Editing an EXISTING feature --------------------------------------------
_EDIT_KEYWORDS = (
    "修正", "直し", "直して", "なおして", "変更", "編集", "改善", "変えて", "調整",
    "ように修正", "ようにして", "増やして", "減らして", "大きく", "小さく", "fix", "edit",
)


def is_edit_request(text: str) -> bool:
    return any(k in text for k in _EDIT_KEYWORDS)


def _active_features(project_id: str) -> dict:
    snap = get_db().collection("feature_states").document(project_id).get()
    return (snap.to_dict() or {}) if snap.exists else {}


def resolve_feature(project_id: str, text: str, *, allow_lone_fallback: bool = True) -> str | None:
    """Find which ACTIVE feature a message refers to, by title or slug match.

    `allow_lone_fallback`: when True and exactly one feature is active, an
    unqualified edit phrase is assumed to target it. Callers that must not let a
    NEW-feature build request hijack the only existing feature (it carries no
    explicit reference) pass False.
    """
    states = _active_features(project_id)
    actives = [
        k for k, v in states.items()
        if v == "active" and not any(k.endswith(s) for s in ("_worker", "_theme", "_title")) and k != "updated_at"
    ]
    # Prefer a title match (most natural: 「電卓を…」), then slug.
    for f in actives:
        title = states.get(f"{f}_title")
        if title and title in text:
            return f
    for f in actives:
        if f in text:
            return f
    # Exactly one active feature → assume it's the target (only when allowed).
    if allow_lone_fallback:
        return actives[0] if len(actives) == 1 else None
    return None


def start_edit(
    project_id: str, feature: str, instruction: str, images: list[dict] | None = None
) -> None:
    """Regenerate an existing feature's code with the change instruction applied."""
    conversation_id = conversation_id_for(project_id)
    _set_build(conversation_id, status=_BUILD_DESIGNING, phase="editing", goal=instruction, started_at=_now_iso(), model=_model_for_phase("editing"))
    threading.Thread(
        target=_run_edit, args=(project_id, feature, instruction, images), daemon=True
    ).start()


def _run_edit(
    project_id: str, feature: str, instruction: str, images: list[dict] | None = None
) -> None:
    conversation_id = conversation_id_for(project_id)
    from app.workers import ui_designer

    try:
        _progress(conversation_id, "✏️ 修正版を生成しています…（数十秒）")
        snap = get_db().collection("generated_views").document(f"{project_id}_{feature}").get()
        cur = (snap.to_dict() or {}) if snap.exists else {}
        plan = {
            "feature": feature,
            "title": cur.get("title") or feature,
            "theme": cur.get("theme", "default"),
        }
        manifest = ui_designer.design(
            instruction, plan=plan, current_html=cur.get("html") or None, images=images
        )
        cand = manifest.model_dump(mode="json")
        _set_flow(
            conversation_id,
            stage=_STAGE_BUILT,
            mode="edit",
            goal=instruction,
            feature=feature,
            candidate=cand,
        )
        _progress(conversation_id, _check_report(cand))
        append_message(
            conversation_id,
            ChatMessage(
                role="assistant",
                text=(
                    f"✏️「{plan['title']}」の修正版を作成しました。下のプレビューで確認できます。\n"
                    "問題なければ「反映して」で更新します。"
                ),
            ),
        )
        _set_build(conversation_id, status=_BUILD_DONE)
    except Exception as exc:  # noqa: BLE001
        append_message(
            conversation_id,
            ChatMessage(role="assistant", text=f"❌ 修正版の作成中にエラーが発生しました: {str(exc)[:200]}"),
        )
        _set_build(conversation_id, status=_BUILD_ERROR, error=str(exc)[:300])


def handle_request(
    project_id: str,
    goal: str,
    images: list[dict] | None = None,
    hint_feature: str | None = None,
) -> dict:
    """Single pipeline entry for a substantive request, from the main chat OR a
    feature screen. The ORCHESTRATOR decides create-vs-edit-vs-chat; we then run the
    SAME pipeline (start_plan for new, start_edit for existing).

    `goal` is passed through VERBATIM to the generator — classification never
    rewrites it, so the original intent is preserved while the plan/design stages
    add detail. Returns {"action", "feature", "building"}.
    """
    from app.orchestrator import service as orchestrator

    decision = orchestrator.classify_request(project_id, goal, hint_feature=hint_feature)
    action = decision.get("action")
    feature = decision.get("feature")
    # The Orchestrator read the history and may add a context note (resolved target
    # / premise). Keep the user's ORIGINAL text verbatim at the front and APPEND the
    # note — enrich without degrading. The pipeline then just executes this.
    note = (decision.get("context_note") or "").strip()
    pipeline_goal = f"{goal}\n\n[文脈（過去の会話から補足）] {note}" if note else goal
    if action in ("edit", "create"):
        # Runaway/loop guard: a heavy worker run. Trip the breaker before spending
        # PRO tokens if this project is looping (rolling run-rate cap).
        allowed, count = guard_run(project_id)
        if not allowed:
            return {"action": "rate_limited", "feature": None, "building": False, "count": count}
    if action == "edit" and feature:
        start_edit(project_id, feature, pipeline_goal, images=images)
        return {"action": "edit", "feature": feature, "building": True}
    if action == "create":
        start_plan(project_id, pipeline_goal, images=images)
        return {"action": "create", "feature": None, "building": True}
    return {"action": "chat", "feature": None, "building": False}


def guard_run(project_id: str) -> tuple[bool, int]:
    """Record a heavy worker run and report whether it's within the loop-guard cap."""
    from app.control_plane import guard

    return guard.record_and_check(project_id)


def current_build(project_id: str) -> dict:
    """The conversation's background-build record ({status, phase, goal, ...})."""
    snap = get_db().collection(_COLLECTION).document(conversation_id_for(project_id)).get()
    data = (snap.to_dict() or {}) if snap.exists else {}
    return data.get("build") or {}


_PHASE_LABELS = {
    "planning": "設計案",
    "revising": "修正後の設計案",
    "codegen": "コード",
    "editing": "修正版",
}

# Per-phase time budget (seconds). Past the budget → "slow"; well past → "stuck".
# Non-resident workers can't be pinged directly, so the build record's timestamps
# are the observable: a long gap with status still "designing" means the worker
# (or its LLM call) likely died, leaving the chat locked.
_PHASE_BUDGET = {"planning": 40, "revising": 40, "codegen": 130, "editing": 130}
_STUCK_FACTOR = 2.5


def _age_sec(iso: str | None) -> float:
    if not iso:
        return 0.0
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return 0.0
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - then).total_seconds())


def diagnose_build(project_id: str) -> dict:
    """Actually investigate the running pipeline (not a canned reply).

    Reads the build record the background worker writes and judges health from the
    elapsed time vs the phase budget: progressing / slow / stuck. Used by the
    reception worker to answer 'is it really running?' truthfully and to release a
    locked chat when a worker has clearly died.
    """
    build = current_build(project_id)
    status = build.get("status") or "idle"
    phase = build.get("phase")
    goal = build.get("goal", "")
    if status != _BUILD_DESIGNING:
        health = status if status in ("error", "done") else "idle"
        return {"status": status, "phase": phase, "goal": goal, "health": health,
                "total_sec": 0, "since_update_sec": 0, "error": build.get("error")}
    total = int(_age_sec(build.get("started_at") or build.get("updated_at")))
    since = int(_age_sec(build.get("updated_at")))
    budget = _PHASE_BUDGET.get(phase or "planning", 90)
    if total > budget * _STUCK_FACTOR:
        health = "stuck"
    elif total > budget:
        health = "slow"
    else:
        health = "progressing"
    return {"status": status, "phase": phase, "goal": goal, "health": health,
            "total_sec": total, "since_update_sec": since, "error": build.get("error")}


def recover_build(project_id: str, reason: str = "") -> None:
    """Release a stuck/cancelled background build so the chat isn't locked forever."""
    _set_build(conversation_id_for(project_id), status=_BUILD_ERROR, error=(reason[:300] or "recovered"))


def building_status_reply(project_id: str, text: str, diag: dict) -> str:
    """The reception worker INVESTIGATES the pipeline (diagnose_build) and explains
    the real situation in its own words — it reasons over the diagnostic facts with
    the reception-agent prompt, rather than emitting a fixed 'please wait' template.
    Falls back to a concise factual line only when no LLM is reachable.
    """
    what = _PHASE_LABELS.get(diag.get("phase"), "作業")
    goal = (diag.get("goal") or "").strip()
    total = diag.get("total_sec", 0)
    since = diag.get("since_update_sec", 0)
    health = diag.get("health")
    facts = (
        f"- 対象: {goal[:80] or '（不明）'}\n"
        f"- 現在のフェーズ: {what}（{diag.get('phase')}）\n"
        f"- 経過: {total}秒（最終更新から {since}秒）\n"
        f"- 自動判定: {health}（progressing=順調 / slow=想定より遅い / stuck=停止の可能性）\n"
        f"- 直近のエラー: {diag.get('error') or 'なし'}"
    )
    from app import agents
    from app.llm.gateway import ModelTier, get_llm

    llm = get_llm()
    if llm.enabled:
        prompt = (
            f"{agents.load('reception')}\n\n"
            "あなたは受付AIワーカーです。バックグラウンドで動くアプリ生成パイプラインの稼働状況を、"
            "下の診断結果に基づいて正直に説明してください。定型文は禁止。いまどの工程か、順調か/"
            "遅いか/止まっていそうか、ユーザーは待てばよいか・中止(「キャンセル」)すべきかを、"
            "2〜3文の簡潔な日本語で伝えます。stuck の場合は停止の可能性と再試行/キャンセルを案内し、"
            "誇張や断定のしすぎはしないこと。\n\n"
            f"【パイプライン診断（実測）】\n{facts}\n\n"
            f"【ユーザーの発言】{text}\n\n"
            "受付ワーカーの返答:"
        )
        try:
            out = llm.generate(prompt, tier=ModelTier.FLASH).strip()
            if out:
                return out
        except Exception:  # noqa: BLE001
            pass
    # Fallback (no LLM): still grounded in the diagnosis, not a vague template.
    if health == "slow":
        return f"稼働中です。{what}に想定より時間がかかっています（経過{total}秒）。もう少し待つか「キャンセル」で中止できます。"
    return f"稼働中です。いま{what}を生成しています（経過{total}秒・順調）。完了すると自動表示されます。中止は「キャンセル」。"


def get_candidate(project_id: str) -> dict | None:
    """The generated manifest currently awaiting publish (new or edited), for preview."""
    snap = get_db().collection(_COLLECTION).document(conversation_id_for(project_id)).get()
    data = (snap.to_dict() or {}) if snap.exists else {}
    return (data.get("flow") or {}).get("candidate")


def _format_plan(plan: DesignPlan) -> str:
    bullets = "\n".join(f"・{f}" for f in plan.features) or "・（主な機能は実装時に補完します）"
    save = "あり（再読込しても保持）" if plan.persistence else "なし"
    return (
        f"🧩 設計案：{plan.title}\n"
        f"{plan.summary}\n\n"
        f"主な機能:\n{bullets}\n\n"
        f"データ保存: {save} ／ テーマ: {plan.theme}\n\n"
        f"このプランで良ければ「これで作って」と送ってください（コードを生成します）。\n"
        f"修正したい点があれば、その内容をそのまま返信してください（例：「色を増やして」「保存も付けて」）。"
    )


# --- Stage 1: design proposal (fast) ----------------------------------------

def _progress(conversation_id: str, text: str) -> None:
    """Post a build progress/check line to the chat (role=system) so the user sees
    what the worker is doing, in real time, not just a spinner."""
    append_message(conversation_id, ChatMessage(role="system", text=text))


def _check_report(candidate: dict | None) -> str:
    """A short human-readable summary of automatic checks on a generated artifact."""
    if not candidate:
        return "🔍 チェック: 生成物が見つかりませんでした ⚠️"
    parts: list[str] = []
    gen = candidate.get("generated_by", "?")
    if gen == "stub":
        parts.append("LLM未到達で仮ページ ⚠️")
    if (candidate.get("kind") or "data") == "app":
        parts.append("HTML " + ("✅" if candidate.get("html") else "なし ⚠️"))
        cmds = candidate.get("commands") or []
        parts.append(f"操作ツール {len(cmds)}個 " + ("✅" if cmds else "⚠️"))
    else:
        parts.append(f"項目{len(candidate.get('fields') or [])}・一覧列{len(candidate.get('list_columns') or [])}")
    parts.append(f"生成元 {gen}")
    return "🔍 チェック: " + " / ".join(parts)


def start_plan(
    project_id: str,
    goal: str,
    feedback: str | None = None,
    previous: dict | None = None,
    images: list[dict] | None = None,
) -> None:
    """Generate (or revise) a design proposal in the background, then post it."""
    conversation_id = conversation_id_for(project_id)
    phase = "revising" if (feedback and previous) else "planning"
    _set_build(conversation_id, status=_BUILD_DESIGNING, phase=phase, goal=goal, started_at=_now_iso(), model=_model_for_phase(phase))
    threading.Thread(
        target=_run_plan, args=(project_id, goal, feedback, previous, images), daemon=True
    ).start()


def _run_plan(
    project_id: str, goal: str, feedback: str | None, previous: dict | None, images: list[dict] | None = None
) -> None:
    conversation_id = conversation_id_for(project_id)
    from app.workers import ui_designer

    try:
        _progress(conversation_id, "📝 設計案を作成しています…")
        plan = ui_designer.plan_feature(goal, feedback=feedback, previous=previous, images=images)
        _set_flow(
            conversation_id,
            stage=_STAGE_PLAN,
            goal=goal,
            plan=plan.model_dump(mode="json"),
            feature=plan.feature,
        )
        append_message(conversation_id, ChatMessage(role="assistant", text=_format_plan(plan)))
        _set_build(conversation_id, status=_BUILD_DONE)
    except Exception as exc:  # noqa: BLE001
        append_message(
            conversation_id,
            ChatMessage(role="assistant", text=f"❌ 設計案の作成中にエラーが発生しました: {str(exc)[:200]}"),
        )
        _set_build(conversation_id, status=_BUILD_ERROR, error=str(exc)[:300])


# --- Stage 2: code generation from the approved plan ------------------------

def start_codegen(project_id: str, goal: str, plan: dict) -> None:
    """Generate the real HTML app from the approved plan in the background."""
    conversation_id = conversation_id_for(project_id)
    _set_build(conversation_id, status=_BUILD_DESIGNING, phase="codegen", goal=goal, started_at=_now_iso(), model=_model_for_phase("codegen"))
    threading.Thread(
        target=_run_codegen, args=(project_id, goal, plan), daemon=True
    ).start()


def _run_codegen(project_id: str, goal: str, plan: dict) -> None:
    conversation_id = conversation_id_for(project_id)
    from app.models.orchestrator import PlanRequest
    from app.orchestrator import service as orchestrator

    try:
        _progress(conversation_id, "🛠 AIワーカーがコードを生成しています…（数十秒）")
        result = orchestrator.plan_and_register(
            PlanRequest(project_id=project_id, goal=goal), design_plan=plan
        )
        feat = result.plan.feature
        snap = get_db().collection("generated_views").document(f"{project_id}_{feat}").get()
        candidate = snap.to_dict() if snap.exists else None
        _set_flow(
            conversation_id,
            stage=_STAGE_BUILT,
            mode="create",
            goal=goal,
            plan=plan,
            feature=feat,
            approval_id=result.approval_id,
            candidate=candidate,
        )
        _progress(conversation_id, _check_report(candidate))
        append_message(
            conversation_id,
            ChatMessage(
                role="assistant",
                text=(
                    "✅ コードが完成しました。下のプレビューで動作を確認できます。\n"
                    "問題なければ「反映して」で公開します（左メニューに追加されます）。"
                ),
            ),
        )
        _set_build(conversation_id, status=_BUILD_DONE)
    except Exception as exc:  # noqa: BLE001
        append_message(
            conversation_id,
            ChatMessage(role="assistant", text=f"❌ コード生成でエラーが発生しました: {str(exc)[:200]}"),
        )
        _set_build(conversation_id, status=_BUILD_ERROR, error=str(exc)[:300])


def conversation_state(project_id: str) -> dict:
    """Everything the chat needs to render from scratch and poll: history, whether
    a background step is running, the current flow stage, and (at the built stage)
    the feature to preview + the approval to publish."""
    conversation_id = conversation_id_for(project_id)
    snap = get_db().collection(_COLLECTION).document(conversation_id).get()
    data = (snap.to_dict() or {}) if snap.exists else {}
    build = data.get("build") or {}
    flow = data.get("flow") or {"stage": _STAGE_IDLE}
    stage = flow.get("stage", _STAGE_IDLE)
    return {
        "conversation_id": conversation_id,
        "messages": data.get("messages", []),
        "building": build.get("status") == _BUILD_DESIGNING,
        # The work happening NOW (planning/revising/codegen/editing). The flow stage
        # stays "plan" during code generation, so the spinner must key off phase.
        "phase": build.get("phase") if build.get("status") == _BUILD_DESIGNING else None,
        "stage": stage,
        "mode": flow.get("mode", "create"),
        "pending_feature": flow.get("feature") if stage == _STAGE_BUILT else None,
        "pending_approval_id": flow.get("approval_id") if stage == _STAGE_BUILT else None,
    }


def append_message(conversation_id: str, message: ChatMessage) -> None:
    doc = get_db().collection(_COLLECTION).document(conversation_id)
    payload = message.model_dump(mode="json")
    # ArrayUnion keeps the single-doc model simple and atomic for the MVP volume.
    from google.cloud import firestore  # local import: keeps module import cheap

    doc.set(
        {"messages": firestore.ArrayUnion([payload]), "project_id": conversation_id},
        merge=True,
    )


def detect_intent(text: str) -> str | None:
    """Very small rule-based intent detector (placeholder for Gemini Flash)."""
    lowered = text.lower()
    if not any(k in lowered for k in _BUILD_KEYWORDS):
        return None
    for feature, kws in _FEATURE_KEYWORDS.items():
        if any(k in lowered for k in kws):
            return f"build_feature:{feature}"
    return "build_feature:unknown"


def compose_reply(text: str, intent: str | None) -> str:
    """Deterministic reply. Replaced by Gemini-routed responses in Phase 2."""
    if intent and intent.startswith("build_feature:"):
        feature = intent.split(":", 1)[1]
        label = {
            "task": "タスク管理",
            "pdf_memo": "PDFメモ",
            "unknown": "ご要望の",
        }.get(feature, "ご要望の")
        return (
            f"「{label}」機能の追加リクエストを受け付けました。"
            "これから設計エージェント（Orchestrator）が作業計画を作成し、"
            "進捗はこの画面にリアルタイムで表示されます。"
            "（※現在 Phase 1：Orchestrator 連携は Phase 2 で有効化されます）"
        )
    return (
        "メッセージを受け取りました。"
        "「タスク管理を追加して」のように、追加したい機能を伝えてください。"
    )
