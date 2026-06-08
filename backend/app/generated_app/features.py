"""Feature-level managing AI worker (standard spec).

Every generated feature gets a managing worker exposed as an instruction chat on
the feature screen. The user operates the feature in natural language; the worker
(Gemini Flash) replies and, where applicable, performs operations via the feature's
deterministic API. For the `task` feature it can create tasks.

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
from app.llm.gemini import ModelTier, get_gemini
from app.models.reception import ChatMessage
from app.models.tasks import FeatureWorkerIn, Task

router = APIRouter(prefix="/api/app/features", tags=["generated-app:feature-worker"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chat_ref(project_id: str, feature: str):
    return get_db().collection("feature_chats").document(f"{project_id}_{feature}")


def _worker_enabled(project_id: str, feature: str) -> bool:
    snap = get_db().collection("feature_states").document(project_id).get()
    if not snap.exists:
        return False
    data = snap.to_dict()
    return data.get(feature) == "active" and data.get(f"{feature}_worker", True) is not False


@router.get("/{feature}/worker")
def get_worker(feature: str, project_id: str = "default") -> dict:
    require_feature_active(project_id, feature)
    snap = _chat_ref(project_id, feature).get()
    messages = snap.to_dict().get("messages", []) if snap.exists else []
    return {"enabled": _worker_enabled(project_id, feature), "messages": messages}


@router.post("/{feature}/worker/messages")
def post_worker_message(feature: str, body: FeatureWorkerIn) -> dict:
    require_feature_active(body.project_id, feature)
    if not _worker_enabled(body.project_id, feature):
        raise HTTPException(status_code=409, detail="この機能のAIワーカーは無効です")

    snap = _chat_ref(body.project_id, feature).get()
    history = snap.to_dict().get("messages", []) if snap.exists else []

    reply_text, created = _respond(feature, body.project_id, body.text, history)
    user_msg = ChatMessage(role="user", text=body.text)
    assistant_msg = ChatMessage(role="assistant", text=reply_text)

    from google.cloud import firestore  # local import keeps module import cheap

    _chat_ref(body.project_id, feature).set(
        {
            "messages": firestore.ArrayUnion(
                [user_msg.model_dump(mode="json"), assistant_msg.model_dump(mode="json")]
            ),
            "updated_at": _now_iso(),
        },
        merge=True,
    )
    return {"reply": assistant_msg.model_dump(mode="json"), "created": created}


# --- worker logic ------------------------------------------------------------

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


def _respond(feature: str, project_id: str, text: str, history: list[dict]) -> tuple[str, list[dict]]:
    gemini = get_gemini()
    base = agents.load("feature_worker")

    if feature == "task":
        tasks = [d.to_dict() for d in get_db().collection("app_tasks").where("project_id", "==", project_id).stream()]
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

    # Generic feature worker (conversational).
    if not gemini.enabled:
        return f"（機能ワーカー・スタブ）承りました：{text}", []
    prompt = f"{base}\n\n機能: {feature}\n直近の会話: {json.dumps(history[-6:], ensure_ascii=False)}\nユーザーの指示: {text}\n\n簡潔な日本語で返答してください。"
    try:
        return gemini.generate(prompt, tier=ModelTier.FLASH).strip(), []
    except Exception:  # noqa: BLE001
        return "（処理中に問題が発生しました）", []
