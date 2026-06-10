"""Feature-level managing AI worker (standard spec).

DECOUPLED from the main build pipeline (decision 2026-06-09): a feature's worker
operates ONLY on that feature's CONTENT — the data/objects it holds (tasks, records,
the entities behind the view). It does NOT create or restructure features.

Changing the feature itself (its UI, fields, layout, code) is the MAIN chat's job
(the Orchestrator pipeline). If the user asks the feature worker for a structural
change, it DETECTS it and FORWARDS the request to the main chat pipeline
(Receptor → Orchestrator) so the user doesn't have to re-ask (spec G3) — a feature
never restructures itself directly, but the request isn't dropped either.

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

    snap = _chat_ref(body.project_id, feature).get()
    history = snap.to_dict().get("messages", []) if snap.exists else []
    user_msg = ChatMessage(role="user", text=body.text)

    command: dict | None = None
    # The `task` feature keeps its deterministic create-tasks operation (content op).
    if feature == "task":
        reply_text, changed = _respond_task(body.project_id, body.text, history)
    else:
        # Content-only: operate on this feature's data/objects. NEVER forwards to the
        # design pipeline — structural changes are redirected to the main chat.
        # For app-kind features, returns a `command` for the running app to execute.
        reply_text, changed, command = _respond_content(
            body.project_id, feature, body.text, history, _manifest(body.project_id, feature)
        )

    reply = ChatMessage(role="assistant", text=reply_text)
    _append(body.project_id, feature, user_msg, reply)
    return {
        "reply": reply.model_dump(mode="json"),
        "building": False,
        "created": changed,
        "data_changed": bool(changed),
        "command": command,  # app-kind: {name, args} for the live app to apply
    }


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


_ENTITIES = "app_entities"


def _apply_entity_ops(project_id: str, feature: str, ops: list[dict]) -> list[dict]:
    """Apply create/update/delete to this feature's entities (content only)."""
    db = get_db()
    changed: list[dict] = []
    for op in (ops or [])[:50]:
        kind = op.get("op")
        if kind == "create":
            eid = f"e_{uuid.uuid4().hex[:12]}"
            db.collection(_ENTITIES).document(eid).set(
                {
                    "entity_id": eid,
                    "feature": feature,
                    "project_id": project_id,
                    "data": op.get("data") or {},
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                }
            )
            changed.append({"entity_id": eid, "op": "create"})
        elif kind in ("update", "delete") and op.get("entity_id"):
            ref = db.collection(_ENTITIES).document(op["entity_id"])
            snap = ref.get()
            if not snap.exists or snap.to_dict().get("feature") != feature:
                continue  # never touch another feature's data
            if kind == "update":
                merged = {**(snap.to_dict().get("data") or {}), **(op.get("data") or {})}
                ref.set({"data": merged, "updated_at": _now_iso()}, merge=True)
            else:
                ref.delete()
            changed.append({"entity_id": op["entity_id"], "op": kind})
    return changed


_STRUCTURE_REDIRECT = "「{title}」自体の変更（見た目・項目・機能の追加/削除など）はメインチャットからご依頼ください。ここでは、この機能の中身の操作を担当します。"


def _route_to_main(project_id: str, text: str, feature: str, title: str) -> str:
    """Hand a structural-change request off to the main chat pipeline (Receptor →
    Orchestrator), so the user doesn't have to re-ask there. Spec G3: the Specialist
    Worker DETECTS and FORWARDS (not just declines)."""
    from app.reception import service as reception

    try:
        res = reception.handle_request(project_id, text, hint_feature=feature)
        action = res.get("action")
        if action in ("edit", "create"):
            kind_ja = "改修" if action == "edit" else "新規作成"
            return (
                f"「{title}」自体の変更はメインチャットの担当なので、メインチャットへ取り次ぎました"
                f"（{kind_ja}として処理を開始）。メインチャットで設計案・進捗をご確認ください。"
            )
        if action == "rate_limited":
            return "ただいま処理が混み合っています。少し待ってから、メインチャットでご依頼ください。"
    except Exception:  # noqa: BLE001 — fall back to pointing the user to the main chat
        pass
    return _STRUCTURE_REDIRECT.format(title=title)


def _respond_content(
    project_id: str, feature: str, text: str, history: list[dict], manifest: dict
) -> tuple[str, list[dict], dict | None]:
    """Operate on the feature's CONTENT only. Returns (reply, changed_entities, command).

    - data-kind: edits entities (changed list).
    - app-kind: maps the instruction to one of the app's declared `commands`; the
      returned `command` is dispatched to the RUNNING app by the frontend.
    Structural change -> redirect to the main chat (no action here).
    """
    llm = get_llm()
    base = agents.load("feature_worker")
    title = manifest.get("title") or feature
    kind = manifest.get("kind") or "data"

    if not llm.enabled:
        return f"（機能ワーカー・スタブ）承りました：{text}", [], None

    # === mini-app (kind=app): map NL -> an MCP-style tool call ================
    # The mini-app declares its content-edit tools (MCP shape: name/description/
    # inputSchema). The specialist worker maps the instruction to ONE tool call
    # {name, arguments}; the running app executes it via applyAgentCommand.
    if kind == "app":
        tools = manifest.get("commands") or []
        tool_names = {t.get("name") for t in tools if isinstance(t, dict) and t.get("name")}
        if not tool_names:
            return (
                "このミニアプリには編集ツールが定義されていません。中身はアプリ上の操作で、"
                "アプリ自体の変更はメインチャットからお願いします。"
            ), [], None
        prompt = (
            f"{base}\n\n"
            f"対象ミニアプリ: {title}。あなたは専門ワーカーとして、宣言されたツールだけでこのアプリの中身を操作します。\n"
            f"利用可能ツール(MCP形式 name/description/inputSchema): {json.dumps(tools, ensure_ascii=False)}\n"
            f"直近の会話: {json.dumps(history[-6:], ensure_ascii=False)}\n"
            f"ユーザーの指示: {text}\n\n"
            "判定して JSON のみで出力:\n"
            '{"category":"content|structure|chat","reply":"<日本語の短い返答>",'
            '"command":{"name":"<toolsのname>","arguments":{<inputSchemaに沿った引数>}}}\n'
            "・中身の操作に対応するツールがある → category=content, command を埋める（nameは必ずtoolsの中から）\n"
            "・アプリ自体（UI/機能）の変更要求 → category=structure（command不要）\n"
            "・質問/相談や対応ツールが無い → category=chat（command不要）"
        )
        data = _safe_json(llm, prompt)
        category = data.get("category", "chat")
        reply = str(data.get("reply", "")).strip()
        if category == "structure":
            return _route_to_main(project_id, text, feature, title), [], None
        if category == "content":
            cmd = data.get("command") or {}
            name = cmd.get("name") if isinstance(cmd, dict) else None
            if name in tool_names:  # never dispatch an undeclared tool
                return (reply or "反映します。"), [], {"name": name, "arguments": cmd.get("arguments") or {}}
        # No matching tool for a content-ish request → this needs a capability the
        # app doesn't have yet. Adding it is a feature change = the main chat's job.
        return (
            reply
            or f"このミニアプリには、その操作に対応するツールがありません（利用可能: {('、'.join(sorted(tool_names)))}）。"
            "新しい操作を増やすには、メインチャットで「この機能に〜できるようにして」と依頼してください。"
        ), [], None

    # === data-kind: edit entities ============================================
    entities = [
        {"entity_id": d.id, **(d.to_dict().get("data") or {})}
        for d in get_db()
        .collection(_ENTITIES)
        .where("project_id", "==", project_id)
        .where("feature", "==", feature)
        .stream()
    ]
    field_keys = [f.get("key") or f.get("name") for f in (manifest.get("fields") or [])]
    prompt = (
        f"{base}\n\n"
        f"対象機能: {title}（データ系）。あなたはこの機能の『中身（データ）』だけを扱います。\n"
        "機能そのものの変更（UI・項目・レイアウト・コードの追加/削除）は担当外です。\n"
        f"データ項目: {json.dumps(field_keys, ensure_ascii=False)}\n"
        f"現在のデータ({len(entities)}件・最大20): {json.dumps(entities[:20], ensure_ascii=False)}\n"
        f"直近の会話: {json.dumps(history[-6:], ensure_ascii=False)}\n"
        f"ユーザーの指示: {text}\n\n"
        "判定して JSON のみで出力:\n"
        '{"category":"content|structure|chat","reply":"<日本語の短い返答>",'
        '"ops":[{"op":"create|update|delete","entity_id":"<update/delete時>","data":{<項目に沿った値>}}]}'
    )
    data = _safe_json(llm, prompt)
    category = data.get("category", "chat")
    reply = str(data.get("reply", "")).strip()
    if category == "structure":
        return _route_to_main(project_id, text, feature, title), [], None
    if category == "content":
        changed = _apply_entity_ops(project_id, feature, data.get("ops") or [])
        if changed:
            reply = (reply or "更新しました。") + f"（{len(changed)}件を反映しました）"
        return reply or "承知しました。", changed, None
    return reply or "承知しました。", [], None


def _safe_json(llm, prompt: str) -> dict:
    """Run the LLM and parse its JSON, tolerating a ```json fence. {} on failure."""
    try:
        raw = llm.generate(prompt, tier=ModelTier.FLASH).strip()
        if raw.startswith("```"):
            raw = raw.strip("`").split("\n", 1)[-1]
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return {}
