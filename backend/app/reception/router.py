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
from app.models.orchestrator import PlanRequest
from app.models.reception import ChatMessage, MessageIn, ReceptionReply
from app.orchestrator import service as orchestrator
from app.reception import service

router = APIRouter(prefix="/api/reception", tags=["reception"])


@router.get("/health")
def reception_health() -> dict:
    return {"status": "ok", "module": "reception"}


@router.post("/messages", response_model=ReceptionReply)
def post_message(body: MessageIn) -> ReceptionReply:
    conversation_id = service.conversation_id_for(body.project_id)
    service.append_message(conversation_id, ChatMessage(role="user", text=body.text))

    intent = service.classify(body.text)
    task_id: str | None = None
    approval_id: str | None = None
    activated_feature: str | None = None
    disabled_feature: str | None = None

    if intent == "approve":
        pending = approvals.find_latest_pending(body.project_id)
        if pending:
            res = approvals.approve(pending["approval_id"])
            activated_feature = res["feature"]
            approval_id = pending["approval_id"]
            label = service.feature_label(activated_feature)
            reply_text = f"承認しました。「{label}」を有効化しました。右のパネルで使えます。"
        else:
            reply_text = "承認できる保留中の計画がありません。先に「タスク管理を追加して」などで機能追加を依頼してください。"

    elif intent == "rollback":
        disabled = approvals.disable_active_features(body.project_id)
        if disabled:
            disabled_feature = disabled[0]
            labels = "、".join(service.feature_label(f) for f in disabled)
            reply_text = f"「{labels}」を無効化しました（ロールバック）。データは保持しています。"
        else:
            reply_text = "無効化できる有効な機能がありません。"

    elif intent.startswith("build_feature:"):
        result = orchestrator.plan_and_register(
            PlanRequest(project_id=body.project_id, goal=body.text)
        )
        reply_text = result.summary
        task_id = result.task_id
        approval_id = result.approval_id

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
    )
