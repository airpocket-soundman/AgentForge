"""Reception module — Phase 1.

Responsibilities (per IMPLEMENTATION_GUIDE.md Phase 1):
- Accept a chat message from the Web Shell over REST.
- Persist the conversation to Firestore (the browser subscribes to it live).
- Reply immediately with a lightweight, deterministic response.

Gemini (Flash) and the Orchestrator hand-off are wired in Phase 2; until then the
reply is templated so the whole loop is exercisable against the Firestore emulator
without any API key.
"""
from fastapi import APIRouter

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
    """Store the user's message, generate a reply, store it, and return both.

    On an app-building intent, hand off to the Orchestrator: generate a work plan
    and register it (pending) in the Control Plane, then summarise it back.
    """
    conversation_id = service.conversation_id_for(body.project_id)

    user_msg = ChatMessage(role="user", text=body.text)
    service.append_message(conversation_id, user_msg)

    intent = service.detect_intent(body.text)
    task_id: str | None = None
    approval_id: str | None = None

    if intent and intent.startswith("build_feature:"):
        result = orchestrator.plan_and_register(
            PlanRequest(project_id=body.project_id, goal=body.text)
        )
        reply_text = result.summary
        task_id = result.task_id
        approval_id = result.approval_id
    else:
        reply_text = service.compose_reply(body.text, intent)

    assistant_msg = ChatMessage(role="assistant", text=reply_text)
    service.append_message(conversation_id, assistant_msg)

    return ReceptionReply(
        conversation_id=conversation_id,
        reply=assistant_msg,
        detected_intent=intent,
        task_id=task_id,
        approval_id=approval_id,
    )
