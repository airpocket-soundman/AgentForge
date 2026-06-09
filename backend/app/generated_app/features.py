"""Feature-level managing AI worker (standard spec).

Every generated feature gets a managing worker exposed as an instruction chat on
the feature screen. The chat is GENERAL purpose (not fix-only): the worker either
answers conversationally OR — when the user asks to change the feature — forwards
the request into the SAME app-design pipeline the main chat uses. The Orchestrator
(not this module) decides create-vs-edit; the user's text flows through verbatim,
so intent is preserved. The resulting preview + 反映 surface from the shared
pipeline state (conversation flow), shown in place on the feature screen.

Conversation is stored in feature_chats/{project}_{feature}. The worker can be
turned off per feature (feature_states.{feature}_worker = false).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app import agents
from app.control_plane.approvals import require_feature_active
from app.firestore import get_db
from app.llm.gateway import ModelTier, get_llm
from app.models.reception import ChatMessage
from app.models.tasks import FeatureWorkerIn, Task

router = APIRouter(prefix="/api/app/features", tags=["generated-app:feature-worker"])

_VIEWS = "generated_views"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chat_ref(project_id: str, feature: str):
    return get_db().collection("feature_chats").document(f"{project_id}_{feature}")


def _manifest(project_id: str, feature: str) -> dict:
    snap = get_db().collection(_VIEWS).document(f"{project_id}_{feature}").get()
    return (snap.to_dict() or {}) if snap.exists else {}


def _worker_enabled(project_id: str, feature: str) -> bool:
    snap = get_db().collection("feature_states").document(project_id).get()
    if not snap.exists:
        return False
    data = snap.to_dict()
    return data.get(feature) == "active" and data.get(f"{feature}_worker", True) is not False


def _append(project_id: str, feature: str, *messages: ChatMessage) -> None:
    from google.cloud import firestore  # local import keeps module import cheap

    _chat_ref(project_id, feature).set(
        {
            "messages": firestore.ArrayUnion([m.model_dump(mode="json") for m in messages]),
            "updated_at": _now_iso(),
        },
        merge=True,
    )


@router.get("/{feature}/worker")
def get_worker(feature: str, project_id: str = "default") -> dict:
    require_feature_active(project_id, feature)
    doc = _chat_ref(project_id, feature).get()
    data = doc.to_dict() if doc.exists else {}
    return {"enabled": _worker_enabled(project_id, feature), "messages": data.get("messages", [])}


@router.post("/{feature}/worker/messages")
def post_worker_message(feature: str, body: FeatureWorkerIn) -> dict:
    require_feature_active(body.project_id, feature)
    if not _worker_enabled(body.project_id, feature):
        raise HTTPException(status_code=409, detail="この機能のAIワーカーは無効です")

    from app.reception import service as reception

    snap = _chat_ref(body.project_id, feature).get()
    history = snap.to_dict().get("messages", []) if snap.exists else []
    user_msg = ChatMessage(role="user", text=body.text)

    # A build/design is already running on the shared pipeline → stay responsive.
    if reception.current_build(body.project_id).get("status") == "designing":
        busy = ChatMessage(
            role="assistant",
            text="ただいま前の指示を反映中です。完了するとプレビューが表示されます。少しお待ちください。",
        )
        _append(body.project_id, feature, user_msg, busy)
        return {"reply": busy.model_dump(mode="json"), "building": True, "created": []}

    # The `task` feature keeps its deterministic create-tasks operation.
    if feature == "task":
        reply_text, created = _respond_task(body.project_id, body.text, history)
        reply = ChatMessage(role="assistant", text=reply_text)
        _append(body.project_id, feature, user_msg, reply)
        return {"reply": reply.model_dump(mode="json"), "building": False, "created": created}

    # Generated app feature: forward to the SHARED pipeline. The Orchestrator
    # decides create-vs-edit-vs-chat; the user's text is passed through verbatim.
    extra_text, images = reception.split_attachments(body.attachments)
    res = reception.handle_request(
        body.project_id, body.text + extra_text, images=images, hint_feature=feature
    )
    if res["action"] == "edit":
        reply = ChatMessage(
            role="assistant",
            text="承知しました。変更版を作成しています。完了したら下のプレビューで確認し、「反映」できます。",
        )
        _append(body.project_id, feature, user_msg, reply)
        return {"reply": reply.model_dump(mode="json"), "building": True, "created": []}
    if res["action"] == "create":
        reply = ChatMessage(
            role="assistant",
            text="新しい機能の作成として受け付けました。メインチャットに設計案を表示します。",
        )
        _append(body.project_id, feature, user_msg, reply)
        return {"reply": reply.model_dump(mode="json"), "building": True, "created": []}

    if res["action"] == "rate_limited":
        reply = ChatMessage(
            role="assistant",
            text="短時間に実行が集中しています。トークン保護のため一時停止しました。少し待ってからお試しください。",
        )
        _append(body.project_id, feature, user_msg, reply)
        return {"reply": reply.model_dump(mode="json"), "building": False, "created": []}

    # Conversational: answer with the feature worker's base prompt.
    reply = ChatMessage(role="assistant", text=_chat_reply(feature, body.text, history, _manifest(body.project_id, feature)))
    _append(body.project_id, feature, user_msg, reply)
    return {"reply": reply.model_dump(mode="json"), "building": False, "created": []}


# --- worker logic ------------------------------------------------------------

def _chat_reply(feature: str, text: str, history: list[dict], manifest: dict) -> str:
    """A conversational answer from the feature worker (no feature change)."""
    base = agents.load("feature_worker")
    llm = get_llm()
    if not llm.enabled:
        return f"（機能ワーカー・スタブ）承りました：{text}"
    prompt = (
        f"{base}\n\n"
        f"対象の機能: {manifest.get('title') or feature}（slug: {feature}）\n"
        f"説明: {manifest.get('description', '')}\n"
        f"直近の会話: {json.dumps(history[-6:], ensure_ascii=False)}\n"
        f"ユーザーの指示: {text}\n\n"
        "これは機能の変更ではなく、質問・相談・使い方への応答です。簡潔な日本語で答えてください。"
    )
    try:
        return llm.generate(prompt, tier=ModelTier.FLASH).strip() or "承知しました。"
    except Exception:  # noqa: BLE001
        return "（処理中に問題が発生しました。言い換えてお試しください）"


def _create_tasks(project_id: str, titles: list[str]) -> list[dict]:
    created = []
    for title in titles:
        if not title:
            continue
        task_id = f"t_{uuid.uuid4().hex[:12]}"
        task = Task(task_id=task_id, project_id=project_id, title=title)
        get_db().collection("app_tasks").document(task_id).set(task.model_dump(mode="json"))
        created.append({"task_id": task_id, "title": title})
    return created


def _respond_task(project_id: str, text: str, history: list[dict]) -> tuple[str, list[dict]]:
    gemini = get_llm()
    base = agents.load("feature_worker")
    tasks = [
        d.to_dict()
        for d in get_db().collection("app_tasks").where("project_id", "==", project_id).stream()
    ]
    task_titles = [t.get("title", "") for t in tasks]
    if not gemini.enabled:
        return (f"（機能ワーカー・スタブ）承りました：{text}（現在{len(task_titles)}件）", [])
    prompt = (
        f"{base}\n\n"
        "あなたはタスク管理機能の管理AIワーカーです。ユーザーの指示に応じて運用を支援します。\n"
        "タスクを新規追加すべき指示なら create_tasks にタイトル配列を入れてください（不要なら空配列）。\n"
        f"現在のタスク: {json.dumps(task_titles, ensure_ascii=False)}\n"
        f"直近の会話: {json.dumps(history[-6:], ensure_ascii=False)}\n"
        f"ユーザーの指示: {text}\n\n"
        'JSONのみで出力: {"reply": "<日本語の短い返答>", "create_tasks": ["<title>", ...]}'
    )
    try:
        raw = gemini.generate(prompt, tier=ModelTier.FLASH).strip()
        if raw.startswith("```"):
            raw = raw.strip("`").split("\n", 1)[-1]
        data = json.loads(raw)
        created = _create_tasks(project_id, data.get("create_tasks", []) or [])
        reply = str(data.get("reply", "")).strip()
        if created:
            reply += f"（{len(created)}件のタスクを追加しました）"
        return reply, created
    except Exception:  # noqa: BLE001
        return "（指示の処理中に問題が発生しました。言い換えてお試しください）", []
