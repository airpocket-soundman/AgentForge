"""Reception module — Phase 1 + conversational control.

Responsibilities:
- Accept a chat message from the Web Shell over REST and persist it to Firestore.
- Route by intent:
    build_feature:* -> Orchestrator (generate plan + register pending)
    approve         -> Control Plane: approve the latest pending plan ("反映して")
    rollback        -> Control Plane: soft-disable active features ("戻して")
    chat            -> templated reply
- Reply immediately; the browser also subscribes to Firestore for live state.
"""
from fastapi import APIRouter

from app.control_plane import approvals
from app.models.reception import ChatMessage, MessageIn, ReceptionReply
from app.reception import service

router = APIRouter(prefix="/api/reception", tags=["reception"])


@router.get("/health")
def reception_health() -> dict:
    return {"status": "ok", "module": "reception"}


@router.get("/state/{project_id}")
def get_state(project_id: str) -> dict:
    """Full chat state for the browser to render from scratch and poll while a
    background design runs (survives navigation / reload)."""
    return service.conversation_state(project_id)


@router.get("/candidate/{project_id}")
def get_candidate(project_id: str) -> dict:
    """The generated app awaiting publish (new or edited), for the chat preview."""
    return {"manifest": service.get_candidate(project_id)}


@router.post("/messages", response_model=ReceptionReply)
def post_message(body: MessageIn) -> ReceptionReply:
    conversation_id = service.conversation_id_for(body.project_id)
    service.append_message(conversation_id, ChatMessage(role="user", text=body.text))

    # The main worker is busy: the reception worker actually INVESTIGATES the
    # pipeline (diagnose_build) instead of replying from a template, and can
    # release a chat that a dead worker left locked.
    build = service.current_build(body.project_id)
    if build.get("status") == "designing":
        diag = service.diagnose_build(body.project_id)
        # Escape hatch: cancel even while a build is running (busy-guard otherwise
        # blocks every message, including 「キャンセル」).
        if service.is_cancel(body.text):
            service.recover_build(body.project_id, "user cancelled")
            service.clear_flow(body.project_id)
            reply = ChatMessage(role="assistant", text="作業を中止しました。新しいご依頼をどうぞ。")
            service.append_message(conversation_id, reply)
            return ReceptionReply(conversation_id=conversation_id, reply=reply, detected_intent="cancel", building=False)
        # Diagnosed as stuck (no progress past the phase budget) → unlock.
        if diag["health"] == "stuck":
            service.recover_build(body.project_id, f"stuck at {diag.get('phase')} for {diag['total_sec']}s")
            reply = ChatMessage(
                role="assistant",
                text=(
                    f"{diag['total_sec']} 秒以上応答がなく、処理が停止した可能性があります。"
                    "安全のため解除しました。お手数ですが、もう一度ご依頼ください"
                    "（直前のプランは保持しています）。"
                ),
            )
            service.append_message(conversation_id, reply)
            return ReceptionReply(conversation_id=conversation_id, reply=reply, detected_intent="recovered", building=False)
        reply = ChatMessage(role="assistant", text=service.building_status_reply(body.project_id, body.text, diag))
        service.append_message(conversation_id, reply)
        return ReceptionReply(
            conversation_id=conversation_id, reply=reply, detected_intent="busy", building=True
        )

    # Attachments: text/data files are inlined into the request; images go to the
    # LLM for vision. Intent/feature resolution still keys off the typed text only.
    extra_text, images = service.split_attachments(body.attachments)
    goal_text = body.text + extra_text

    flow = service.get_flow(body.project_id)
    stage = flow.get("stage", "idle")
    intent = service.classify(body.text)
    task_id: str | None = None
    approval_id: str | None = None
    activated_feature: str | None = None
    disabled_feature: str | None = None
    building = False

    # === Stage: a design PROPOSAL is under review =========================
    if stage == "plan":
        if service.is_cancel(body.text):
            service.clear_flow(body.project_id)
            reply_text = "設計をキャンセルしました。新しく機能を依頼してください。"
        elif service.is_plan_ok(body.text):
            allowed, count = service.guard_run(body.project_id)
            if not allowed:
                reply_text = (
                    f"短時間に実行が集中しています（直近{count}回）。トークン保護のため一時停止しました。"
                    "少し待ってから「これで作って」と送ってください。"
                )
            else:
                service.start_codegen(body.project_id, flow["goal"], flow["plan"])
                building = True
                reply_text = (
                    "プランを承認しました。AIワーカーがコードを生成します（数十秒〜1分）。\n"
                    "完了するとここにプレビューが表示されます。"
                )
        else:
            # Anything else = a revision instruction; rebuild the proposal.
            service.start_plan(
                body.project_id, flow["goal"], feedback=goal_text, previous=flow["plan"], images=images
            )
            building = True
            reply_text = "修正を反映して設計案を作り直します…（数秒）"

    # === Stage: code is BUILT, awaiting publish ===========================
    elif stage == "built":
        if intent == "approve" or service.is_plan_ok(body.text):
            if flow.get("mode") == "edit":
                title = (flow.get("candidate") or {}).get("title") or service.feature_label(flow["feature"])
                res = approvals.publish_edit(body.project_id, flow["feature"], flow["candidate"])
                activated_feature = res["feature"]
                service.clear_flow(body.project_id)
                reply_text = f"「{title}」を更新しました。"
            else:
                approval_id = flow.get("approval_id")
                if not approval_id:
                    # No approval was registered for this candidate (e.g. an
                    # errored/partial codegen) — don't call approve(None).
                    service.clear_flow(body.project_id)
                    reply_text = "公開対象が見つかりませんでした。お手数ですが、もう一度ご依頼ください。"
                else:
                    res = approvals.approve(approval_id)
                    activated_feature = res["feature"]
                    service.clear_flow(body.project_id)
                    reply_text = f"公開しました。「{service.feature_title(body.project_id, activated_feature)}」を左メニューに追加しました。"
        elif service.is_cancel(body.text) or intent == "rollback":
            service.clear_flow(body.project_id)
            reply_text = "キャンセルしました（生成物は破棄しました）。"
        else:
            reply_text = "公開するには「反映して」、やめるには「キャンセル」と送ってください。"

    # === Stage: idle ======================================================
    elif intent == "approve":
        pending = approvals.find_latest_pending(body.project_id)
        if pending:
            res = approvals.approve(pending["approval_id"])
            activated_feature = res["feature"]
            approval_id = pending["approval_id"]
            reply_text = f"承認しました。「{service.feature_label(activated_feature)}」を有効化しました。"
        else:
            reply_text = "承認できる設計がありません。先に作りたい機能を伝えてください。"

    elif intent == "rollback":
        disabled = approvals.disable_active_features(body.project_id)
        if disabled:
            disabled_feature = disabled[0]
            labels = "、".join(service.feature_label(f) for f in disabled)
            reply_text = f"「{labels}」を無効化しました（ロールバック）。データは保持しています。"
        else:
            reply_text = "無効化できる有効な機能がありません。"

    else:
        # Substantive request: the ORCHESTRATOR decides new-vs-edit-vs-chat and the
        # SAME pipeline runs (create → design proposal; edit → regenerate existing).
        res = service.handle_request(body.project_id, goal_text, images=images)
        if res["action"] == "edit":
            building = True
            reply_text = f"「{service.feature_title(body.project_id, res['feature'])}」の修正版を作成しています…（数十秒）"
        elif res["action"] == "create":
            building = True
            reply_text = "設計案を作成しています…（数秒）。少しお待ちください。"
        elif res["action"] == "rate_limited":
            reply_text = (
                f"短時間に実行が集中しています（直近{res.get('count', '')}回）。"
                "トークン保護のため一時停止しました。少し待ってからもう一度お試しください。"
            )
        else:
            reply_text = service.compose_reply(body.text, None)

    assistant_msg = ChatMessage(role="assistant", text=reply_text)
    service.append_message(conversation_id, assistant_msg)

    return ReceptionReply(
        conversation_id=conversation_id,
        reply=assistant_msg,
        detected_intent=intent,
        task_id=task_id,
        approval_id=approval_id,
        activated_feature=activated_feature,
        disabled_feature=disabled_feature,
        building=building,
    )
