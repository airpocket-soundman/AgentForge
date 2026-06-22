"""Feature-level managing AI worker (standard spec).

DECOUPLED from the main build pipeline (decision 2026-06-09): a feature's worker
operates ONLY on that feature's CONTENT — the data/objects it holds (tasks, records,
the entities behind the view). It does NOT create or restructure features.

Changing the feature itself (its UI, fields, layout, code) is the MAIN chat's job
(the Orchestrator pipeline). If the user asks the feature worker for a structural
change, it DETECTS it and FORWARDS the request to the main chat pipeline
(Receptor → Orchestrator) so the user doesn't have to re-ask (spec G3) — a feature
never restructures itself directly, but the request isn't dropped either.

Conversation is stored per app + screen/context in
feature_chats/{project}_{feature}_{context}. The worker can be turned off per
feature (feature_states.{feature}_worker = false).
"""
from __future__ import annotations

import json
import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from app import agents
from app.auth import CurrentUser, current_user, require_project_access
from app.control_plane.approvals import require_feature_active
from app.firestore import get_db
from app.llm.gateway import ModelTier, get_llm
from app.models.reception import ChatMessage
from app.models.tasks import FeatureWorkerIn, Task

router = APIRouter(prefix="/api/app/features", tags=["generated-app:feature-worker"])

_VIEWS = "generated_views"
_STATE = "app_state"
_DEFAULT_CONTEXT = "default"


def _today_context() -> str:
    # Demo/prod user base is Japan-oriented; use JST for natural date phrases.
    return (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _context_id(raw: str | None) -> str:
    ctx = re.sub(r"[^a-zA-Z0-9_-]+", "_", (raw or _DEFAULT_CONTEXT).strip()).strip("_")
    return (ctx or _DEFAULT_CONTEXT)[:80]


def _chat_doc_id(project_id: str, feature: str, context_id: str | None = None) -> str:
    return f"{project_id}_{feature}_{_context_id(context_id)}"


def _chat_ref(project_id: str, feature: str, context_id: str | None = None):
    return get_db().collection("feature_chats").document(_chat_doc_id(project_id, feature, context_id))


def _manifest(project_id: str, feature: str) -> dict:
    snap = get_db().collection(_VIEWS).document(f"{project_id}_{feature}").get()
    return (snap.to_dict() or {}) if snap.exists else {}


def _state_doc_id(project_id: str, feature: str) -> str:
    return f"{project_id}_{feature}"


def _load_app_state(project_id: str, feature: str):
    snap = get_db().collection(_STATE).document(_state_doc_id(project_id, feature)).get()
    return snap.to_dict().get("state") if snap.exists else None


def _save_app_state(project_id: str, feature: str, state) -> None:
    get_db().collection(_STATE).document(_state_doc_id(project_id, feature)).set(
        {"project_id": project_id, "feature": feature, "state": state, "updated_at": _now_iso()},
        merge=True,
    )


def _worker_enabled(project_id: str, feature: str) -> bool:
    snap = get_db().collection("feature_states").document(project_id).get()
    if not snap.exists:
        return False
    data = snap.to_dict()
    return data.get(feature) == "active" and data.get(f"{feature}_worker", True) is not False


_OP_LABEL = {"create": "作成", "update": "更新", "delete": "削除", "clear": "一括削除"}


def _work_report(command: dict | None, changed: list[dict] | None) -> ChatMessage | None:
    """A system 'what I did' line for the app chat — posted whenever the Specialist
    Worker actually operates (tool call or data change). None for pure chat."""
    if command and command.get("name"):
        args = command.get("arguments") or {}
        a = "、".join(f"{k}={str(v)[:30]}" for k, v in list(args.items())[:4])
        return ChatMessage(role="system",
                           text=f"🔧 専門ワーカーが操作を実行：「{command['name']}」" + (f"（{a}）" if a else ""))
    if changed:
        if all(isinstance(c, dict) and c.get("op") for c in changed):
            from collections import Counter

            cnt = Counter(c["op"] for c in changed)
            s = "、".join(f"{_OP_LABEL.get(k, k)}{n}件" for k, n in cnt.items())
        else:
            s = f"{len(changed)}件"
        return ChatMessage(role="system", text=f"🔧 専門ワーカーがデータを変更：{s}")
    return None


def _append(
    project_id: str,
    feature: str,
    context_id: str | None,
    context_label: str | None,
    *messages: ChatMessage,
) -> None:
    from google.cloud import firestore  # local import keeps module import cheap

    ctx = _context_id(context_id)
    _chat_ref(project_id, feature, ctx).set(
        {
            "project_id": project_id,
            "feature": feature,
            "context_id": ctx,
            "context_label": context_label or ctx,
            "messages": firestore.ArrayUnion([m.model_dump(mode="json") for m in messages]),
            "updated_at": _now_iso(),
        },
        merge=True,
    )


@router.get("/{feature}/worker")
def get_worker(
    feature: str,
    project_id: str = "default",
    context_id: str = _DEFAULT_CONTEXT,
    user: CurrentUser = Depends(current_user),
) -> dict:
    require_project_access(user, project_id)
    require_feature_active(project_id, feature)
    ctx = _context_id(context_id)
    doc = _chat_ref(project_id, feature, ctx).get()
    data = doc.to_dict() if doc.exists else {}
    return {
        "enabled": _worker_enabled(project_id, feature),
        "context_id": ctx,
        "context_label": data.get("context_label") or ctx,
        "messages": data.get("messages", []),
    }


@router.post("/{feature}/worker/messages")
def post_worker_message(feature: str, body: FeatureWorkerIn, user: CurrentUser = Depends(current_user)) -> dict:
    require_project_access(user, body.project_id)
    require_feature_active(body.project_id, feature)
    if not _worker_enabled(body.project_id, feature):
        raise HTTPException(status_code=409, detail="この機能のAIワーカーは無効です")

    ctx = _context_id(body.context_id)
    snap = _chat_ref(body.project_id, feature, ctx).get()
    history = snap.to_dict().get("messages", []) if snap.exists else []
    user_msg = ChatMessage(role="user", text=body.text)

    # Attached images (e.g. a 翻訳 button sending a pasted photo) → vision input.
    images = [{"mime": a.mime or "image/png", "data": a.content}
              for a in body.attachments if getattr(a, "kind", "") == "image" and a.content][:4]

    # Show the Specialist Worker as ACTIVE in the status monitor while it works,
    # and always release it afterwards — its work continues server-side regardless
    # of the user navigating away (the HTTP call completes independently of the UI).
    from app.control_plane import worker_status
    from app.llm.gateway import ModelTier, model_label

    title = _manifest(body.project_id, feature).get("title") or feature
    worker_status.record_status("Specialist Worker", body.project_id, worker_status.ACTIVE,
                                model=model_label(ModelTier.FLASH), detail=f"「{title}」を操作中")
    command: dict | None = None
    try:
        # The `task` feature keeps its deterministic create-tasks operation (content op).
        if feature == "task":
            reply_text, changed = _respond_task(
                body.project_id, body.text, history, user_call_name=body.user_call_name
            )
        else:
            # Content-only: operate on this feature's data/objects. NEVER forwards to the
            # design pipeline — structural changes are redirected to the main chat.
            # For app-kind features, returns a `command` for the running app to execute.
            reply_text, changed, command = _respond_content(
                body.project_id, feature, body.text, history, _manifest(body.project_id, feature),
                images=images, user_call_name=body.user_call_name,
            )
    finally:
        worker_status.record_status("Specialist Worker", body.project_id, worker_status.STOPPED, detail=None)

    reply = ChatMessage(role="assistant", text=reply_text)
    # Transparency (workers.html §運用ルール): the Specialist Worker reports what it
    # actually did — a system line in the app chat each time it operates — instead of
    # silently acting (mirrors the main-chat workers' interim progress reports).
    report = _work_report(command, changed)
    msgs = [user_msg] + ([report] if report else []) + [reply]
    _append(body.project_id, feature, ctx, body.context_label, *msgs)
    return {
        "reply": reply.model_dump(mode="json"),
        "building": False,
        "context_id": ctx,
        "created": changed,
        "data_changed": bool(changed),
        "command": command,  # app-kind: {name, args} for the live app to apply
    }


# --- worker logic ------------------------------------------------------------

def _user_context_instruction(user_call_name: str | None) -> str:
    name = " ".join((user_call_name or "").split())[:40]
    if not name:
        return ""
    return (
        "\n\n[ユーザー設定]\n"
        f"ユーザーの呼び名: {name}\n"
        "以後、自然な範囲でこの呼び名でユーザーに呼びかけてください。"
        "ただし毎回・毎文のように過度には呼ばないでください。"
    )


def _chat_reply(
    feature: str, text: str, history: list[dict], manifest: dict, user_call_name: str | None = None
) -> str:
    """A conversational answer from the feature worker (no feature change)."""
    base = agents.load("feature_worker")
    llm = get_llm()
    if not llm.enabled:
        return f"（機能ワーカー・スタブ）承りました：{text}"
    prompt = (
        f"{base}\n\n"
        f"{_user_context_instruction(user_call_name)}\n\n"
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


def _respond_task(
    project_id: str, text: str, history: list[dict], user_call_name: str | None = None
) -> tuple[str, list[dict]]:
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
        f"{_user_context_instruction(user_call_name)}\n\n"
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


def _route_to_main(
    project_id: str, text: str, feature: str, title: str, user_call_name: str | None = None
) -> str:
    """Hand a structural-change request off to the main chat pipeline (Receptor →
    Orchestrator), so the user doesn't have to re-ask there. Spec G3: the Specialist
    Worker DETECTS and FORWARDS (not just declines)."""
    from app.reception import service as reception

    try:
        res = reception.handle_request(project_id, text, hint_feature=feature, user_call_name=user_call_name)
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


def _tool_names(manifest: dict) -> set[str]:
    return {t.get("name") for t in (manifest.get("commands") or []) if isinstance(t, dict) and t.get("name")}


def _state_mode(manifest: dict) -> str:
    mode = str(manifest.get("worker_state_mode") or "commands").strip().lower()
    return mode if mode in {"commands", "state", "hybrid"} else "commands"


def _can_direct_state_edit(manifest: dict) -> bool:
    return _state_mode(manifest) in {"state", "hybrid"} and isinstance(manifest.get("state_schema"), dict) and bool(manifest.get("state_schema"))


def _compact_json(value, limit: int = 24000) -> str:
    raw = json.dumps(value, ensure_ascii=False)
    if len(raw) <= limit:
        return raw
    return raw[:limit] + "…(truncated)"


def _normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "")


def _app_worker_operation_manual(feature: str, title: str, tools: list[dict], manifest: dict) -> str:
    available = ", ".join(t.get("name", "") for t in tools if isinstance(t, dict) and t.get("name"))
    command_lines: list[str] = []
    for tool in tools:
        if not isinstance(tool, dict) or not tool.get("name"):
            continue
        schema = tool.get("inputSchema") or {}
        props = schema.get("properties") if isinstance(schema, dict) else {}
        required = set(schema.get("required") or []) if isinstance(schema, dict) else set()
        args = []
        if isinstance(props, dict):
            for key, spec in props.items():
                label = f"{key}{'*' if key in required else ''}"
                if isinstance(spec, dict) and spec.get("description"):
                    label += f":{spec.get('description')}"
                args.append(label)
        command_lines.append(f"- {tool.get('name')}: {tool.get('description', '')}。arguments: {', '.join(args) or 'なし'}")
    generated_manual = str(manifest.get("worker_instructions") or "").strip()
    examples = manifest.get("worker_examples") or []
    example_lines = []
    if isinstance(examples, list):
        for ex in examples[:12]:
            if not isinstance(ex, dict):
                continue
            user = str(ex.get("user") or "").strip()
            command = ex.get("command") or {}
            reply = str(ex.get("reply") or "").strip()
            if user:
                example_lines.append(f"- ユーザー: {user} / command: {json.dumps(command, ensure_ascii=False)} / reply: {reply}")

    common = (
        "この会話でのあなたの役割:\n"
        f"- あなたは「{title}」の操作用 Specialist Worker。ユーザーは自然文でこのアプリの中身を操作したい。\n"
        "- 目的は、会話からユーザーの意図を読み取り、利用可能な操作APIに正しく近づけること。\n"
        f"- 利用可能API: {available}\n"
        + "\n".join(command_lines)
        + "\n"
        "- 『追加』『入れて』『作って』は作成/追加意図。『変更』『直して』『移動』『更新』は更新意図。"
        "『消して』『削除』『消去』『なくして』は削除意図。語尾だけでなく文全体の意図から最適なAPIを選ぶ。\n"
        "- 必要な対象・値・日時・タイトルなどが十分に分かるなら category=content で最適なAPIを呼ぶ。\n"
        "- 情報が足りない、対象が曖昧、時刻が不自然、複数解釈があり得る場合は category=chat にして、短く具体的に聞き返す。\n"
        "- 聞き返した後にユーザーが『はい』『それで』などと確認した場合は、直近の会話から不足情報を補ってAPI実行へ進む。\n"
        "- APIでできる操作を『できません』とは言わない。APIに必要な引数へ自然文を変換する。\n"
        "- ただし、宣言APIで表せない新機能追加・画面変更は category=structure としてメインチャットへ取り次ぐ。\n"
    )
    if generated_manual:
        common += "\n[このアプリ固有の専門ワーカー指示]\n" + generated_manual[:4000] + "\n"
    if example_lines:
        common += "\n[このアプリで想定される自然言語指示とAPI対応例]\n" + "\n".join(example_lines) + "\n"
    return common


def _respond_state_content(
    project_id: str,
    feature: str,
    text: str,
    history: list[dict],
    manifest: dict,
    images: list | None = None,
    user_call_name: str | None = None,
) -> tuple[str, list[dict], dict | None] | None:
    """Let the Specialist Worker edit AF.load/AF.save state directly.

    This is the generic path for unknown future data-centered mini-apps. The app
    declares its persisted state schema; the worker reads the current state,
    returns a complete replacement state, and the backend saves it atomically.
    """
    if not _can_direct_state_edit(manifest):
        return None
    llm = get_llm()
    if not llm.enabled:
        return None
    title = manifest.get("title") or feature
    state_schema = manifest.get("state_schema") or {}
    current_state = _load_app_state(project_id, feature)
    tools = manifest.get("commands") or []
    prompt = (
        f"{agents.load('feature_worker')}\n\n"
        f"{_user_context_instruction(user_call_name)}\n\n"
        f"対象ミニアプリ: {title}（slug: {feature}）。あなたはこのミニアプリの操作用 Specialist Worker。\n"
        "このアプリは AF.load()/AF.save() の永続化 state を持つ。ユーザーの自然文を読み、"
        "アプリの中身の変更は persisted state を直接編集してよい。\n"
        f"今日の日付（Asia/Tokyo）: {_today_context()}\n"
        f"state_schema(JSON Schema風): {_compact_json(state_schema, 12000)}\n"
        f"現在のstate: {_compact_json(current_state, 32000)}\n"
        f"補助的に使えるcommands（必要な場合のみ参考）: {json.dumps(tools, ensure_ascii=False)}\n"
        f"{_app_worker_operation_manual(feature, title, tools, manifest)}\n"
        f"直近の会話: {json.dumps(history[-8:], ensure_ascii=False)}\n"
        + ("【添付画像あり】画像内のテキストも読み取り、state更新に必要なら反映すること。\n" if images else "")
        + f"ユーザーの指示: {text}\n\n"
        "JSONのみで出力:\n"
        '{"category":"content|structure|chat","reply":"<日本語の短い返答>",'
        '"state":<更新後の完全なstate。変更しない場合はnull>,'
        '"ops":[{"op":"create|update|delete|clear","target":"<対象の短い説明>"}]}\n\n'
        "判断ルール:\n"
        "1. 追加/更新/削除/一括削除/メモ追記/状態変更など、state_schema内のデータ変更で表せるなら category=content。\n"
        "2. state は差分ではなく、保存すべき完全な新状態を返す。既存の無関係なデータは保持する。\n"
        "2a. 追加する配列要素に schema 上 id がある場合は、既存 id と衝突しない短い文字列 id を必ず作る。\n"
        "3. 新しい画面・新しい項目・UI変更・state_schemaに無いデータ構造追加は category=structure。\n"
        "4. 日付や時刻は正規化する。時刻が15:65のように不自然なら実行せず category=chat で『16:05の意味でよろしいですか？』のように確認する。\n"
        "5. 削除/一括削除は、対象範囲が明示されていれば実行してよい。対象が曖昧なら category=chat で確認する。\n"
        "6. 純粋な質問・使い方相談・現状確認は category=chat。stateはnull。\n"
        "7. 担当外の構造変更は category=structure とし、ここではstateを変えない。\n"
    )
    data = _safe_json(llm, prompt, images=images)
    category = data.get("category")
    reply = str(data.get("reply", "")).strip()
    if category == "structure":
        return _route_to_main(project_id, text, feature, title, user_call_name=user_call_name), [], None
    if category == "chat":
        return reply or "承知しました。", [], None
    if category != "content":
        return None
    new_state = data.get("state")
    if new_state is None:
        return reply or "変更内容を特定できませんでした。もう少し具体的に教えてください。", [], None
    try:
        if len(json.dumps(new_state, ensure_ascii=False)) > 900_000:
            return "更新後のデータが大きすぎるため保存できません。対象を絞ってください。", [], None
    except TypeError:
        return "保存できない形式のデータが含まれていました。別の言い方で指示してください。", [], None
    _save_app_state(project_id, feature, new_state)
    ops = data.get("ops") if isinstance(data.get("ops"), list) else []
    changed = [{"entity_id": str(op.get("target") or "app_state")[:80], "op": str(op.get("op") or "update")} for op in ops[:20] if isinstance(op, dict)]
    if not changed:
        changed = [{"entity_id": "app_state", "op": "update"}]
    return reply or "更新しました。", changed, None


def _default_state_update(project_id: str, feature: str, text: str, manifest: dict) -> tuple[str, list[dict], dict | None] | None:
    if feature == "schedule":
        return _default_schedule_state_update(project_id, feature, text)
    if feature == "household_budget":
        return _default_household_budget_state_update(project_id, feature, text)
    if not _can_direct_state_edit(manifest):
        return None
    return None


def _default_schedule_state_update(project_id: str, feature: str, text: str) -> tuple[str, list[dict], dict | None] | None:
    parsed_delete = _parse_schedule_delete(text)
    if parsed_delete and parsed_delete.get("all"):
        state = _load_app_state(project_id, feature)
        if not isinstance(state, dict):
            return None
        events = state.get("events")
        if not isinstance(events, list):
            return None
        before = len(events)
        if parsed_delete.get("date"):
            events = [e for e in events if not (isinstance(e, dict) and e.get("date") == parsed_delete["date"])]
            label = f"{parsed_delete['date']} の予定"
        else:
            events = []
            label = "すべての予定"
        removed = before - len(events)
        if removed <= 0:
            return f"{label}は見つかりませんでした。", [], None
        state["events"] = events
        _save_app_state(project_id, feature, state)
        return f"{label}を削除しました。", [{"entity_id": "events", "op": "delete"} for _ in range(removed)], None

    parsed_many = _parse_schedule_add_many(text)
    if not parsed_many:
        return None
    state = _load_app_state(project_id, feature)
    if not isinstance(state, dict):
        state = {}
    events = state.get("events")
    if not isinstance(events, list):
        events = []
    existing_ids = {str(e.get("id")) for e in events if isinstance(e, dict) and e.get("id")}
    added = []
    for item in parsed_many[:60]:
        eid = f"e_{uuid.uuid4().hex[:10]}"
        while eid in existing_ids:
            eid = f"e_{uuid.uuid4().hex[:10]}"
        existing_ids.add(eid)
        ev = {"id": eid, **item}
        events.append(ev)
        added.append(ev)
    state["events"] = events
    _save_app_state(project_id, feature, state)
    dates = "、".join(f"{e['date']} {e.get('time') or '終日'}" for e in added)
    title = added[0]["title"] if added else ""
    return f"{dates} に「{title}」を追加しました。", [{"entity_id": "events", "op": "create"} for _ in added], None


def _default_household_budget_state_update(project_id: str, feature: str, text: str) -> tuple[str, list[dict], dict | None] | None:
    parsed = _parse_budget_transaction(text)
    if not parsed:
        return None
    state = _load_app_state(project_id, feature)
    if not isinstance(state, dict):
        state = {}
    tx = state.get("transactions")
    if not isinstance(tx, list):
        tx = []
    tx.append({"id": f"b_{uuid.uuid4().hex[:10]}", **parsed})
    state["transactions"] = tx
    _save_app_state(project_id, feature, state)
    kind = "収入" if parsed["type"] == "income" else "支出"
    return (
        f"{parsed['date']} に{kind}「{parsed['memo']}」{int(parsed['amount']):,}円を追加しました。",
        [{"entity_id": "transactions", "op": "create"}],
        None,
    )


def _default_app_command(feature: str, text: str, manifest: dict) -> tuple[str, dict] | None:
    """Deterministic NL -> command fallback for built-in templates.

    Default apps should feel operable from their Specialist Worker even when the
    lightweight model misses a straightforward command mapping.
    """
    names = _tool_names(manifest)
    t = (text or "").strip()
    if not t:
        return None
    if feature == "schedule" and "delete_event" in names:
        parsed_delete = _parse_schedule_delete(t)
        if parsed_delete:
            if parsed_delete.get("all") and parsed_delete.get("date"):
                return f"{parsed_delete['date']} の予定をすべて削除します。", {
                    "name": "delete_event",
                    "arguments": parsed_delete,
                }
            if parsed_delete.get("title"):
                target = f"{parsed_delete.get('date')} の「{parsed_delete['title']}」" if parsed_delete.get("date") else f"「{parsed_delete['title']}」"
                return f"{target}を削除します。", {"name": "delete_event", "arguments": parsed_delete}
    if feature == "schedule" and "add_event" in names:
        parsed = _parse_schedule_add(t)
        if parsed:
            title = parsed["title"]
            return f"{parsed['date']} {parsed.get('time') or '終日'} に「{title}」を追加します。", {
                "name": "add_event",
                "arguments": parsed,
            }
    if feature in ("task", "task_manager") and "add_task" in names:
        if "clear_done" in names and any(w in t for w in ("完了", "済み")) and any(w in t for w in ("消して", "削除", "消去", "クリア")):
            return "完了済みタスクを削除します。", {"name": "clear_done", "arguments": {}}
        if "delete_task" in names and _intent_family(t) == "delete":
            title = _extract_quoted(t) or _clean_tail(
                re.sub(r"(タスク|やること|todo|to-do)", "", t, flags=re.I),
                ("を削除して", "削除して", "を消して", "消して", "を消去して", "消去して"),
            )
            if title:
                return f"「{title}」を削除します。", {"name": "delete_task", "arguments": {"title": title}}
        if "toggle_task" in names and any(w in t for w in ("完了", "終わった", "済み", "未完了")):
            title = _extract_quoted(t) or _clean_tail(
                re.sub(r"(タスク|やること|todo|to-do|完了|未完了|済み|終わった)", "", t, flags=re.I),
                ("にして", "して", "にする"),
            )
            if title:
                return f"「{title}」の状態を切り替えます。", {"name": "toggle_task", "arguments": {"title": title, "done": "未完了" not in t}}
        if "rename_task" in names and any(w in t for w in ("名前", "リネーム", "変更")):
            m = re.search(r"[「『\"]([^」』\"]+)[」』\"]\s*(?:を|から).*[「『\"]([^」』\"]+)[」』\"]", t)
            if m:
                return f"「{m.group(1)}」を「{m.group(2)}」に変更します。", {
                    "name": "rename_task",
                    "arguments": {"title": m.group(1), "new_title": m.group(2)},
                }
        title = _extract_quoted(t) or _clean_tail(
            re.sub(r"(タスク|やること|todo|to-do)", "", t, flags=re.I),
            ("を追加して", "追加して", "を入れて", "入れて", "を作って", "作って"),
        )
        if title and any(w in t for w in ("追加", "入れて", "作って", "登録")):
            return f"「{title}」を追加します。", {"name": "add_task", "arguments": {"title": title}}
    if feature == "memo" and "add_note" in names:
        if "delete_note" in names and _intent_family(t) == "delete":
            title = _extract_quoted(t) or _clean_tail(
                re.sub(r"(メモ|ノート)", "", t),
                ("を削除して", "削除して", "を消して", "消して", "を消去して", "消去して"),
            )
            if title:
                return f"「{title}」のメモを削除します。", {"name": "delete_note", "arguments": {"title": title}}
        if "append_note" in names and any(w in t for w in ("追記", "追加で", "書き足")):
            quoted = _extract_quoted(t)
            if quoted:
                return "メモに追記します。", {"name": "append_note", "arguments": {"text": quoted}}
        quoted = _extract_quoted(t)
        if quoted and any(w in t for w in ("メモ", "ノート", "追加", "作って", "作成")):
            return f"「{quoted}」のメモを作成します。", {"name": "add_note", "arguments": {"title": quoted, "body": ""}}
    if feature == "calculator" and "compute" in names:
        if "clear" in names and any(w in t for w in ("クリア", "消して", "全消去", "リセット")):
            return "電卓をクリアします。", {"name": "clear", "arguments": {}}
        expr = re.sub(r"[^0-9+\-*/×÷().％%]", "", t)
        if expr and any(ch in expr for ch in "+-*/×÷"):
            return "計算します。", {"name": "compute", "arguments": {"expression": expr.replace("％", "%")}}
    if feature == "paint":
        if "clear" in names and any(w in t for w in ("全消去", "消して", "クリア")):
            return "キャンバスを全消去します。", {"name": "clear", "arguments": {}}
        if "undo" in names and any(w in t for w in ("戻して", "取り消", "undo")):
            return "ひとつ戻します。", {"name": "undo", "arguments": {}}
        if "set_tool" in names and any(w in t for w in ("消しゴム", "eraser")):
            return "消しゴムに切り替えます。", {"name": "set_tool", "arguments": {"tool": "eraser"}}
        if "set_tool" in names and any(w in t for w in ("ペン", "pen")):
            return "ペンに切り替えます。", {"name": "set_tool", "arguments": {"tool": "pen"}}
    return None


def _confirmation_app_command(
    feature: str, text: str, history: list[dict], manifest: dict
) -> tuple[str, dict] | None:
    names = _tool_names(manifest)
    normalized = (text or "").strip().lower()
    yes_words = {"はい", "うん", "ok", "okay", "yes", "それで", "それでお願いします", "お願いします"}
    if feature != "schedule" or "add_event" not in names or normalized not in yes_words:
        return None
    assistant_text = ""
    previous_user = ""
    for msg in reversed(history or []):
        role = msg.get("role")
        body = msg.get("text") or ""
        if not assistant_text and role == "assistant":
            assistant_text = body
            continue
        if assistant_text and role == "user":
            previous_user = body
            break
    if not assistant_text or not previous_user or "意味でよろしいですか" not in assistant_text:
        return None
    fixed_time = _parse_time(assistant_text)
    parsed = _parse_schedule_add(previous_user)
    if not fixed_time or not parsed:
        return None
    parsed["time"] = fixed_time
    return f"{parsed['date']} {fixed_time} に「{parsed['title']}」を追加します。", {
        "name": "add_event",
        "arguments": parsed,
    }


def _default_app_clarification(feature: str, text: str, manifest: dict) -> str | None:
    """Deterministic clarification guardrail for ambiguous/invalid app operations."""
    names = _tool_names(manifest)
    if feature == "schedule" and {"add_event", "update_event"} & names:
        return _schedule_time_clarification(text)
    return None


def _command_override(feature: str, command: dict, original_text: str, manifest: dict) -> tuple[str, dict] | None:
    if feature != "schedule" or not isinstance(command, dict):
        return _generic_command_override(command, original_text, manifest)
    name = command.get("name")
    if name != "delete_event" and _schedule_delete_intent(original_text):
        return _default_app_command(feature, original_text, manifest) or (
            "削除したい予定の日付やタイトルを教えてください。",
            {"name": "", "arguments": {}},
        )
    return _generic_command_override(command, original_text, manifest)


def _generic_command_override(command: dict, original_text: str, manifest: dict) -> tuple[str, dict] | None:
    if not isinstance(command, dict):
        return None
    name = str(command.get("name") or "")
    if not name:
        return None
    user_intent = _intent_family(original_text)
    command_intent = _command_family(name, manifest)
    if user_intent and command_intent and user_intent != command_intent:
        return (
            f"「{original_text}」は{_intent_label(user_intent)}の意図に見えますが、"
            f"選ばれたAPI（{name}）は{_intent_label(command_intent)}系です。"
            "対象や操作内容をもう少し具体的に教えてください。",
            {"name": "", "arguments": {}},
        )
    return None


def _intent_family(text: str) -> str:
    t = text or ""
    if any(w in t for w in ("削除", "消して", "消去", "消す", "消し", "なくして", "取り除", "remove", "delete")):
        return "delete"
    if any(w in t for w in ("追加", "入れて", "作って", "作成", "登録", "新規", "add", "create")):
        return "add"
    if any(w in t for w in ("変更", "更新", "直して", "修正", "移動", "リネーム", "名前を変", "edit", "update", "rename")):
        return "update"
    if any(w in t for w in ("クリア", "全消去", "リセット", "初期化", "clear", "reset")):
        return "clear"
    return ""


def _command_family(name: str, manifest: dict) -> str:
    hay = name.lower()
    for tool in manifest.get("commands") or []:
        if isinstance(tool, dict) and tool.get("name") == name:
            hay += " " + str(tool.get("description") or "").lower()
            break
    if any(w in hay for w in ("delete", "remove", "削除", "消去")):
        return "delete"
    if any(w in hay for w in ("add", "create", "append", "追加", "作成", "追記", "登録")):
        return "add"
    if any(w in hay for w in ("update", "edit", "rename", "set_", "変更", "更新", "編集")):
        return "update"
    if any(w in hay for w in ("clear", "reset", "クリア", "初期化", "全消去")):
        return "clear"
    return ""


def _intent_label(intent: str) -> str:
    return {"add": "追加", "delete": "削除", "update": "更新", "clear": "クリア"}.get(intent, intent)


def _command_clarification(feature: str, command: dict, original_text: str) -> str | None:
    """Validate LLM-selected app commands before the frontend applies them."""
    if feature != "schedule":
        return None
    name = command.get("name")
    if name not in {"add_event", "update_event"}:
        return None
    args = command.get("arguments") or {}
    if not isinstance(args, dict):
        return "時刻や予定内容をうまく読み取れませんでした。もう一度、日付・時刻・タイトルを教えてください。"
    invalid_from_text = _schedule_time_clarification(original_text)
    if invalid_from_text:
        return invalid_from_text
    time_text = str(args.get("time") or "").strip()
    if time_text and not _valid_time(time_text):
        return _schedule_time_clarification(time_text, require_intent=False) or "時刻が不自然です。正しい時刻を教えてください。"
    return None


def _extract_quoted(text: str) -> str:
    m = re.search(r"[「『\"]([^」』\"]+)[」』\"]", text or "")
    return m.group(1).strip() if m else ""


def _clean_tail(text: str, suffixes: tuple[str, ...]) -> str:
    out = (text or "").strip(" 。、\n\t")
    for s in suffixes:
        if out.endswith(s):
            out = out[: -len(s)]
    return out.strip(" 。、\n\t")


def _parse_schedule_add(text: str) -> dict | None:
    text = _normalize_text(text)
    if _schedule_delete_intent(text):
        return None
    if not any(w in text for w in ("予定", "スケジュール", "入れて", "追加", "登録")):
        return None
    date = _parse_date(text)
    if not date:
        return None
    time = _parse_time(text)
    title = _parse_schedule_title(text)
    if not title:
        return None
    return {"date": date, "time": time or "", "title": title, "memo": ""}


def _parse_schedule_add_many(text: str) -> list[dict] | None:
    t = _normalize_text(text)
    if _schedule_delete_intent(t):
        return None
    if not any(w in t for w in ("予定", "スケジュール", "入れて", "追加", "登録")):
        return None
    dates = _parse_dates(t)
    if len(dates) < 2:
        return None
    clarification = _schedule_time_clarification(t)
    if clarification:
        return None
    time = _parse_time(t)
    title = _parse_schedule_title(t)
    if not title:
        return None
    return [{"date": d, "time": time or "", "title": title, "memo": ""} for d in dates]


def _parse_schedule_delete(text: str) -> dict | None:
    text = _normalize_text(text)
    if not _schedule_delete_intent(text):
        return None
    date = _parse_date(text)
    if any(w in text for w in ("すべて", "全て", "全部", "全件", "一括")):
        args: dict = {"all": True}
        if date:
            args["date"] = date
        return args
    title = _parse_schedule_title(text)
    if date and _is_generic_schedule_delete_title(title):
        return {"date": date, "all": True}
    if not title:
        return None
    args = {"title": title}
    if date:
        args["date"] = date
    return args


def _parse_budget_transaction(text: str) -> dict | None:
    t = _normalize_text(text)
    if any(w in t for w in ("消して", "削除", "消去", "直して", "変更", "いくら", "合計", "集計")):
        return None
    amount = _parse_budget_amount(t)
    if amount is None:
        return None
    tx_type = "income" if any(w in t for w in ("収入", "給料", "給与", "賞与", "ボーナス", "入金", "売上")) else "expense"
    category = _budget_category(t, tx_type)
    memo = _budget_memo(t, amount)
    if not memo:
        memo = category
    return {
        "date": _parse_budget_date(t),
        "type": tx_type,
        "category": category,
        "memo": memo,
        "amount": amount,
    }


def _parse_budget_amount(text: str) -> int | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(万|万円)", text)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r"(\d{1,3}(?:,\d{3})+|\d+)\s*円", text)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


def _parse_budget_date(text: str) -> str:
    now = datetime.now(timezone.utc) + timedelta(hours=9)
    parsed = _parse_date(text)
    if parsed:
        return parsed
    if "昨日" in text:
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    return now.strftime("%Y-%m-%d")


def _budget_category(text: str, tx_type: str) -> str:
    if tx_type == "income":
        return "給与" if any(w in text for w in ("給料", "給与", "賞与", "ボーナス")) else "その他"
    mapping = [
        ("食費", ("ランチ", "昼食", "夕食", "朝食", "ご飯", "弁当", "カレー", "コンビニ", "スーパー", "食費", "カフェ")),
        ("交通", ("電車", "バス", "タクシー", "交通", "定期", "ガソリン")),
        ("日用品", ("日用品", "洗剤", "ティッシュ", "トイレット", "文具")),
        ("交際", ("飲み会", "会食", "プレゼント", "交際")),
        ("趣味", ("映画", "本", "ゲーム", "趣味")),
        ("住居", ("家賃", "電気", "ガス", "水道", "住居")),
    ]
    for cat, words in mapping:
        if any(w in text for w in words):
            return cat
    return "その他"


def _budget_memo(text: str, amount: int) -> str:
    out = _normalize_text(text)
    out = re.sub(r"\d+(?:\.\d+)?\s*(?:万円|万)", " ", out)
    out = re.sub(r"\d{1,3}(?:,\d{3})+\s*円?", " ", out)
    out = re.sub(r"\d+\s*円?", " ", out)
    out = re.sub(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日?", " ", out)
    out = re.sub(r"\d{4}[/-]\d{1,2}[/-]\d{1,2}", " ", out)
    out = re.sub(r"\d{1,2}\s*月\s*\d{1,2}\s*日?", " ", out)
    out = re.sub(r"(?<!月)\d{1,2}\s*日", " ", out)
    out = re.sub(r"(今日|本日|昨日|明日|を|で|として|入れて|追加|登録|支出|収入)", " ", out)
    return " ".join(out.split()).strip(" 。、,")


def _schedule_delete_intent(text: str) -> bool:
    return any(w in (text or "") for w in ("消して", "削除", "消去", "消す", "消し", "なくして", "取り消して"))


def _is_generic_schedule_delete_title(title: str) -> bool:
    compact = re.sub(r"\s+", "", _normalize_text(title))
    return compact in {
        "",
        "予定",
        "スケジュール",
        "予定を",
        "スケジュールを",
        "予定を消して",
        "予定消して",
        "スケジュールを消して",
        "予定を削除して",
        "スケジュールを削除して",
    }


def _parse_date(text: str) -> str | None:
    text = _normalize_text(text)
    now = datetime.now(timezone.utc) + timedelta(hours=9)
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?", text)
    if not m:
        m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
    if m:
        y, mo, d = map(int, m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}"
    m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日?", text)
    if m:
        mo, d = map(int, m.groups())
        return f"{now.year:04d}-{mo:02d}-{d:02d}"
    m = re.search(r"(?<!月)(\d{1,2})\s*日", text)
    if m:
        d = int(m.group(1))
        return f"{now.year:04d}-{now.month:02d}-{d:02d}"
    if "明日" in text:
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")
    if "今日" in text or "本日" in text:
        return now.strftime("%Y-%m-%d")
    return None


def _parse_dates(text: str) -> list[str]:
    t = _normalize_text(text)
    now = datetime.now(timezone.utc) + timedelta(hours=9)
    out: list[str] = []

    def add_date(y: int, mo: int, d: int) -> None:
        if 1 <= mo <= 12 and 1 <= d <= 31:
            val = f"{y:04d}-{mo:02d}-{d:02d}"
            if val not in out:
                out.append(val)

    for y, mo, d in re.findall(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?", t):
        add_date(int(y), int(mo), int(d))
    for y, mo, d in re.findall(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", t):
        add_date(int(y), int(mo), int(d))
    for mo, d in re.findall(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日?", t):
        add_date(now.year, int(mo), int(d))
    for group in re.findall(r"((?:\d{1,2}\s*[、,]\s*)+\d{1,2})\s*日", t):
        for d in re.findall(r"\d{1,2}", group):
            add_date(now.year, now.month, int(d))
    for d in re.findall(r"(?<!月)(\d{1,2})\s*日", t):
        add_date(now.year, now.month, int(d))
    if "明日" in t:
        val = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        if val not in out:
            out.append(val)
    if "今日" in t or "本日" in t:
        val = now.strftime("%Y-%m-%d")
        if val not in out:
            out.append(val)
    return out


def _parse_time(text: str) -> str:
    text = _normalize_text(text)
    for m in re.finditer(r"(\d{1,2})\s*[:：]\s*(\d{2})", text):
        hour, minute = int(m.group(1)), int(m.group(2))
        if _valid_time_parts(hour, minute):
            return f"{hour:02d}:{minute:02d}"
    for m in re.finditer(r"(\d{1,2})\s*時\s*(?:(\d{1,2})\s*分?)?", text):
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        if _valid_time_parts(hour, minute):
            return f"{hour:02d}:{minute:02d}"
    return ""


def _valid_time(text: str) -> bool:
    m = re.fullmatch(r"\s*(\d{1,2})\s*[:：]\s*(\d{2})\s*", text or "")
    if not m:
        return False
    return _valid_time_parts(int(m.group(1)), int(m.group(2)))


def _valid_time_parts(hour: int, minute: int) -> bool:
    return 0 <= hour <= 23 and 0 <= minute <= 59


def _schedule_time_clarification(text: str, require_intent: bool = True) -> str | None:
    text = _normalize_text(text)
    if require_intent and not any(w in (text or "") for w in ("予定", "スケジュール", "入れて", "追加", "登録", "変更", "更新", "移動")):
        return None
    raw = text or ""
    m = re.search(r"(\d{1,2})\s*[:：]\s*(\d{2})", raw)
    if not m:
        m = re.search(r"(\d{1,2})\s*時\s*(\d{1,2})\s*分?", raw)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    if _valid_time_parts(hour, minute):
        return None
    shown = f"{hour:02d}:{minute:02d}"
    if 0 <= hour <= 23 and minute >= 60:
        total = hour * 60 + minute
        fixed = f"{total // 60:02d}:{total % 60:02d}"
        return f"{shown} は時刻として不自然です。{fixed} の意味でよろしいですか？"
    return f"{shown} は時刻として不自然です。正しい時刻を教えてください。"


def _parse_schedule_title(text: str) -> str:
    text = _normalize_text(text)
    for pat in (
        r"[、,]\s*(.+?)\s*という予定",
        r"[、,]\s*(.+?)\s*を(?:予定|スケジュール)?(?:に)?(?:入れて|追加して|登録して)",
        r"に\s*(.+?)\s*という予定",
        r"に\s*(.+?)\s*を(?:入れて|追加して|登録して)",
    ):
        m = re.search(pat, text)
        if m:
            title = _strip_date_time(m.group(1))
            if title:
                return title
    title = _strip_date_time(text)
    title = re.sub(r"(予定|スケジュール)?(を)?(入れて|追加して|登録して|作って)$", "", title).strip()
    return title


def _strip_date_time(text: str) -> str:
    out = _normalize_text(text)
    out = re.sub(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日?", "", out)
    out = re.sub(r"\d{4}[/-]\d{1,2}[/-]\d{1,2}", "", out)
    out = re.sub(r"\d{1,2}\s*月\s*\d{1,2}\s*日?", "", out)
    out = re.sub(r"(?:\d{1,2}\s*[、,]\s*)+\d{1,2}\s*日", "", out)
    out = re.sub(r"(?<!月)\d{1,2}\s*日", "", out)
    out = re.sub(r"\d{1,2}\s*[:：]\s*\d{2}", "", out)
    out = re.sub(r"\d{1,2}\s*時\s*(?:\d{1,2}\s*分?)?", "", out)
    out = re.sub(r"(今日|本日|明日|の|に|、|,)", " ", out)
    return " ".join(out.split()).strip(" 。")


def _respond_content(
    project_id: str, feature: str, text: str, history: list[dict], manifest: dict,
    images: list | None = None,
    user_call_name: str | None = None,
) -> tuple[str, list[dict], dict | None]:
    """Operate on the feature's CONTENT only. Returns (reply, changed_entities, command).

    - data-kind: edits entities (changed list).
    - app-kind: for state/hybrid apps, can edit the persisted AF state directly;
      otherwise maps the instruction to one of the app's declared `commands`.
    Structural change -> redirect to the main chat (no action here).
    """
    llm = get_llm()
    base = agents.load("feature_worker")
    title = manifest.get("title") or feature
    kind = manifest.get("kind") or "data"

    if not llm.enabled and kind != "app":
        return f"（機能ワーカー・スタブ）承りました：{text}", [], None

    # === mini-app (kind=app): map NL -> an MCP-style tool call ================
    # The mini-app declares its content-edit tools (MCP shape: name/description/
    # inputSchema). The specialist worker maps the instruction to ONE tool call
    # {name, arguments}; the running app executes it via applyAgentCommand.
    if kind == "app":
        deterministic_state = _default_state_update(project_id, feature, text, manifest)
        if deterministic_state is not None:
            return deterministic_state
        state_result = _respond_state_content(
            project_id, feature, text, history, manifest, images=images, user_call_name=user_call_name
        )
        if state_result is not None:
            return state_result
        tools = manifest.get("commands") or []
        tool_names = _tool_names(manifest)
        if not tool_names:
            return (
                "このミニアプリには、ワーカーが扱える state_schema または編集ツールが定義されていません。"
                "中身はアプリ上で操作し、アプリ自体の変更はメインチャットからお願いします。"
            ), [], None
        reply = ""
        category = "chat"
        if llm.enabled:
            prompt = (
                f"{base}\n\n"
                f"{_user_context_instruction(user_call_name)}\n\n"
                f"対象ミニアプリ: {title}（slug: {feature}）。あなたは専門ワーカーとして、宣言されたツールだけでこのアプリの中身を操作します。\n"
                f"今日の日付（Asia/Tokyo）: {_today_context()}\n"
                f"利用可能ツール(MCP形式 name/description/inputSchema): {json.dumps(tools, ensure_ascii=False)}\n"
                f"{_app_worker_operation_manual(feature, title, tools, manifest)}\n"
                f"直近の会話: {json.dumps(history[-6:], ensure_ascii=False)}\n"
                + ("【添付画像あり】画像内のテキストも読み取って指示の対象にすること。\n" if images else "")
                + f"ユーザーの指示: {text}\n\n"
                "判定して JSON のみで出力:\n"
                '{"category":"content|structure|chat","reply":"<日本語の短い返答>",'
                '"command":{"name":"<toolsのname>","arguments":{<inputSchemaに沿った引数>}}}\n\n'
                "判断ルール:\n"
                "0. まずユーザーの意図を classify する: add/create, update/change, delete/remove, toggle, clear/reset, query/chat, structure。"
                "そのうえで利用可能APIから最も近いものを選ぶ。\n"
                "1. ユーザーの指示が利用可能ツールのどれかで意味的に実行できるなら、必ず category=content にする。"
                "ツール名や引数名をユーザーが正確に言っていなくても、意味から最も近いツールを選ぶ。\n"
                "2. 日付・時刻・数量・タイトル・本文などは、inputSchema に合う形へ正規化する。"
                "例:『6月22日の12:00』→ date='YYYY-06-22', time='12:00'。年が無ければ今日の日付の年を使う。\n"
                "3. 存在しない時刻や不自然な値は勝手に登録しない。例:『15:65』は"
                " category=chat とし、『16:05 の意味でよろしいですか？』のように確認する。\n"
                "4. 削除語があるのに追加APIを選ぶ、追加語があるのに削除APIを選ぶ等、意図とAPIが矛盾する出力は禁止。\n"
                "5. 翻訳・要約・抽出などツールの引数に生成テキストが必要な場合は、その本文を arguments に入れる。\n"
                "6. UI/項目/新ボタン追加など、アプリそのものの構造変更は category=structure。\n"
                "7. 純粋な質問・相談で操作しない場合だけ category=chat。\n"
                "8. category=chat の reply は、分からない点を1つずつ具体的に聞く。"
                "例:『何日の予定ですか？』『どの予定のメモを変更しますか？』"
            )
            data = _safe_json(llm, prompt, images=images)
            category = data.get("category", "chat")
            reply = str(data.get("reply", "")).strip()
            if category == "structure":
                return _route_to_main(project_id, text, feature, title, user_call_name=user_call_name), [], None
            if category == "content":
                cmd = data.get("command") or {}
                name = cmd.get("name") if isinstance(cmd, dict) else None
                if name in tool_names:  # never dispatch an undeclared tool
                    override = _command_override(feature, cmd, text, manifest)
                    if override:
                        override_reply, override_command = override
                        if override_command.get("name") in tool_names:
                            return override_reply, [], override_command
                        return override_reply, [], None
                    clarification = _command_clarification(feature, cmd, text)
                    if clarification:
                        return clarification, [], None
                    return (reply or "反映します。"), [], {"name": name, "arguments": cmd.get("arguments") or {}}
        confirmed = _confirmation_app_command(feature, text, history, manifest)
        if confirmed:
            confirmed_reply, command = confirmed
            return reply or confirmed_reply, [], command
        clarification = _default_app_clarification(feature, text, manifest)
        if clarification:
            return clarification, [], None
        fallback = _default_app_command(feature, text, manifest)
        if fallback:
            fb_reply, command = fallback
            return reply or fb_reply, [], command
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
        f"{_user_context_instruction(user_call_name)}\n\n"
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
    data = _safe_json(llm, prompt, images=images)
    category = data.get("category", "chat")
    reply = str(data.get("reply", "")).strip()
    if category == "structure":
        return _route_to_main(project_id, text, feature, title, user_call_name=user_call_name), [], None
    if category == "content":
        changed = _apply_entity_ops(project_id, feature, data.get("ops") or [])
        if changed:
            reply = (reply or "更新しました。") + f"（{len(changed)}件を反映しました）"
        return reply or "承知しました。", changed, None
    return reply or "承知しました。", [], None


def _safe_json(llm, prompt: str, images: list | None = None) -> dict:
    """Run the LLM and parse its JSON, tolerating a ```json fence. {} on failure.
    `images` (attachments) are passed for vision (e.g. translating text in a photo)."""
    try:
        raw = llm.generate(prompt, tier=ModelTier.FLASH, images=images or None).strip()
        if raw.startswith("```"):
            raw = raw.strip("`").split("\n", 1)[-1]
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return {}
