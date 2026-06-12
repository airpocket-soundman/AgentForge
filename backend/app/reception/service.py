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
from contextlib import contextmanager
from datetime import datetime, timezone

from app.control_plane import registry, worker_status
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
_STAGE_CONFIRM = "confirm"  # Receptor restated the request; awaiting user OK to dispatch
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


# Timeout 3-choice replies (workers.html §3(b)): ② wait / ③ stop & retry.
_WAIT_KEYWORDS = ("もう少し待", "もうすこし待", "待つ", "まつ", "待ち", "待って", "そのまま", "継続", "続けて", "続行", "wait", "②")
_RETRY_KEYWORDS = ("再トライ", "リトライ", "やり直", "やりなお", "再試行", "もう一回", "もういちど", "再生成", "retry", "③")


def is_wait(text: str) -> bool:
    t = _normalize_short(text)
    return len(t) <= 20 and any(k in t for k in _WAIT_KEYWORDS)


def is_retry(text: str) -> bool:
    t = _normalize_short(text)
    return len(t) <= 20 and any(k in t for k in _RETRY_KEYWORDS)


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


# Worker chat (app chat) on/off is a deterministic FEATURE-LEVEL flag (has_worker),
# not a code edit — the Receptor flips it directly. Detect NL instructions for it.
_WORKER_WORDS = ("ワーカーチャット", "ワーカー", "aiワーカー", "ワーカーパネル", "チャットパネル", "チャット欄")
_WORKER_OFF = ("不要", "いらない", "要らない", "消して", "削除", "非表示", "外して", "オフ", "off", "なくして", "省いて", "隠して")
_WORKER_ON = ("付けて", "つけて", "表示して", "表示に", "オンに", " on", "出して", "有効", "ほしい", "欲しい")


def worker_toggle_intent(text: str) -> bool | None:
    """True=show / False=hide / None=not a worker-chat toggle instruction."""
    t = text.lower()
    if not any(w in t for w in _WORKER_WORDS):
        return None
    if any(w in t for w in _WORKER_OFF):
        return False
    if any(w in t for w in _WORKER_ON):
        return True
    return None


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
    _set_build(conversation_id, status=_BUILD_DESIGNING, phase="editing", goal=instruction, started_at=_now_iso(), model=_model_for_phase("editing"), timeout_count=0, prompt_pending=False)
    threading.Thread(
        target=_run_edit, args=(project_id, feature, instruction, images), daemon=True
    ).start()


def _run_edit(
    project_id: str, feature: str, instruction: str, images: list[dict] | None = None
) -> None:
    """Receptor → Orchestrator 'edit' over the MCP-like bus (see _run_codegen)."""
    conversation_id = conversation_id_for(project_id)
    from app.control_plane import worker_bus
    from app.workers import ui_designer

    corr = f"edit_{uuid.uuid4().hex[:12]}"  # correlation id for the bus message thread

    def _do_edit(_payload: dict) -> dict:
        _progress(conversation_id, "✏️ 修正版を生成しています…")
        snap = get_db().collection("generated_views").document(f"{project_id}_{feature}").get()
        cur = (snap.to_dict() or {}) if snap.exists else {}
        plan = {
            "feature": feature,
            "title": cur.get("title") or feature,
            "theme": cur.get("theme", "default"),
        }
        cur_html = cur.get("html") or None

        reqs = registry.get_requirements(project_id, feature)  # pinned past requirements

        def _build(extra: str | None = None):
            from app.llm.gateway import get_llm

            instr = instruction if not extra else (
                f"{instruction}\n\n[前回の検証・レビュー指摘（必ず修正すること）]\n{extra}"
            )
            # Patch-first: targeted SEARCH/REPLACE against the current code (fast,
            # no unrelated regressions). Vision edits (images) need full context →
            # skip straight to the full rewrite. Any patch miss falls back too.
            if cur_html and not images:
                with _llm_heartbeat(conversation_id, "✏️ 差分修正"):
                    m = ui_designer.design_patch(instr, cur, requirements=reqs)
                if m is not None:
                    _progress(conversation_id, "🧩 差分パッチを適用しました")
                    return m
                _progress(conversation_id, "↩️ 差分にできない変更のため、全体を再生成します…")
            with _llm_heartbeat(conversation_id, "✏️ 修正版生成"):
                m = ui_designer.design(instr, plan=plan, current_html=cur_html, images=images, requirements=reqs)
            if m.generated_by == "stub" and get_llm().enabled:  # failed → auto-retry once (visible)
                _progress(conversation_id, "⚠️ 生成に失敗しました → 自動リトライします…")
                with _llm_heartbeat(conversation_id, "✏️ 修正版生成（リトライ）"):
                    m = ui_designer.design(instr, plan=plan, current_html=cur_html, images=images, requirements=reqs)
            return m

        manifest = _build()
        passed, gates = _run_gates(conversation_id, instruction, manifest.model_dump(mode="json"), corr, requirements=reqs)
        attempts = 1
        while not passed and attempts < _GATE_MAX_ATTEMPTS:
            attempts += 1
            _progress(conversation_id, f"↩️ 指摘を反映して再生成しています…（{attempts}回目）")
            manifest = _build(_gate_feedback(gates))
            passed, gates = _run_gates(conversation_id, instruction, manifest.model_dump(mode="json"), corr, requirements=reqs)

        cand = manifest.model_dump(mode="json")
        if passed:
            _set_flow(conversation_id, stage=_STAGE_BUILT, mode="edit",
                      goal=instruction, feature=feature, candidate=cand)
            _progress(conversation_id, _check_report(cand))
            append_message(conversation_id, ChatMessage(role="assistant", text=(
                f"✏️「{plan['title']}」の修正版を作成しました（検証・レビュー通過）。下のプレビューで確認できます。\n"
                "問題なければ「反映して」で更新します。"
            )))
            return {"status": "ok", "result": {"passed": True, "feature": feature}}

        # Not verified → NOT publishable. Don't enable 「反映して」; keep the live
        # version untouched. The user can re-issue the edit instruction.
        _set_flow(conversation_id, stage=_STAGE_IDLE)
        _progress(conversation_id, _check_report(cand))
        if manifest.generated_by == "stub":
            text = (
                f"❌「{plan['title']}」の修正版を生成できませんでした（LLM に到達できていない可能性）。\n"
                "claude ブリッジ（:8765）を確認のうえ、もう一度「直して」と指示してください。現状の版はそのままです。"
            )
        else:
            text = (
                f"❌「{plan['title']}」の修正版が要件を満たせませんでした（未完成のため公開しません）:\n" + _gate_feedback(gates) + "\n"
                "もう一度、直したい点を具体的に指示してください。現状の版はそのままです。"
            )
        append_message(conversation_id, ChatMessage(role="assistant", text=text))
        return {"status": "needs_revision",
                "result": {"passed": False, "feature": feature},
                "findings": [_gate_feedback(gates)]}

    rep = worker_bus.dispatch(
        task_id=corr, sender="Receptor", to="Orchestrator", intent="edit",
        payload={"feature": feature, "instruction": instruction}, handler=_do_edit,
        project_id=project_id, model=_model_for_phase("editing"),
    )
    if rep.get("status") == "failed":
        append_message(
            conversation_id,
            ChatMessage(role="assistant", text=f"❌ 修正版の作成中にエラーが発生しました: {(rep.get('error') or '')[:200]}"),
        )
        _set_build(conversation_id, status=_BUILD_ERROR, error=(rep.get("error") or "")[:300])
        return
    _set_build(conversation_id, status=_BUILD_DONE)
    if rep.get("status") == "ok":
        worker_status.record_status("Orchestrator", project_id, worker_status.STOPPED,
                                    detail="修正版の公開待ち（「反映して」）")
    else:
        worker_status.record_status("Orchestrator", project_id, worker_status.IDLE,
                                    detail="修正失敗・再指示待ち")


# --- Preview (built-stage) revision loop --------------------------------------
# At the preview stage the user could previously only 「反映して」 or cancel; a
# tweak required publishing first. Now a substantive message revises the CANDIDATE
# (regenerate → gate → re-preview) — the live/published version stays untouched.

def start_candidate_revision(project_id: str, instruction: str, images: list[dict] | None = None) -> None:
    conversation_id = conversation_id_for(project_id)
    _set_build(conversation_id, status=_BUILD_DESIGNING, phase="editing", goal=instruction,
               started_at=_now_iso(), model=_model_for_phase("editing"), timeout_count=0, prompt_pending=False)
    threading.Thread(target=_run_candidate_revision, args=(project_id, instruction, images), daemon=True).start()


def _run_candidate_revision(project_id: str, instruction: str, images: list[dict] | None = None) -> None:
    conversation_id = conversation_id_for(project_id)
    from app.control_plane import worker_bus
    from app.workers import ui_designer

    flow = get_flow(project_id)
    cand = flow.get("candidate") or {}
    feature = flow.get("feature") or cand.get("feature") or ""
    mode = flow.get("mode", "create")
    corr = f"rev_{uuid.uuid4().hex[:12]}"

    def _do_revise(_payload: dict) -> dict:
        from app.llm.gateway import get_llm

        _progress(conversation_id, "✏️ プレビューを修正しています…")
        plan = {"feature": feature, "title": cand.get("title") or feature, "theme": cand.get("theme", "default")}
        cur_html = cand.get("html") or None
        reqs = registry.get_requirements(project_id, feature) if feature else []

        def _build(extra: str | None = None):
            instr = instruction if not extra else (
                f"{instruction}\n\n[前回の検証・レビュー指摘（必ず修正すること）]\n{extra}"
            )
            if cur_html and not images:  # patch-first (see _run_edit)
                with _llm_heartbeat(conversation_id, "✏️ 差分修正"):
                    m = ui_designer.design_patch(instr, cand, requirements=reqs)
                if m is not None:
                    _progress(conversation_id, "🧩 差分パッチを適用しました")
                    return m
                _progress(conversation_id, "↩️ 差分にできない変更のため、全体を再生成します…")
            with _llm_heartbeat(conversation_id, "✏️ 修正版生成"):
                m = ui_designer.design(instr, plan=plan, current_html=cur_html, images=images, requirements=reqs)
            if m.generated_by == "stub" and get_llm().enabled:  # failed → auto-retry once
                _progress(conversation_id, "⚠️ 生成に失敗しました → 自動リトライします…")
                with _llm_heartbeat(conversation_id, "✏️ 修正版生成（リトライ）"):
                    m = ui_designer.design(instr, plan=plan, current_html=cur_html, images=images, requirements=reqs)
            return m

        manifest = _build()
        passed, gates = _run_gates(conversation_id, instruction, manifest.model_dump(mode="json"), corr, requirements=reqs)
        attempts = 1
        while not passed and attempts < _GATE_MAX_ATTEMPTS:
            attempts += 1
            _progress(conversation_id, f"↩️ 指摘を反映して再生成しています…（{attempts}回目）")
            manifest = _build(_gate_feedback(gates))
            passed, gates = _run_gates(conversation_id, instruction, manifest.model_dump(mode="json"), corr, requirements=reqs)

        if not passed:
            # Keep the EXISTING candidate (flow untouched); just report.
            append_message(conversation_id, ChatMessage(role="assistant", text=(
                "❌ プレビューの修正が要件を満たせなかったため、プレビューは前のままです:\n"
                + _gate_feedback(gates) + "\n別の言い方で指示するか、「反映して」（現状のまま公開）/「キャンセル」を選べます。"
            )))
            return {"status": "needs_revision", "result": {"passed": False, "feature": feature},
                    "findings": [_gate_feedback(gates)]}

        new_cand = manifest.model_dump(mode="json")
        if mode == "create" and feature:
            # 「反映して」(approve) activates the generated_views doc — keep it in
            # sync with the revised candidate so what's published is what's previewed.
            get_db().collection("generated_views").document(f"{project_id}_{feature}").set(
                {**new_cand, "project_id": project_id, "status": "pending", "updated_at": _now_iso()},
                merge=True,
            )
        _set_flow(conversation_id, stage=_STAGE_BUILT, mode=mode, goal=flow.get("goal"),
                  plan=flow.get("plan"), feature=feature, approval_id=flow.get("approval_id"),
                  candidate=new_cand)
        _progress(conversation_id, _check_report(new_cand))
        append_message(conversation_id, ChatMessage(role="assistant", text=(
            "✏️ プレビューを修正しました（検証・レビュー通過）。更新版を確認のうえ、"
            "よければ「反映して」、さらに直す点があれば続けて指示してください。"
        )))
        return {"status": "ok", "result": {"passed": True, "feature": feature}}

    rep = worker_bus.dispatch(
        task_id=corr, sender="Receptor", to="Orchestrator", intent="edit",
        payload={"feature": feature, "instruction": instruction, "target": "candidate"},
        handler=_do_revise, project_id=project_id, model=_model_for_phase("editing"),
    )
    if rep.get("status") == "failed":
        append_message(conversation_id, ChatMessage(
            role="assistant", text=f"❌ プレビュー修正でエラーが発生しました: {(rep.get('error') or '')[:200]}"))
        _set_build(conversation_id, status=_BUILD_ERROR, error=(rep.get("error") or "")[:300])
        return
    _set_build(conversation_id, status=_BUILD_DONE)
    worker_status.record_status("Orchestrator", project_id, worker_status.STOPPED,
                                detail="プレビュー公開待ち（「反映して」）")


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


def handle_request_bg(
    project_id: str, goal: str, images: list[dict] | None = None, hint_feature: str | None = None
) -> None:
    """Run classify+route on a background thread so the Receptor can answer instantly.

    Classification calls an LLM, so doing it synchronously made the 'immediate' ack
    slow. The Receptor now acknowledges at once; this thread classifies and either
    kicks the build (which posts its own progress) or posts a chat reply."""
    threading.Thread(
        target=_handle_request_worker, args=(project_id, goal, images, hint_feature), daemon=True
    ).start()


def _handle_request_worker(
    project_id: str, goal: str, images: list[dict] | None, hint_feature: str | None
) -> None:
    conversation_id = conversation_id_for(project_id)
    from app.orchestrator import service as orchestrator

    # Keep a build record "designing" while the Receptor classifies / writes its
    # restatement (both call an LLM), so the chat keeps polling and shows the result.
    _set_build(conversation_id, status=_BUILD_DESIGNING, phase="receiving", goal=goal,
               started_at=_now_iso(), model=_model_for_phase("planning"), timeout_count=0, prompt_pending=False)
    try:
        decision = orchestrator.classify_request(project_id, goal, hint_feature=hint_feature)
        action = decision.get("action")
        feature = decision.get("feature")
        note = (decision.get("context_note") or "").strip()
        pipeline_goal = f"{goal}\n\n[文脈（過去の会話から補足）] {note}" if note else goal
        if action in ("edit", "create"):
            # Don't dispatch yet — the Receptor restates what it will ask the
            # Orchestrator and waits for the user's OK (then start_confirm path).
            _start_confirm(project_id, action, feature, pipeline_goal, images=images)
        else:
            append_message(conversation_id, ChatMessage(role="assistant", text=_receptor_chat(project_id, goal)))
    except Exception as exc:  # noqa: BLE001
        append_message(
            conversation_id,
            ChatMessage(role="assistant", text=f"受付の処理中にエラーが発生しました: {str(exc)[:200]}"),
        )
    finally:
        _set_build(conversation_id, status=_BUILD_DONE)


# --- Restate & confirm BEFORE dispatching to the Orchestrator -----------------
# The Receptor consolidates the request, restates it for the user, and only on the
# user's OK does it dispatch (start_plan / start_edit). Stored on the flow at
# stage="confirm": mode=action(create|edit), feature=edit target, goal=instruction.

def _start_confirm(project_id: str, action: str, feature: str | None, goal: str,
                   images: list[dict] | None = None) -> None:
    conversation_id = conversation_id_for(project_id)
    restate = _confirm_restatement(project_id, action, feature, goal)
    # Keep attachments with the pending request so they survive to dispatch.
    _set_flow(conversation_id, stage=_STAGE_CONFIRM, mode=action, goal=goal, feature=feature)
    if images:
        get_db().collection(_COLLECTION).document(conversation_id).set(
            {"flow": {"pending_images": images}}, merge=True
        )
    append_message(conversation_id, ChatMessage(role="assistant", text=restate))


def start_confirm_bg(project_id: str, action: str, feature: str | None, goal: str) -> None:
    """Re-run the restatement in the background (used when the user revises at the
    confirm stage), so the HTTP reply stays instant."""
    threading.Thread(target=_start_confirm, args=(project_id, action, feature, goal), daemon=True).start()


def _confirm_restatement(project_id: str, action: str, feature: str | None, goal: str) -> str:
    """The Receptor's restatement of what it will ask the Orchestrator + a request
    to confirm. LLM-generated (its own words); minimal fallback when offline."""
    from app import agents
    from app.llm.gateway import ModelTier, get_llm

    target = (f"既存機能「{feature_title(project_id, feature)}」の改修"
              if action == "edit" and feature else "新しい機能の作成")
    llm = get_llm()
    if llm.enabled:
        prompt = (
            f"{agents.load('reception')}\n\n"
            "あなたは受付（Receptor）。これから制作チーム（Orchestrator）に渡す依頼内容を、"
            "ユーザーに復唱して確認します。次の依頼を1〜3文で具体的に要約して復唱し、最後に必ず\n"
            "『この内容で制作を依頼してよいですか？修正があれば教えてください。よければ「お願い」とお送りください。』\n"
            "と添えてください。誇張や勝手な追加はせず、ユーザーの意図に忠実に。\n\n"
            f"種別: {target}\n依頼（原文＋文脈）:\n{goal}\n\n受付の復唱:"
        )
        try:
            out = llm.generate(prompt, tier=ModelTier.FLASH).strip()
            if out:
                return out
        except Exception:  # noqa: BLE001
            pass
    return (
        f"承知しました。次の内容で進めます（{target}）:\n{goal}\n\n"
        "この内容で制作を依頼してよいですか？修正があれば教えてください。よければ「お願い」とお送りください。"
    )


def dispatch_confirmed(project_id: str) -> dict:
    """Dispatch the confirmed request to the Orchestrator (called on the user's OK
    at the confirm stage). Returns {"action", "feature"}."""
    flow = get_flow(project_id)
    action = flow.get("mode")
    feature = flow.get("feature")
    instruction = flow.get("goal") or ""
    snap = get_db().collection(_COLLECTION).document(conversation_id_for(project_id)).get()
    images = ((snap.to_dict() or {}).get("flow") or {}).get("pending_images") if snap.exists else None
    clear_flow(project_id)  # reset; start_* will set the build/flow
    if action == "edit" and feature:
        start_edit(project_id, feature, instruction, images=images)
        return {"action": "edit", "feature": feature}
    start_plan(project_id, instruction, images=images)
    return {"action": "create", "feature": None}


def _receptor_chat(project_id: str, text: str) -> str:
    """Receptor's conversational reply — LLM-generated (its own words), not a fixed
    template. Falls back to a minimal line only when no LLM is reachable."""
    from app import agents
    from app.llm.gateway import ModelTier, get_llm

    llm = get_llm()
    if llm.enabled:
        snap = get_db().collection(_COLLECTION).document(conversation_id_for(project_id)).get()
        msgs = (snap.to_dict() or {}).get("messages", []) if snap.exists else []
        history = "\n".join(f"{m.get('role')}: {(m.get('text') or '')[:160]}" for m in msgs[-6:]) or "（履歴なし）"
        _states = _active_features(project_id)
        _meta = ("_worker", "_theme", "_title")
        feats = "、".join(
            _states.get(f"{k}_title") or k
            for k, v in _states.items()
            if v == "active" and not any(k.endswith(s) for s in _meta) and k not in ("updated_at", "last_changed_feature")
        ) or "（まだ無し）"
        prompt = (
            f"{agents.load('reception')}\n\n"
            "あなたは受付AIワーカー（Receptor）。軽い処理のみで即応し、ユーザーと自然に簡潔に会話します。\n"
            "重要な役割：ユーザーの意図が『機能の作成・改変』っぽいが、まだ**何を・どう**するかが具体的でないときは、"
            "いきなり制作チーム（Orchestrator）に投げず、**具体化する質問を返す**。\n"
            "  例:『タスク管理を変更できますか？』→『できます。どこをどう変えたいですか？（例：項目の追加、表示順、"
            "色分け、集計の追加 など）』のように、選択肢を添えて尋ねる。\n"
            "十分に具体的（作るもの/変える箇所と内容が明確）になったら、『では◯◯を作ります／直します』と確認し、"
            "ユーザーがそれで良ければ実際の作業に入る、と伝える。\n"
            "ただの雑談・質問にはそのまま簡潔に答える。定型文の繰り返しは避ける。\n\n"
            f"現在ある機能: {feats}\n直近の会話:\n{history}\n\nユーザー: {text}\n受付の返答:"
        )
        try:
            out = llm.generate(prompt, tier=ModelTier.FLASH).strip()
            if out:
                return out
        except Exception:  # noqa: BLE001
            pass
    return compose_reply(text, None)


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
    "receiving": "受付（依頼の整理）",
    "planning": "設計案",
    "revising": "修正後の設計案",
    "codegen": "コード",
    "editing": "修正版",
}

# Stall judgment is SILENCE-based: "time since the last sign of life (heartbeat)",
# NOT total elapsed time. Total scales with project size/difficulty and with
# healthy gate-revision rounds, so a fixed total mis-judges complex builds; any
# healthy step emits a progress heartbeat within one LLM call, so silence doesn't.
# Budgets exceed one silent step's worst case (a single PRO call can take minutes;
# its read-timeout is 600s — silence beyond budget×factor means the call would
# have died anyway). These never auto-kill: the user decides ①stop/②wait/③retry.
_SILENCE_BUDGET = {"receiving": 120, "planning": 150, "revising": 150, "codegen": 480, "editing": 480}
_STUCK_FACTOR = 1.5


def _silence_health(phase: str | None, since_sec: float) -> str:
    """Pure: health from silence (sec since last heartbeat) vs the phase budget."""
    budget = _SILENCE_BUDGET.get(phase or "planning", 300)
    if since_sec > budget * _STUCK_FACTOR:
        return "stuck"
    if since_sec > budget:
        return "slow"
    return "progressing"


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

    Judges health from SILENCE — time since the last heartbeat (every progress
    line the pipeline posts also refreshes the build record) vs the phase's
    silence budget. Total time is reported but never drives the judgment: it
    legitimately grows with project size and gate-revision rounds.
    """
    build = current_build(project_id)
    status = build.get("status") or "idle"
    phase = build.get("phase")
    goal = build.get("goal", "")
    if status != _BUILD_DESIGNING:
        health = status if status in ("error", "done") else "idle"
        return {"status": status, "phase": phase, "goal": goal, "health": health,
                "total_sec": 0, "since_update_sec": 0,
                "last_activity": build.get("last_activity"), "error": build.get("error")}
    total = int(_age_sec(build.get("started_at") or build.get("updated_at")))
    since = int(_age_sec(build.get("updated_at")))
    health = _silence_health(phase, since)
    # Cross-check the EXECUTOR's liveness (worker registry). The heartbeat updates
    # both records, so "build silent + Orchestrator not active" means the process
    # is gone (e.g. a dev reload / crash) — report stuck immediately instead of
    # claiming "順調" until a silence budget expires.
    executor_alive = True
    try:
        for w in worker_status.list_workers(project_id):
            if w.get("worker_type") == "Orchestrator":
                executor_alive = (w.get("status") == "active" and not w.get("stale"))
                break
        else:
            executor_alive = False
    except Exception:  # noqa: BLE001 — registry read failure shouldn't break diagnosis
        pass
    if not executor_alive:
        health = "stuck"
    return {"status": status, "phase": phase, "goal": goal,
            "health": health, "executor_alive": executor_alive,
            "total_sec": total, "since_update_sec": since,
            "last_activity": build.get("last_activity"), "error": build.get("error")}


def recover_orphaned_builds() -> int:
    """Startup reaper: any build still 'designing' when the PROCESS starts is an
    orphan by definition (its threads died with the previous process — e.g. a dev
    reload or a crash). Mark it failed, tell the user honestly, and stop the
    executor's status record so chat and monitor agree from t=0."""
    n = 0
    try:
        for doc in get_db().collection(_COLLECTION).stream():
            data = doc.to_dict() or {}
            build = data.get("build") or {}
            if build.get("status") != _BUILD_DESIGNING:
                continue
            cid = doc.id
            pid = cid[len("conv_"):] if cid.startswith("conv_") else cid
            _set_build(cid, status=_BUILD_ERROR, error="backend restart interrupted the build",
                       prompt_pending=False)
            worker_status.record_status("Orchestrator", pid, worker_status.STOPPED,
                                        detail="再起動により中断")
            append_message(cid, ChatMessage(role="assistant", text=(
                "⚠️ システムの再起動により、進行中の作業が中断されました（生成物は公開されていません）。\n"
                "お手数ですが「これで作って」または依頼の再送で再開できます（設計案・要求は保持しています）。"
            )))
            n += 1
    except Exception:  # noqa: BLE001 — startup must never fail because of the reaper
        pass
    return n


def recover_build(project_id: str, reason: str = "") -> None:
    """Release a stuck/cancelled background build so the chat isn't locked forever."""
    _set_build(conversation_id_for(project_id), status=_BUILD_ERROR, error=(reason[:300] or "recovered"))


# Timeout (stall) control — Receptor judges and the USER decides (workers.html §3b).
_TIMEOUT_FORCE_STOP_N = 2  # after N timeouts, Receptor force-stops and just reports


def bump_timeout(project_id: str) -> int:
    """Record one more timeout judgment for the running build; return the new count."""
    n = int(current_build(project_id).get("timeout_count", 0)) + 1
    _set_build(conversation_id_for(project_id), timeout_count=n)
    return n


def mark_prompted(project_id: str) -> None:
    """A ①②③ prompt is now awaiting the user's answer (suppresses re-prompts)."""
    _set_build(conversation_id_for(project_id), prompt_pending=True)


def extend_wait(project_id: str) -> None:
    """② もう少し待つ: clear the pending prompt. The write itself refreshes the
    heartbeat (updated_at), so the silence clock restarts — the next stall
    judgment will be #2 and force-stops."""
    _set_build(conversation_id_for(project_id), prompt_pending=False)


def _stall_decision(health: str, prompt_pending: bool, timeout_count: int) -> str:
    """Pure: what the Receptor should do on a watch tick.

    Returns "none" (healthy, or a prompt is already awaiting the user's answer),
    "prompt" (post the ①②③ choices), or "force_stop" (this judgment reaches N)."""
    if health not in ("slow", "stuck") or prompt_pending:
        return "none"
    return "force_stop" if timeout_count + 1 >= _TIMEOUT_FORCE_STOP_N else "prompt"


def _pipeline_snapshot(diag: dict) -> str:
    """One-line, user-readable state of the pipeline at judgment time (透明性):
    which stage, what it was last doing, and how long it has been silent."""
    what = _PHASE_LABELS.get(diag.get("phase"), "作業")
    last = (diag.get("last_activity") or "").strip()
    head = f"工程: {what}" + (f" ／ 最後の動き: 「{last}」" if last else "")
    return f"{head}（{diag.get('since_update_sec', 0)}秒 応答なし・全体 {diag.get('total_sec', 0)}秒）"


def _timeout_prompt_text(diag: dict) -> str:
    return (
        "⏱ パイプラインの応答が途絶えている可能性があります。\n"
        f"{_pipeline_snapshot(diag)}\n"
        "どうしますか？ ①「停止」／ ②「もう少し待つ」／ ③「停止して再トライ」"
    )


def _force_stop_text(count: int, diag: dict) -> str:
    return (
        f"{count} 回タイムアウトしたため、安全のため強制停止しました。\n"
        f"{_pipeline_snapshot(diag)}\n"
        "直前のプランは保持しています。もう一度ご依頼ください。"
    )


def judge_stall_on_poll(project_id: str) -> None:
    """Proactive stall watch (VISION 柱5): runs on the chat's state poll, so the
    Receptor judges and speaks WITHOUT waiting for the user to say something.
    Poll-driven means it naturally pauses while the app is closed (spec: 閉鎖中は
    休止) and needs no resident watchdog thread."""
    build = current_build(project_id)
    if build.get("status") != _BUILD_DESIGNING:
        return
    diag = diagnose_build(project_id)
    decision = _stall_decision(
        diag["health"], bool(build.get("prompt_pending")), int(build.get("timeout_count", 0))
    )
    if decision == "none":
        return
    conversation_id = conversation_id_for(project_id)
    # Mark first to keep concurrent poll ticks (multiple tabs) from double-posting.
    _set_build(conversation_id, prompt_pending=True)
    count = bump_timeout(project_id)
    if decision == "force_stop" or count >= _TIMEOUT_FORCE_STOP_N:
        recover_build(project_id, f"force-stop after {count} timeouts")
        append_message(conversation_id, ChatMessage(role="assistant", text=_force_stop_text(count, diag)))
    else:
        append_message(conversation_id, ChatMessage(role="assistant", text=_timeout_prompt_text(diag)))


def retry_build(project_id: str) -> str:
    """③ stop & retry: stop the current run and re-kick it from the last good stage
    (reuses the saved flow — design proposal / approved plan are not thrown away)."""
    build = current_build(project_id)
    phase = build.get("phase")
    recover_build(project_id, "user retry")
    flow = get_flow(project_id)
    goal = flow.get("goal") or build.get("goal") or ""
    if phase == "codegen" and flow.get("plan"):
        start_codegen(project_id, goal, flow["plan"])
        return "codegen"
    if phase == "editing" and flow.get("feature"):
        start_edit(project_id, flow["feature"], goal)
        return "editing"
    start_plan(project_id, goal)
    return "planning"


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
    alive = diag.get("executor_alive", True)
    facts = (
        f"- 対象: {goal[:80] or '（不明）'}\n"
        f"- 現在のフェーズ: {what}（{diag.get('phase')}）\n"
        f"- 最後の動き: {(diag.get('last_activity') or '（記録なし）')[:80]}\n"
        f"- 経過: 全体 {total}秒／最後の動きから {since}秒（判定は無音時間ベース）\n"
        f"- 実行ワーカー(Orchestrator)の生存記録: {'あり（稼働中）' if alive else '途絶（プロセス停止の可能性大）'}\n"
        f"- 自動判定: {health}（progressing=順調 / slow=応答が遅い / stuck=停止の可能性）\n"
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
            "誇張や断定のしすぎはしないこと。**残り時間・完了見込み（『あと◯分』等）を推測して言わない**"
            "（根拠が無い）。実行ワーカーの生存記録が『途絶』の場合は、絶対に『順調』と言わず、"
            "停止している可能性が高いことと「停止して再トライ」を案内すること。\n\n"
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
    crit = ""
    if plan.acceptance:
        crit = "受け入れ条件（完成時に Tester が1つずつ検証します）:\n" + \
               "\n".join(f"・{c}" for c in plan.acceptance) + "\n\n"
    return (
        f"🧩 設計案：{plan.title}\n"
        f"{plan.summary}\n\n"
        f"主な機能:\n{bullets}\n\n"
        f"{crit}"
        f"データ保存: {save} ／ テーマ: {plan.theme}\n\n"
        f"このプランで良ければ「これで作って」と送ってください（コードを生成します）。\n"
        f"修正したい点があれば、その内容をそのまま返信してください（例：「色を増やして」「保存も付けて」）。"
    )


# --- Stage 1: design proposal (fast) ----------------------------------------

def _progress(conversation_id: str, text: str) -> None:
    """Post a build progress/check line to the chat (role=system) AND heartbeat the
    build record (last_activity + updated_at): every visible step both informs the
    user and proves the pipeline is alive — stall judgment is silence-based, so a
    long build that keeps reporting never gets mis-judged as stalled."""
    append_message(conversation_id, ChatMessage(role="system", text=text))
    _set_build(conversation_id, last_activity=text[:80])


@contextmanager
def _llm_heartbeat(conversation_id: str, label: str):
    """Keep the heartbeat fresh DURING a long LLM call: a single PRO call can be
    minutes of silence, which the stall watch would otherwise flag. Awaiting the
    call is a legitimate liveness signal (the call itself is bounded by the LLM
    read-timeout, so a hung bridge still surfaces as `failed`). Writes only the
    build record — no chat spam."""
    stop = threading.Event()
    project_id = conversation_id[len("conv_"):] if conversation_id.startswith("conv_") else conversation_id

    def _beat() -> None:
        n = 0
        while not stop.wait(45):
            n += 1
            try:
                _set_build(conversation_id, last_activity=f"{label}（実行中・約{n * 45}秒）")
                # Single source of truth: the SAME liveness signal feeds the worker
                # registry, so the status monitor and the Receptor's judgment can
                # never tell different stories about the executor.
                worker_status.record_status("Orchestrator", project_id, worker_status.ACTIVE,
                                            detail=f"{label}（実行中）")
            except Exception:  # noqa: BLE001 — a transient write must not kill the beat
                pass

    t = threading.Thread(target=_beat, daemon=True)
    t.start()
    try:
        yield
    finally:
        stop.set()


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
    _set_build(conversation_id, status=_BUILD_DESIGNING, phase=phase, goal=goal, started_at=_now_iso(), model=_model_for_phase(phase), timeout_count=0, prompt_pending=False)
    threading.Thread(
        target=_run_plan, args=(project_id, goal, feedback, previous, images), daemon=True
    ).start()


def _run_plan(
    project_id: str, goal: str, feedback: str | None, previous: dict | None, images: list[dict] | None = None
) -> None:
    """Receptor → Orchestrator 'plan' over the MCP-like bus (see _run_codegen)."""
    conversation_id = conversation_id_for(project_id)
    from app.control_plane import worker_bus
    from app.workers import ui_designer

    corr = f"plan_{uuid.uuid4().hex[:12]}"

    def _do_plan(_payload: dict) -> dict:
        _progress(conversation_id, "📝 設計案を作成しています…")
        with _llm_heartbeat(conversation_id, "📝 設計案作成"):
            plan = ui_designer.plan_feature(goal, feedback=feedback, previous=previous, images=images)
        plan_dict = plan.model_dump(mode="json")
        # Screen mock (SVG) at the PLAN stage: the user reviews/corrects the look
        # BEFORE any expensive PRO code is written; a revision just redraws this
        # in seconds. Best-effort — "" means the plan proceeds without a mock.
        _progress(conversation_id, "🎨 画面イメージ（モック）を作成しています…")
        with _llm_heartbeat(conversation_id, "🎨 モック作成"):
            mock = ui_designer.design_mock(goal, plan_dict)
        if mock:
            plan_dict["mock_svg"] = mock
        _set_flow(
            conversation_id,
            stage=_STAGE_PLAN,
            goal=goal,
            plan=plan_dict,
            feature=plan.feature,
        )
        append_message(conversation_id, ChatMessage(role="assistant", text=_format_plan(plan)))
        if mock:
            # The mock is a normal chat message with an inline SVG image — it sits
            # in the conversation flow right under the proposal.
            append_message(conversation_id, ChatMessage(
                role="assistant", svg=mock,
                text="🎨 画面イメージ（モック・コード作成前）です。見た目・構成の修正は、コードを書く前の今が最も手早く反映できます。",
            ))
        return {"status": "ok", "result": {"feature": plan.feature}}

    rep = worker_bus.dispatch(
        task_id=corr, sender="Receptor", to="Orchestrator", intent="plan",
        payload={"goal": goal, "revision": bool(feedback)}, handler=_do_plan,
        project_id=project_id, model=_model_for_phase("planning"),
    )
    if rep.get("status") == "failed":
        append_message(
            conversation_id,
            ChatMessage(role="assistant", text=f"❌ 設計案の作成中にエラーが発生しました: {(rep.get('error') or '')[:200]}"),
        )
        _set_build(conversation_id, status=_BUILD_ERROR, error=(rep.get("error") or "")[:300])
        return
    _set_build(conversation_id, status=_BUILD_DONE)
    worker_status.record_status("Orchestrator", project_id, worker_status.IDLE,
                                detail="設計案の承認待ち（「これで作って」）")


# --- Stage 2: code generation from the approved plan ------------------------

def start_codegen(project_id: str, goal: str, plan: dict) -> None:
    """Generate the real HTML app from the approved plan in the background."""
    conversation_id = conversation_id_for(project_id)
    _set_build(conversation_id, status=_BUILD_DESIGNING, phase="codegen", goal=goal, started_at=_now_iso(), model=_model_for_phase("codegen"), timeout_count=0, prompt_pending=False)
    threading.Thread(
        target=_run_codegen, args=(project_id, goal, plan), daemon=True
    ).start()


# --- Deploy-time gate: Tester (runs / meets intent) + Reviewer (conventions) ---
# Phase 1 bounds the quality loop; Phase 4 replaces the bound with the
# timeout-based, user-controlled stop (workers.html §3(b)).
_GATE_MAX_ATTEMPTS = 2


def _run_gates(conversation_id: str, goal: str, manifest: dict, task_id: str,
               criteria: list[str] | None = None, design_plan: dict | None = None,
               requirements: list[str] | None = None) -> tuple[bool, dict]:
    """Run Tester + Reviewer on a generated manifest; post the result to chat.

    The two are independent, so run them concurrently to halve the gate's latency.
    `criteria` = the plan's user-approved acceptance list (Tester verifies each);
    `design_plan` / `requirements` let the Reviewer judge fit-to-need (the approved
    design / the feature's pinned requirements), not just conventions."""
    from concurrent.futures import ThreadPoolExecutor

    from app.control_plane import worker_bus
    from app.workers import reviewer, tester

    project_id = conversation_id[len("conv_"):] if conversation_id.startswith("conv_") else conversation_id
    flash = _model_for_phase("planning")  # gates run on FLASH
    payload = {"manifest": manifest, "goal": goal, "criteria": criteria or [],
               "design_plan": design_plan, "requirements": requirements or []}
    _progress(conversation_id, "🔎 Tester（動作検証）と Reviewer（規約・設計適合レビュー）を実行中…")

    # Orchestrator dispatches verify/review to Tester/Reviewer over the MCP-like bus
    # (request/report logged + correlated by task_id; recipient status via the bus).
    def _verify(p):
        return worker_bus.gate_report_fields(tester.verify(p["manifest"], p["goal"], criteria=p.get("criteria") or None))

    def _review(p):
        return worker_bus.gate_report_fields(reviewer.review(
            p["manifest"], p["goal"], design_plan=p.get("design_plan"),
            requirements=p.get("requirements") or None))

    with ThreadPoolExecutor(max_workers=2) as ex:
        t_fut = ex.submit(worker_bus.dispatch, task_id=task_id, sender="Orchestrator", to="Tester",
                          intent="verify", payload=payload, handler=_verify, project_id=project_id, model=flash)
        r_fut = ex.submit(worker_bus.dispatch, task_id=task_id, sender="Orchestrator", to="Reviewer",
                          intent="review", payload=payload, handler=_review, project_id=project_id, model=flash)
        t_rep, r_rep = t_fut.result(), r_fut.result()

    tv = t_rep.get("result") or {}
    rv = r_rep.get("result") or {}
    passed = t_rep.get("status") == "ok" and r_rep.get("status") == "ok"
    _progress(conversation_id, _gate_report(tv, rv))
    return passed, {"tester": tv, "reviewer": rv}


def _gate_report(tv: dict, rv: dict) -> str:
    t = "✅" if tv.get("verdict") == "pass" else "⚠️"
    r = "✅" if rv.get("verdict") == "ok" else "⚠️"
    lines = [f"🔎 動作検証 {t} ／ 規約レビュー {r}"]
    # Per-criterion results (the user-approved acceptance list) — itemized ✅/❌.
    for c in tv.get("criteria", []):
        mark = "✅" if c.get("ok") else "❌"
        note = f"（{c['note']}）" if (not c.get("ok") and c.get("note")) else ""
        lines.append(f"・[条件] {mark} {c.get('text', '')}{note}")
    for e in tv.get("errors", []):
        if str(e).startswith("受け入れ条件NG"):
            continue  # already shown above as a ❌ criterion line
        lines.append(f"・[動作] {e}")
    for f in rv.get("findings", []):
        lines.append(f"・[規約] {f}")
    return "\n".join(lines)


def _gate_feedback(gates: dict) -> str:
    items = [f"[動作] {e}" for e in gates["tester"].get("errors", [])]
    items += [f"[規約] {f}" for f in gates["reviewer"].get("findings", [])]
    return "\n".join(items) or "（指摘なし）"


def _run_codegen(project_id: str, goal: str, plan: dict) -> None:
    """Receptor → Orchestrator 'build' over the MCP-like bus. The handler is the
    Orchestrator's work (generate → gate → register); the bus logs the request/
    report (correlated by `corr`, same thread as the inner verify/review) and
    drives the recipient's active→stopped status. A raised handler becomes a
    `failed` report, which the Receptor turns into the user-facing error."""
    conversation_id = conversation_id_for(project_id)
    from app.control_plane import worker_bus
    from app.models.orchestrator import PlanRequest
    from app.orchestrator import service as orchestrator

    req = PlanRequest(project_id=project_id, goal=goal)
    corr = f"build_{uuid.uuid4().hex[:12]}"  # correlation id for the bus message thread
    # The mock SVG was for plan-stage review only — don't waste codegen-prompt
    # tokens on it (the textual plan + acceptance carry the agreed design).
    plan = {k: v for k, v in (plan or {}).items() if k != "mock_svg"}
    criteria = plan.get("acceptance") or None  # user-approved acceptance list

    def _gen(feedback: str | None = None):
        """One generation; on a stub result (LLM unreachable/parse failure) retry
        once automatically — visible to the user, per spec (failed → auto-retry)."""
        from app.llm.gateway import get_llm

        with _llm_heartbeat(conversation_id, "🛠 コード生成"):
            m = orchestrator.build_app(req, design_plan=plan, feedback=feedback)
        if m.generated_by == "stub" and get_llm().enabled:
            _progress(conversation_id, "⚠️ 生成に失敗しました → 自動リトライします…")
            with _llm_heartbeat(conversation_id, "🛠 コード生成（リトライ）"):
                m = orchestrator.build_app(req, design_plan=plan, feedback=feedback)
        return m

    def _do_build(_payload: dict) -> dict:
        from app.workers import ui_designer

        _progress(conversation_id, "🛠 AIワーカーがコードを生成しています…")
        manifest = _gen()
        passed, gates = _run_gates(conversation_id, goal, manifest.model_dump(mode="json"), corr, criteria=criteria, design_plan=plan)
        attempts = 1
        while not passed and attempts < _GATE_MAX_ATTEMPTS:
            attempts += 1
            # Repair pass: fix the cited issues with targeted patches first (fast,
            # no unrelated regressions); fall back to a full regeneration.
            _progress(conversation_id, f"↩️ 指摘を反映して修正しています…（{attempts}回目・まず差分パッチ）")
            with _llm_heartbeat(conversation_id, "🛠 差分修正"):
                patched = ui_designer.design_patch(goal, manifest.model_dump(mode="json"),
                                                   feedback=_gate_feedback(gates))
            if patched is not None:
                _progress(conversation_id, "🧩 差分パッチを適用しました")
                manifest = patched
            else:
                _progress(conversation_id, "↩️ 差分にできない変更のため、全体を再生成します…")
                manifest = _gen(_gate_feedback(gates))
            passed, gates = _run_gates(conversation_id, goal, manifest.model_dump(mode="json"), corr, criteria=criteria, design_plan=plan)

        if passed:
            # Only a verified result is publishable: register it and offer 「反映して」.
            result = orchestrator.register_app(req, manifest)
            feat = result.plan.feature
            snap = get_db().collection("generated_views").document(f"{project_id}_{feat}").get()
            candidate = snap.to_dict() if snap.exists else None
            _set_flow(
                conversation_id, stage=_STAGE_BUILT, mode="create", goal=goal, plan=plan,
                feature=feat, approval_id=result.approval_id, candidate=candidate,
            )
            _progress(conversation_id, _check_report(candidate))
            append_message(conversation_id, ChatMessage(role="assistant", text=(
                "✅ 検証・レビューを通過しました。下のプレビューで動作を確認できます。\n"
                "問題なければ「反映して」で公開します（左メニューに追加されます）。"
            )))
            return {"status": "ok", "result": {"passed": True, "feature": feat}}

        # Not verified → NOT publishable. Do not register or offer 「反映して」.
        # Stay at the plan stage so the user can retry (「これで作って」) or redirect.
        _set_flow(conversation_id, stage=_STAGE_PLAN, goal=goal, plan=plan, feature=manifest.feature)
        if manifest.generated_by == "stub":
            text = (
                "❌ うまく生成できませんでした（AI ワーカー＝LLM に到達できていない可能性）。\n"
                "claude ブリッジ（:8765）が起動しているか確認のうえ、「これで作って」で再試行してください。"
            )
        else:
            text = (
                "❌ 生成物が要件を満たせませんでした（未完成のため公開はできません）:\n" + _gate_feedback(gates) + "\n"
                "「これで作って」で作り直すか、設計を変えたい点を返信してください。"
            )
        append_message(conversation_id, ChatMessage(role="assistant", text=text))
        return {"status": "needs_revision",
                "result": {"passed": False, "feature": manifest.feature},
                "findings": [_gate_feedback(gates)]}

    rep = worker_bus.dispatch(
        task_id=corr, sender="Receptor", to="Orchestrator", intent="build",
        payload={"goal": goal, "design_plan": plan}, handler=_do_build,
        project_id=project_id, model=_model_for_phase("codegen"),
    )
    if rep.get("status") == "failed":
        append_message(
            conversation_id,
            ChatMessage(role="assistant", text=f"❌ コード生成でエラーが発生しました: {(rep.get('error') or '')[:200]}"),
        )
        _set_build(conversation_id, status=_BUILD_ERROR, error=(rep.get("error") or "")[:300])
        return
    _set_build(conversation_id, status=_BUILD_DONE)
    if rep.get("status") == "ok":
        worker_status.record_status("Orchestrator", project_id, worker_status.STOPPED,
                                    detail="プレビュー公開待ち（「反映して」）")
    else:
        worker_status.record_status("Orchestrator", project_id, worker_status.IDLE,
                                    detail="生成失敗・再試行待ち")


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
