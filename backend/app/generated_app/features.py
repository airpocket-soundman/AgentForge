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
from app.control_plane.worker_context import append_messages_compacted, summary_message
from app.control_plane.approvals import require_feature_active
from app.firestore import get_db
from app.llm.gateway import ModelTier, get_llm
from app.models.reception import ChatMessage
from app.models.tasks import FeatureWorkerIn, Task
from app.tools import web_search as web_search_tool

router = APIRouter(prefix="/api/app/features", tags=["generated-app:feature-worker"])

_VIEWS = "generated_views"
_STATE = "app_state"
_APP_CONNECTORS = "app_connectors"
_DEFAULT_CONTEXT = "default"
_FEATURE_CHAT_KEEP_RECENT = 70


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
    ctx = _context_id(context_id)
    # Transactional append (compaction needs read-modify-write; a transaction keeps
    # concurrent worker replies and user posts from dropping each other).
    append_messages_compacted(
        _chat_ref(project_id, feature, ctx),
        [m.model_dump(mode="json") for m in messages],
        keep_recent=_FEATURE_CHAT_KEEP_RECENT,
        base_fields={
            "project_id": project_id,
            "feature": feature,
            "context_id": ctx,
            "context_label": context_label or ctx,
        },
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
    messages = data.get("messages", [])
    compacted = summary_message(str(data.get("compacted_summary") or ""))
    if compacted:
        messages = [compacted, *messages]
    return {
        "enabled": _worker_enabled(project_id, feature),
        "context_id": ctx,
        "context_label": data.get("context_label") or ctx,
        "messages": messages,
    }


@router.post("/{feature}/worker/messages")
def post_worker_message(feature: str, body: FeatureWorkerIn, user: CurrentUser = Depends(current_user)) -> dict:
    require_project_access(user, body.project_id)
    require_feature_active(body.project_id, feature)
    if not _worker_enabled(body.project_id, feature):
        raise HTTPException(status_code=409, detail="この機能のAIワーカーは無効です")

    ctx = _context_id(body.context_id)
    snap = _chat_ref(body.project_id, feature, ctx).get()
    chat_data = snap.to_dict() if snap.exists else {}
    history = chat_data.get("messages", [])
    if chat_data.get("compacted_summary"):
        history = [
            {"role": "system", "text": "以前の会話要約:\n" + str(chat_data.get("compacted_summary"))[-3000:]}
        ] + history
    user_msg = ChatMessage(role="user", text=body.text)

    # Attached images (e.g. a 翻訳 button sending a pasted photo) → vision input.
    images = [{"mime": a.mime or "image/png", "data": a.content}
              for a in body.attachments if getattr(a, "kind", "") == "image" and a.content][:4]

    pipeline_control = _handle_shared_pipeline_control(body.project_id, feature, body.text)
    if pipeline_control is not None:
        reply_text, building, data_changed = pipeline_control
        reply = ChatMessage(role="assistant", text=reply_text)
        _append(body.project_id, feature, ctx, body.context_label, user_msg, reply)
        return {
            "reply": reply.model_dump(mode="json"),
            "building": building,
            "context_id": ctx,
            "created": [],
            "data_changed": data_changed,
            "command": None,
        }

    # Show the Specialist Worker as ACTIVE in the status monitor while it works,
    # and always release it afterwards — its work continues server-side regardless
    # of the user navigating away (the HTTP call completes independently of the UI).
    from app.control_plane import worker_status
    from app.llm.gateway import ModelTier, model_label

    manifest = _manifest(body.project_id, feature)
    title = manifest.get("title") or feature
    worker_tier = _specialist_model_tier(
        body.text,
        direct_state=_can_direct_state_edit(manifest),
        has_images=bool(images),
    )
    worker_status.record_status("Specialist Worker", body.project_id, worker_status.ACTIVE,
                                model=model_label(worker_tier), detail=f"「{title}」を操作中")
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
                body.project_id, feature, body.text, history, manifest,
                images=images, user_call_name=body.user_call_name,
                context_id=ctx, context_label=body.context_label, user_uid=user.uid,
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
    display_name = f"{name}さん"
    return (
        "\n\n[ユーザー設定]\n"
        f"ユーザーの呼び名: {display_name}\n"
        "以後、自然な範囲でこの呼び名でユーザーに呼びかけてください。敬称は省略しないでください。"
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


_STRUCTURE_REDIRECT = (
    "「{title}」自体の変更（見た目・項目・機能の追加/削除など）を制作チームに取り次げませんでした。"
    "少し待ってから、このアプリチャットでもう一度依頼してください。"
)


def _route_to_main(
    project_id: str, text: str, feature: str, title: str, user_call_name: str | None = None
) -> str:
    """Hand a structural-change request off to the main chat pipeline (Receptor →
    Orchestrator), so the user doesn't have to re-ask there. Spec G3: the Specialist
    Worker DETECTS and FORWARDS (not just declines)."""
    from app.reception import service as reception

    try:
        res = reception.handle_request(
            project_id,
            text,
            hint_feature=feature,
            user_call_name=user_call_name,
            restrict_feature=feature,
        )
        action = res.get("action")
        if action == "out_of_scope":
            return (
                f"このアプリチャットから取り次げるのは「{title}」自身の改修だけです。"
                "他のアプリの変更や新規アプリ作成は、対象アプリの画面またはメインチャットから依頼してください。"
            )
        if action in ("edit", "create"):
            kind_ja = "改修" if action == "edit" else "新規作成"
            return (
                f"「{title}」自体の変更として制作チームに取り次ぎました"
                f"（{kind_ja}として処理を開始）。このアプリ画面で進捗とプレビューを確認できます。"
            )
        if action == "rate_limited":
            return "ただいま処理が混み合っています。少し待ってから、このアプリチャットでもう一度依頼してください。"
    except Exception:  # noqa: BLE001 — fall back to pointing the user to the main chat
        pass
    return _STRUCTURE_REDIRECT.format(title=title)


def _handle_shared_pipeline_control(project_id: str, feature: str, text: str) -> tuple[str, bool, bool] | None:
    """Let the app chat continue a Receptor/Orchestrator flow for this feature.

    Returns (reply, building, data_changed). This keeps confirmation, publish, and
    cancel actions inside the feature screen instead of sending the user to the
    main chat.
    """
    from app.reception import service as reception

    flow = reception.get_flow(project_id)
    stage = flow.get("stage")
    flow_feature = flow.get("feature")
    if flow_feature and flow_feature != feature:
        return None
    if stage == "confirm" and flow_feature == feature:
        if reception.is_cancel(text) or reception.is_rejection(text):
            reception.clear_flow(project_id)
            return "依頼を取りやめました。このアプリチャットから別の依頼を続けられます。", False, False
        if reception.is_plan_ok(text):
            res = reception.dispatch_confirmed(project_id)
            return (
                res.get("reply") or "制作チームに依頼しました。進捗はこのアプリ画面に表示されます。",
                bool(res.get("building")),
                False,
            )
        reception.start_confirm_bg(
            project_id,
            flow.get("mode", "edit"),
            feature,
            reception.strip_user_context(flow.get("goal") or "") + "\n\n[ユーザーの修正・追記] " + text,
        )
        return "承知しました。依頼内容を更新して、このアプリ画面で確認できるようにします。", True, False

    if stage == "built" and flow_feature == feature:
        if reception.is_cancel(text) or reception.is_rejection(text):
            reception.clear_flow(project_id)
            return "変更候補を破棄しました。現在公開中のアプリはそのままです。", False, False
        if reception.is_plan_ok(text):
            from app.control_plane import approvals, registry

            candidate = flow.get("candidate") or {}
            if flow.get("mode") == "edit":
                title = candidate.get("title") or reception.feature_title(project_id, feature)
                approvals.publish_edit(project_id, feature, candidate)
                registry.append_requirements(project_id, feature, [flow.get("goal") or ""])
                reception.clear_flow(project_id)
                return f"「{title}」を更新しました。", False, True
            approval_id = flow.get("approval_id")
            if approval_id:
                res = approvals.approve(approval_id)
                activated_feature = res.get("feature") or feature
                registry.append_requirements(project_id, activated_feature, [flow.get("goal") or ""])
                reception.clear_flow(project_id)
                return f"公開しました。「{reception.feature_title(project_id, activated_feature)}」を左メニューに追加しました。", False, True
            reception.clear_flow(project_id)
            return "公開対象が見つかりませんでした。もう一度このアプリチャットから依頼してください。", False, False
    return None


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


def _specialist_model_tier(
    text: str,
    *,
    direct_state: bool = False,
    has_images: bool = False,
) -> ModelTier:
    """Use the stronger tier when a Specialist Worker must reason before acting."""
    normalized = _normalize_text(text)
    if direct_state or has_images or _needs_web_search(normalized):
        return ModelTier.PRO
    operation_groups = (
        ("入れて", "追加", "登録", "作って", "作成"),
        ("変更", "更新", "移動", "直して", "修正"),
        ("削除", "消して", "クリア", "初期化"),
        ("メモ", "本文", "詳細", "追記", "記入"),
        ("調べ", "探して", "検索", "候補"),
    )
    matched_groups = sum(any(word in normalized for word in group) for group in operation_groups)
    return ModelTier.PRO if matched_groups >= 2 else ModelTier.FLASH


def _feature_connectors_context(project_id: str, feature: str, user_uid: str | None) -> str:
    """Summarize app-scoped connectors for the Specialist Worker without secrets."""
    if not user_uid:
        return ""
    try:
        docs = get_db().collection(_APP_CONNECTORS).where("uid", "==", user_uid).stream()
    except Exception:  # noqa: BLE001
        return ""
    lines: list[str] = []
    for doc in docs:
        data = doc.to_dict() or {}
        if data.get("project_id") != project_id or data.get("feature") != feature:
            continue
        actions = data.get("actions") if isinstance(data.get("actions"), dict) else {}
        auth = data.get("auth") if isinstance(data.get("auth"), dict) else {}
        lines.append(
            f"- connector_id={data.get('connector_id')}, label={data.get('label') or data.get('connector_id')}, "
            f"base_url={data.get('base_url')}, auth_type={auth.get('type') or 'none'}, "
            f"auth_configured={bool(auth and auth.get('type') != 'none')}"
        )
        for action_id, action in list(actions.items())[:10]:
            if not isinstance(action, dict):
                continue
            lines.append(
                f"  - action {data.get('connector_id')}.{action_id}: "
                f"{action.get('method')} {action.get('path')} side_effect={action.get('side_effect')} "
                f"description={action.get('description') or ''}"
            )
        if len(lines) >= 80:
            lines.append("  ...(truncated)")
            break
    if not lines:
        return ""
    return (
        "[このアプリに登録済みの外部API connector]\n"
        "以下はユーザー/アプリ単位で登録された connector の公開情報です。auth token/password/header_value は渡されていません。\n"
        + "\n".join(lines)
        + "\n"
    )


def _app_runtime_context(project_id: str, feature: str, user_uid: str | None) -> str:
    connectors = _feature_connectors_context(project_id, feature, user_uid)
    return (
        "[AgentForge ミニアプリ runtime API]\n"
        "- AF.load()/AF.save(state): このアプリの永続 state を読み書きする。接続情報やtoken/passwordはstateに保存しない。\n"
        "- AF.defineConnector(def): このアプリ専用の外部API connectorをユーザー操作で登録する。\n"
        "- AF.listConnectors()/AF.deleteConnector(id): 登録済み connector の確認/削除。\n"
        "- AF.api('connector.action', params): 登録済み connector action だけを呼び出す。任意URLへ直接fetchする設計ではない。\n"
        "- AF.openExternal(url): ユーザーのクリック操作に応じて http(s) URL をシェル経由で別タブに開く。生成HTMLで window.open や href 直入れは使わない。\n"
        "- AF.askWorker(text): アプリ内UIからこの Specialist Worker に相談/操作依頼する。\n"
        "- AF.setChatContext(id,label): 画面や対象ごとにこのワーカーの会話文脈を分ける。\n"
        "- AF.setChatVisible(bool): 画面ごとにチャット欄の表示だけを切り替える。\n"
        + connectors
    )


def _web_search_context(text: str) -> str:
    if not _needs_web_search(text):
        return ""
    query = _web_search_query(text)
    results = web_search_tool.web_search(query, max_results=5)
    if not results:
        return (
            "[リアルタイムWeb検索]\n"
            f"検索クエリ: {query}\n"
            "検索結果を取得できませんでした。必要ならその旨を明記し、既知情報だけで断定しないでください。\n"
        )
    fetched: list[str] = []
    for result in results[:2]:
        body = web_search_tool.web_fetch(result.url, max_chars=1200)
        if body:
            fetched.append(f"- {result.title}\n  URL: {result.url}\n  抜粋: {body}")
    return (
        "[リアルタイムWeb検索結果]\n"
        f"検索クエリ: {query}\n"
        f"{web_search_tool.format_search_results(results)}\n"
        + (("[Web閲覧抜粋]\n" + "\n".join(fetched) + "\n") if fetched else "")
        + "上記は現在のWeb検索スニペットです。アプリ内の本文/メモへ入れる場合は、短く要約し、必要に応じて確認事項を添えてください。\n"
    )


def _needs_web_search(text: str) -> bool:
    t = _normalize_text(text)
    return any(w in t for w in ("検索", "探して", "調べて", "最新", "現在", "近く", "周辺", "営業時間", "ニュース", "今日"))


def _web_search_query(text: str) -> str:
    t = _normalize_text(text)
    for word in (
        "メモに",
        "メモへ",
        "本文に",
        "説明欄に",
        "記入して",
        "入れておいて",
        "入れて",
        "書いておいて",
        "書いて",
        "追記して",
        "追加して",
        "メモして",
        "しておいて",
    ):
        t = t.replace(word, " ")
    t = re.sub(r"(を)?(?:\d+|一|二|三|四|五)?\s*(?:件|つ)?\s*(探して|調べて|検索して)", " ", t)
    t = re.sub(r"(?:\d+|一|二|三|四|五)\s*(?:件|つ)(?:候補|くらい|ほど)?", " ", t)
    return " ".join(t.split())[:200] or _normalize_text(text)[:200]


def _app_worker_operation_manual(feature: str, title: str, tools: list[dict], manifest: dict, runtime_context: str = "") -> str:
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
        "- 1つの文に複数操作が含まれる場合は、小さな操作列に分解して順に処理する。"
        "例: 『予定を追加して、そのメモに調査結果を入れて』は create 後に memo/body/detail を update/append。"
        "例: 『タスクを作って、詳細に要点を書いて、締切も設定して』は create 後に複数フィールドを更新。"
        "対象が一意、または現在開いている詳細 context で一意なら実行し、固定文言に合わないだけで聞き返さない。\n"
        "- 『メモに〜を記入して』『説明欄に〜を書いて』『本文に〜を追記して』のように、"
        "既存フィールドへ文章を入れる依頼は更新意図。対象と本文が分かるなら content として、"
        "memo/body/note/update 系の最も近いAPIまたは state 更新を使う。"
        "ユーザーが『探して』『考えて』『まとめて』と言っている場合は、あなたが短い実用文を作って引数に入れる。"
        "『持っていくものとしてノート』『確認事項として集合時間』のような断片的な指示は、そのまま転記せず、"
        "『持っていくもの: ノート』『確認事項: 集合時間』のようにラベル付きで整理して保存する。\n"
        "- 接続失敗の原因確認、ログ/状態確認、APIレスポンスの切り分け、使い方の確認は制作ではなく category=chat。"
        "登録済み connector や runtime API の文脈を使って、このアプリ内で診断・説明する。"
        "ユーザーが明示的に『直して』『修正して』『実装して』と頼んだ場合だけ category=structure を検討する。\n"
        "- 世間一般のアプリ仕様、UI/UX事例、比較、ベストプラクティス、設計方針の相談も category=chat。"
        "すぐに制作へ進めず、判断材料・選択肢・推奨案を答える。\n"
        "- ただし、宣言APIで表せない新機能追加・画面変更は category=structure としてメインチャットへ取り次ぐ。\n"
    )
    if generated_manual:
        common += "\n[このアプリ固有の専門ワーカー指示]\n" + generated_manual[:4000] + "\n"
    if example_lines:
        common += "\n[このアプリで想定される自然言語指示とAPI対応例]\n" + "\n".join(example_lines) + "\n"
    if runtime_context:
        common += "\n" + runtime_context
    common += (
        "\n[アプリ内チャットの受付方針]\n"
        "- ユーザーがこのアプリの使い方、ログイン/接続設定、どのボタンを押すか、API連携の流れを聞いた場合は、"
        "この文脈を使ってアプリ内で完結する回答をする。\n"
        "- ユーザーが『原因を確認』『調査して』『接続に失敗する』と依頼した場合も、まず category=chat として"
        "診断・切り分け・確認結果を返す。制作チームへの取り次ぎは、改修内容が明確になった後に限る。\n"
        "- 一般仕様や設計相談、他サービス事例、UI/UX比較を聞かれた場合も category=chat として相談に乗る。\n"
        "- UI/項目/API機能追加などアプリ自体の改修が必要な場合は category=structure としてメインチャット相当の"
        "Receptor/Orchestrator に取り次ぐ。ユーザーに『メインチャットへ移動して』とだけ返さない。\n"
    )
    return common


def _respond_state_content(
    project_id: str,
    feature: str,
    text: str,
    history: list[dict],
    manifest: dict,
    original_text: str | None = None,
    images: list | None = None,
    user_call_name: str | None = None,
    context_id: str | None = None,
    context_label: str | None = None,
    user_uid: str | None = None,
) -> tuple[str, list[dict], dict | None] | None:
    """Let the Specialist Worker edit AF.load/AF.save state directly.

    This is the generic path for unknown future data-centered mini-apps. The app
    declares its persisted state schema; the worker reads the current state,
    returns a complete replacement state, and the backend saves it atomically.
    """
    original_text = original_text or text
    if not _can_direct_state_edit(manifest):
        return None
    llm = get_llm()
    if not llm.enabled:
        return None
    title = manifest.get("title") or feature
    state_schema = manifest.get("state_schema") or {}
    current_state = _load_app_state(project_id, feature)
    tools = manifest.get("commands") or []
    runtime_context = _app_runtime_context(project_id, feature, user_uid)
    search_context = _web_search_context(original_text + "\n" + text)
    prompt = (
        f"{agents.load('feature_worker')}\n\n"
        f"{_user_context_instruction(user_call_name)}\n\n"
        f"対象ミニアプリ: {title}（slug: {feature}）。あなたはこのミニアプリの操作用 Specialist Worker。\n"
        "このアプリは AF.load()/AF.save() の永続化 state を持つ。ユーザーの自然文を読み、"
        "アプリの中身の変更は persisted state を直接編集してよい。\n"
        f"今日の日付（Asia/Tokyo）: {_today_context()}\n"
        f"現在のアプリ画面/作業文脈: id={context_id or 'default'}, label={context_label or context_id or 'default'}\n"
        f"state_schema(JSON Schema風): {_compact_json(state_schema, 12000)}\n"
        f"現在のstate: {_compact_json(current_state, 32000)}\n"
        f"補助的に使えるcommands（必要な場合のみ参考）: {json.dumps(tools, ensure_ascii=False)}\n"
        f"{_app_worker_operation_manual(feature, title, tools, manifest, runtime_context)}\n"
        f"{search_context}"
        f"直近の会話: {json.dumps(history[-8:], ensure_ascii=False)}\n"
        + ("【添付画像あり】画像内のテキストも読み取り、state更新に必要なら反映すること。\n" if images else "")
        + f"ユーザーの元の指示: {original_text}\n"
        + f"解釈済みの作業指示: {text}\n\n"
        "JSONのみで出力:\n"
        '{"category":"content|structure|chat","reply":"<日本語の短い返答>",'
        '"state":<更新後の完全なstate。変更しない場合はnull>,'
        '"ops":[{"op":"create|update|delete|clear","target":"<対象の短い説明>"}]}\n\n'
        "判断ルール:\n"
        "0. まずユーザーの依頼を意味単位に分解し、暗黙の対象・目的・本文を補って、保存しやすい構造へ言い換える。"
        "そのうえで state_schema に合う形に変換する。固定文言への一致判定だけで処理しない。\n"
        "1. 追加/更新/削除/一括削除/メモ追記/状態変更など、state_schema内のデータ変更で表せるなら category=content。\n"
        "2. state は差分ではなく、保存すべき完全な新状態を返す。既存の無関係なデータは保持する。\n"
        "2a. 追加する配列要素に schema 上 id がある場合は、既存 id と衝突しない短い文字列 id を必ず作る。\n"
        "2b. スケジュールのタイトルには予定名だけを入れる。"
        "例: '予定に出張を入れて' の title は '出張'。'予定' '入れて' などの依頼語を含めない。\n"
        "3. 新しい画面・新しい項目・UI変更・state_schemaに無いデータ構造追加は category=structure。\n"
        "4. 日付や時刻は正規化する。時刻が15:65のように不自然なら実行せず category=chat で『16:05の意味でよろしいですか？』のように確認する。\n"
        "5. 削除/一括削除は、対象範囲が明示されていれば実行してよい。対象が曖昧なら category=chat で確認する。\n"
        "6. 純粋な質問・使い方相談・現状確認・原因調査・接続失敗の診断・一般仕様相談は category=chat。stateはnull。\n"
        "7. 担当外の構造変更は category=structure とし、ここではstateを変えない。\n"
        "8. 本文/メモ/詳細へ入れる内容は、そのまま転記せず、ユーザーの意図が分かるラベル・箇条書き・短い見出しで整理する。"
        "例:『昼ご飯の予定を入れて。内容は笹かまぼこ』→『予定: 昼ご飯\\n内容: 笹かまぼこ』。\n"
    )
    data = _safe_json(llm, prompt, images=images, tier=ModelTier.PRO)
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
    if _state_contains_unresolved_instruction(original_text + "\n" + text, current_state, new_state):
        return None
    if _state_contains_invalid_structured_value(feature, current_state, new_state):
        return None
    _save_app_state(project_id, feature, new_state)
    ops = data.get("ops") if isinstance(data.get("ops"), list) else []
    changed = [{"entity_id": str(op.get("target") or "app_state")[:80], "op": str(op.get("op") or "update")} for op in ops[:20] if isinstance(op, dict)]
    if not changed:
        changed = [{"entity_id": "app_state", "op": "update"}]
    return reply or "更新しました。", changed, None


def _interpret_app_request(
    feature: str,
    title: str,
    text: str,
    history: list[dict],
    manifest: dict,
    context_id: str | None = None,
    context_label: str | None = None,
    user_call_name: str | None = None,
    images: list | None = None,
) -> dict:
    """Use the LLM as an intent normalizer before applying state/command rules."""
    llm = get_llm()
    if not llm.enabled:
        return {"normalized_request": text, "intent": "content", "operations": []}
    tools = manifest.get("commands") or []
    state_schema = manifest.get("state_schema") or {}
    web_context = _web_search_context(text)
    prompt = (
        f"{agents.load('feature_worker')}\n\n"
        f"{_user_context_instruction(user_call_name)}\n\n"
        f"対象ミニアプリ: {title}（slug: {feature}）。\n"
        f"現在のアプリ画面/作業文脈: id={context_id or 'default'}, label={context_label or context_id or 'default'}\n"
        f"state_schema: {_compact_json(state_schema, 9000)}\n"
        f"commands: {json.dumps(tools, ensure_ascii=False)}\n"
        f"{web_context}"
        f"直近の会話: {json.dumps(history[-6:], ensure_ascii=False)}\n"
        + ("【添付画像あり】画像内のテキストも読み取り、作業指示に反映すること。\n" if images else "")
        + f"ユーザーの元の指示: {text}\n\n"
        "あなたの仕事は実行ではなく、後段の state_schema / commands に載せやすい作業指示へ作り直すこと。\n"
        "JSONのみで出力:\n"
        '{"normalized_request":"<後段に渡す作業指示。1〜6行>",'
        '"intent":"content|structure|chat",'
        '"operations":[{"op":"create|update|append|delete|query|chat|structure","target":"<対象>",'
        '"content":"<整理済み本文>","fields":{"date":"YYYY-MM-DD","time":"HH:MMまたは空",'
        '"title":"<予定名だけ>","memo":"<整理・調査済み本文>"}}],'
        '"reason":"<短く>"}\n\n'
        "ルール:\n"
        "- 元の指示をそのまま転記しない。暗黙の対象、現在開いている文脈、本文、検索/調査の必要性を補う。\n"
        "- 複合命令は操作列に分解する。\n"
        "- スケジュールの '予定にAを入れて' は、予定名をAとして構造化する。"
        "title に '予定' '入れて' '追加して' などの依頼語を残さない。\n"
        "- スケジュール操作は fields に date/time/title/memo を分離する。"
        "予定追加とメモ調査が一緒なら1つの create にまとめ、memo に調査結果を入れる。\n"
        "- タスク管理で『Aというタスクを追加して。案としてBを書いて』のような依頼は、"
        "タスク名をA、詳細/本文をBとして分ける。依頼文全体を title に入れてはいけない。\n"
        "- 本文/メモ/詳細に入れる内容はラベル・箇条書き・短い見出しで整理する。\n"
        "- 『調べて/探して/検索して』があり、上に [リアルタイムWeb検索結果] がある場合は、"
        "その検索結果を先に読んで、候補名・要点・確認事項を含む保存本文まで作る。"
        "後段へ『調べて』という未処理作業を残してはいけない。\n"
        "- Web検索結果が無い場合だけ、『未確認。追加確認が必要』を含めて保存/回答する。\n"
        "- UIや機能追加は intent=structure、純粋な質問は intent=chat。\n"
    )
    data = _safe_json(
        llm,
        prompt,
        images=images,
        tier=_specialist_model_tier(
            text,
            direct_state=_can_direct_state_edit(manifest),
            has_images=bool(images),
        ),
    )
    normalized = str(data.get("normalized_request") or "").strip()
    operations = data.get("operations") if isinstance(data.get("operations"), list) else []
    return {
        "normalized_request": normalized[:2000] or text,
        "intent": str(data.get("intent") or "content").strip(),
        "operations": operations[:12],
    }


def _state_contains_unresolved_instruction(user_text: str, old_state, new_state) -> bool:
    """Reject LLM state edits that copied the user's request instead of executing it."""
    if not any(w in _normalize_text(user_text) for w in ("探して", "調べて", "検索", "メモして", "記入して", "入れておいて")):
        return False
    old_strings = set(_state_strings(old_state))
    user_norm = _normalize_text(user_text)
    for value in _state_strings(new_state):
        if value in old_strings:
            continue
        v = _normalize_text(value)
        if len(v) < 10:
            continue
        if any(w in v for w in ("探して", "調べて", "検索して", "メモして", "記入して", "入れておいて")):
            return True
        # The LLM sometimes drops only the final verb and still stores the request
        # shape. Treat high-overlap search instructions as unresolved.
        core = re.sub(r"(メモ|本文|詳細|に|へ|を|して|ください|おいて|件|つ|候補|\d+|一|二|三|四|五)", "", v)
        search_targets = ("レストラン", "ラーメン", "店", "料理", "食事", "ホテル", "駅", "周辺", "近く")
        if (
            any(w in core for w in search_targets)
            and any(w in user_norm for w in search_targets)
            and any(w in user_norm for w in ("調べ", "探", "検索"))
        ):
            return True
    return False


def _state_strings(value) -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            out.extend(_state_strings(item))
    elif isinstance(value, list):
        for item in value:
            out.extend(_state_strings(item))
    return out


def _schedule_title_looks_like_instruction(title: str) -> bool:
    normalized = _normalize_text(title).strip("。、 ")
    if not normalized or len(normalized) > 80:
        return True
    if normalized in {"予定", "スケジュール", "予定を入れて", "予定を追加"}:
        return True
    return bool(
        re.search(
            r"(?:を|に)?(?:入れて|いれて|追加して|登録して|作って|作成して|"
            r"メモして|記入して|書いて)(?:おいて|ください)?$",
            normalized,
        )
    )


def _state_contains_invalid_structured_value(feature: str, old_state, new_state) -> bool:
    """Reject newly generated values that still look like user instructions."""
    if feature != "schedule" or not isinstance(new_state, dict):
        return False
    old_events = old_state.get("events", []) if isinstance(old_state, dict) else []
    old_by_id = {
        str(event.get("id")): event
        for event in old_events
        if isinstance(event, dict) and event.get("id") is not None
    }
    for event in new_state.get("events", []):
        if not isinstance(event, dict):
            continue
        old_event = old_by_id.get(str(event.get("id")))
        title = str(event.get("title") or "")
        if old_event is not None and title == str(old_event.get("title") or ""):
            continue
        if _schedule_title_looks_like_instruction(title):
            return True
    return False


def _apply_structured_schedule_plan(
    project_id: str,
    feature: str,
    interpretation: dict,
    original_text: str,
) -> tuple[str, list[dict], dict | None] | None:
    """Validate and apply an LLM-normalized schedule operation without reparsing prose."""
    if interpretation.get("intent") != "content":
        return None
    operations = interpretation.get("operations")
    if not isinstance(operations, list):
        return None
    create = next(
        (
            op
            for op in operations
            if isinstance(op, dict)
            and op.get("op") == "create"
            and any(
                token in str(op.get("target") or "").lower()
                for token in ("event", "schedule", "予定", "スケジュール")
            )
        ),
        None,
    )
    if not create or not isinstance(create.get("fields"), dict):
        return None
    fields = create["fields"]
    date = str(fields.get("date") or "").strip()
    time = str(fields.get("time") or "").strip()
    title = str(fields.get("title") or "").strip()
    memo = str(fields.get("memo") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return None
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return None
    if time and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time):
        return None
    if _schedule_title_looks_like_instruction(title):
        return None
    memo_normalized = _normalize_text(memo)
    if any(
        phrase in memo_normalized
        for phrase in ("探して", "調べて", "検索して", "メモして", "記入して", "入れておいて")
    ):
        return None

    state = _load_app_state(project_id, feature)
    if not isinstance(state, dict):
        state = {}
    events = state.get("events")
    if not isinstance(events, list):
        events = []
    existing_ids = {str(event.get("id")) for event in events if isinstance(event, dict)}
    event_id = f"e_{uuid.uuid4().hex[:10]}"
    while event_id in existing_ids:
        event_id = f"e_{uuid.uuid4().hex[:10]}"
    event = {"id": event_id, "date": date, "time": time, "title": title, "memo": memo}
    next_state = {**state, "events": [*events, event]}
    _save_app_state(project_id, feature, next_state)
    label = f"{date} {time or '終日'}"
    return (
        f"{label} に「{title}」を追加" + ("し、メモも更新しました。" if memo else "しました。"),
        [{"entity_id": event_id, "op": "create"}] + ([{"entity_id": event_id, "op": "update"}] if memo else []),
        None,
    )


def _default_state_update(
    project_id: str,
    feature: str,
    text: str,
    manifest: dict,
    context_id: str | None = None,
    context_label: str | None = None,
) -> tuple[str, list[dict], dict | None] | None:
    if feature == "schedule":
        return _default_schedule_state_update(project_id, feature, text, context_id=context_id, context_label=context_label)
    if feature == "task_manager":
        return _default_task_manager_state_update(project_id, feature, text, context_id=context_id, context_label=context_label)
    if feature == "memo":
        return _default_memo_state_update(project_id, feature, text)
    if feature == "household_budget":
        return _default_household_budget_state_update(project_id, feature, text)
    if not _can_direct_state_edit(manifest):
        return None
    return None


def _default_schedule_state_update(
    project_id: str,
    feature: str,
    text: str,
    context_id: str | None = None,
    context_label: str | None = None,
) -> tuple[str, list[dict], dict | None] | None:
    parsed_add_with_memo = _parse_schedule_add_with_memo(project_id, feature, text)
    if parsed_add_with_memo is not None:
        return parsed_add_with_memo

    parsed_memo = _parse_schedule_memo_update(project_id, feature, text, context_id=context_id, context_label=context_label)
    if parsed_memo is not None:
        return parsed_memo

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


def _parse_schedule_add_with_memo(project_id: str, feature: str, text: str) -> tuple[str, list[dict], dict | None] | None:
    t = _normalize_text(text)
    if not t or "メモ" not in t:
        return None
    if not any(w in t for w in ("予定", "スケジュール", "入れて", "追加", "登録")):
        return None
    if not any(w in t for w in ("記入", "入れて", "書いて", "追記", "追加", "メモして", "候補")):
        return None

    memo_match = re.search(r"メモ(?:欄)?(?:に|へ|を)?", t)
    if not memo_match:
        return None
    before_memo = t[: memo_match.start()].strip(" 、。")
    after_memo = t[memo_match.end():].strip(" 、。")
    parsed = _parse_schedule_add(before_memo) or _parse_schedule_add(t)
    if not parsed:
        return None
    memo = _schedule_memo_text_from_instruction("メモに" + after_memo) if after_memo else ""
    if not memo:
        return None

    state = _load_app_state(project_id, feature)
    if not isinstance(state, dict):
        state = {}
    events = state.get("events")
    if not isinstance(events, list):
        events = []
    existing_ids = {str(e.get("id")) for e in events if isinstance(e, dict) and e.get("id")}
    eid = f"e_{uuid.uuid4().hex[:10]}"
    while eid in existing_ids:
        eid = f"e_{uuid.uuid4().hex[:10]}"
    event = {"id": eid, **parsed, "memo": memo}
    events.append(event)
    state["events"] = events
    _save_app_state(project_id, feature, state)
    label = f"{event['date']} {event.get('time') or '終日'}"
    return (
        f"{label} に「{event['title']}」を追加し、メモも更新しました。",
        [{"entity_id": eid, "op": "create"}, {"entity_id": eid, "op": "update"}],
        None,
    )


def _parse_schedule_memo_update(
    project_id: str,
    feature: str,
    text: str,
    context_id: str | None = None,
    context_label: str | None = None,
) -> tuple[str, list[dict], dict | None] | None:
    t = _normalize_text(text)
    if not t:
        return None
    context_is_memo = "メモ" in _normalize_text(context_label or "")
    write_word = any(w in t for w in ("記入", "入れて", "書いて", "追記", "追加", "メモして", "メモを", "候補を", "候補", "しておいて"))
    memo_target_word = any(w in t for w in ("メモ", "候補", "結果", "情報", "詳細", "備考", "持ち物", "店", "レストラン", "食事処", "ラーメン"))
    lookup_word = any(w in t for w in ("探して", "調べて", "検索", "近く", "周辺", "徒歩圏", "候補"))
    if context_is_memo and lookup_word:
        write_word = True
    if not write_word or not (memo_target_word or lookup_word):
        return None
    state = _load_app_state(project_id, feature)
    if not isinstance(state, dict):
        return "まだ予定が保存されていません。先に対象の予定を保存してください。", [], None
    events = state.get("events")
    if not isinstance(events, list):
        return "まだ予定が保存されていません。先に対象の予定を保存してください。", [], None
    candidates = [e for e in events if isinstance(e, dict)]
    if not candidates:
        return "まだ予定がありません。先に対象の予定を追加してください。", [], None

    focused = _schedule_context_event(candidates, context_id, context_label)
    date = _parse_date(t)
    quoted = _extract_quoted(t)
    target_title = ""
    if quoted:
        for ev in candidates:
            title = str(ev.get("title") or "")
            if quoted == title or quoted in title or title in quoted:
                target_title = title
                break
    if not target_title:
        for ev in candidates:
            title = str(ev.get("title") or "").strip()
            if title and title in t:
                target_title = title
                break

    matched = [focused] if focused else candidates
    if date:
        matched = [e for e in matched if e.get("date") == date]
    if target_title:
        matched = [e for e in matched if str(e.get("title") or "") == target_title]

    if len(matched) != 1:
        if len(candidates) == 1 and not date and not target_title:
            matched = candidates
        else:
            return "どの予定のメモに記入するか特定できません。日付か予定タイトルを指定してください。", [], None

    memo = _schedule_memo_text_from_instruction(t)
    if not memo:
        if any(w in t for w in ("探して", "調べて", "検索", "候補")):
            return None
        return "メモに入れる内容を読み取れませんでした。記入したい本文を教えてください。", [], None
    target = matched[0]
    append = any(w in t for w in ("追記", "書き足", "追加で", "付け足"))
    current = str(target.get("memo") or "").strip()
    target["memo"] = (current + "\n" + memo).strip() if append and current else memo
    state["events"] = events
    _save_app_state(project_id, feature, state)
    title = str(target.get("title") or "予定")
    return f"「{title}」のメモを更新しました。", [{"entity_id": str(target.get("id") or "events"), "op": "update"}], None


def _schedule_context_event(events: list[dict], context_id: str | None, context_label: str | None) -> dict | None:
    ctx = _context_id(context_id)
    label = _normalize_text(context_label or "")
    if ctx and ctx != _DEFAULT_CONTEXT:
        raw = ctx
        if raw.startswith("event_"):
            raw = raw[len("event_"):]
        if raw.startswith("schedule_event_"):
            raw = raw[len("schedule_event_"):]
        for ev in events:
            eid = str(ev.get("id") or "")
            if eid and (ctx == eid or raw == eid):
                return ev
    if label:
        for ev in events:
            title = _normalize_text(str(ev.get("title") or ""))
            if title and (title == label or title in label or label in title):
                return ev
    return None


def _schedule_memo_text_from_instruction(text: str) -> str:
    t = _normalize_text(text).strip(" 。")
    m = re.search(r"メモ(?:欄)?(?:に|へ|を)\s*(.+?)(?:を)?(?:記入|入れて|書いて|追記|追加|メモして)(?:ください|して)?$", t)
    if m and m.group(1).strip(" 。、"):
        content = m.group(1).strip(" 。、")
    else:
        content = _memo_request_content(t)
    if not content:
        return ""
    generated = _draft_memo_from_request(content)
    return generated or content


def _memo_request_content(text: str) -> str:
    content = _normalize_text(text).strip(" 。、")
    content = re.sub(r"メモ(?:欄)?(?:に|へ|を)?\s*", "", content).strip(" 。、")
    content = re.sub(r"(?:を)?(?:記入|入れて|書いて|追記|追加|メモして)(?:ください|して|おいて)?$", "", content).strip(" 。、")
    content = re.sub(r"(?:候補|結果|情報)(?:を)?(?:3|三|5|五)?件?$", "", content).strip(" 。、")
    content = re.sub(r"(?:3|三|5|五)?件(?:の)?候補(?:を)?$", "", content).strip(" 。、")
    return content


def _draft_memo_from_request(content: str) -> str:
    """Small deterministic helper for common 'think/search and write it' memo requests.

    The Specialist Worker still handles open-ended generation when the LLM is
    available. This fallback keeps default apps useful when the model misses a
    clear memo-writing command.
    """
    c = _normalize_text(content)
    if _needs_web_search(c):
        results = web_search_tool.web_search(_web_search_query(c), max_results=5)
        if results:
            lines = ["Web検索で確認した候補:"]
            for result in results[:5]:
                item = f"- {result.title}"
                if result.snippet:
                    item += f": {result.snippet}"
                if result.url:
                    item += f"\n  {result.url}"
                lines.append(item)
            lines.append("※営業時間・営業日・予約可否は当日に公式情報で確認する。")
            return "\n".join(lines)
        return (
            "Web検索結果を取得できませんでした。\n"
            f"確認したい内容: {_web_search_query(c)}\n"
            "※現在情報が必要なため、後で再検索してください。"
        )
    if "仙台駅" in c and "仙台名物" in c and any(w in c for w in ("食事", "食事処", "店", "レストラン", "ランチ", "夕食")):
        return (
            "仙台駅周辺で確認したい仙台名物候補:\n"
            "- 牛たん通り（仙台駅3F）: 牛たん定食を駅直結で食べやすい。\n"
            "- 伊達の牛たん本舗 本店: 仙台駅から徒歩圏の牛たん候補。\n"
            "- ずんだ茶寮 仙台駅店: ずんだ餅・ずんだシェイクなどの仙台名物候補。\n"
            "※営業時間と混雑状況は当日に確認する。"
        )
    return _structure_short_note(c)


def _structure_short_note(content: str) -> str:
    """Turn short user fragments into useful note lines instead of raw copies."""
    c = _normalize_text(content).strip(" 。、")
    if not c:
        return ""
    plan_content = re.search(
        r"(.+?)(?:の)?(?:予定|メモ|項目)?(?:を)?(?:入れて|追加して|登録して|書いて|記入して)?[。 、,]*内容(?:は|:|：)\s*(.+)",
        c,
    )
    if plan_content:
        topic = _clean_structured_note_value(plan_content.group(1))
        detail = _clean_structured_note_value(plan_content.group(2))
        lines = []
        if topic:
            lines.append(f"予定: {topic}")
        if detail:
            lines.append(f"内容: {detail}")
        if lines:
            return "\n".join(lines)
    label_content = re.search(r"(.+?)(?:として|は|:|：)\s*(.+)", c)
    if label_content:
        label = _clean_structured_note_label(label_content.group(1))
        detail = _clean_structured_note_value(label_content.group(2))
        if label and detail:
            return f"{label}: {detail}"
    patterns = [
        (r"(?:持っていくもの|持ち物|持参(?:するもの)?)(?:として|は|に|を)?\s*(.+)", "持っていくもの"),
        (r"(?:確認事項|確認すること|要確認)(?:として|は|に|を)?\s*(.+)", "確認事項"),
        (r"(?:場所|会場|行き先)(?:として|は|に|を)?\s*(.+)", "場所"),
        (r"(?:やること|TODO|todo|タスク)(?:として|は|に|を)?\s*(.+)", "やること"),
        (r"(?:目的|ねらい)(?:として|は|に|を)?\s*(.+)", "目的"),
        (r"(?:連絡先|問い合わせ先)(?:として|は|に|を)?\s*(.+)", "連絡先"),
    ]
    for pat, label in patterns:
        m = re.search(pat, c, flags=re.I)
        if m:
            value = _clean_structured_note_value(m.group(1))
            if value:
                return f"{label}: {value}"
    return ""


def _clean_structured_note_value(value: str) -> str:
    out = _normalize_text(value).strip(" 。、")
    out = re.sub(r"(?:を)?(?:記入|入れて|書いて|追記|追加|メモして)(?:ください|して|おいて)?$", "", out).strip(" 。、")
    return out


def _clean_structured_note_label(value: str) -> str:
    out = _normalize_text(value).strip(" 。、")
    out = re.sub(r"(?:の)?(?:予定|メモ|項目|内容)$", "", out).strip(" 。、")
    mapping = {
        "昼ご飯": "予定",
        "昼ごはん": "予定",
        "昼食": "予定",
        "ランチ": "予定",
        "夕ご飯": "予定",
        "夕食": "予定",
        "朝ご飯": "予定",
        "朝食": "予定",
    }
    return mapping.get(out, out)


def _default_memo_state_update(project_id: str, feature: str, text: str) -> tuple[str, list[dict], dict | None] | None:
    t = _normalize_text(text)
    if not t:
        return None
    write_intent = any(w in t for w in ("記入", "入れて", "書いて", "追記", "追加", "書き足", "本文", "メモして"))
    if not write_intent:
        return None
    if _intent_family(t) == "delete":
        return None

    state = _load_app_state(project_id, feature)
    if not isinstance(state, dict):
        state = {}
    notes = state.get("notes")
    if not isinstance(notes, list):
        notes = []
    note_items = [n for n in notes if isinstance(n, dict)]

    target_title = _memo_target_title(t, note_items)
    matched = note_items
    if target_title:
        matched = [n for n in note_items if _note_title(n) == target_title]

    create_new = any(w in t for w in ("新規", "新しいメモ", "メモを作", "メモ作", "作成"))
    if not note_items or create_new:
        body = _memo_body_text_from_instruction(t)
        if not body:
            return "メモに入れる本文を読み取れませんでした。記入したい内容を教えてください。", [], None
        title = target_title or _memo_title_from_instruction(t) or "メモ"
        note = {"id": f"n_{uuid.uuid4().hex[:10]}", "title": title, "body": body, "updated": int(datetime.now(timezone.utc).timestamp() * 1000)}
        notes.append(note)
        state["notes"] = notes
        _save_app_state(project_id, feature, state)
        return f"「{title}」のメモを作成しました。", [{"entity_id": note["id"], "op": "create"}], None

    if len(matched) != 1:
        if len(note_items) == 1 and not target_title:
            matched = note_items
        else:
            return "どのメモに記入するか特定できません。メモのタイトルを指定してください。", [], None

    body = _memo_body_text_from_instruction(t)
    if not body:
        return "メモに入れる本文を読み取れませんでした。記入したい内容を教えてください。", [], None
    target = matched[0]
    append = any(w in t for w in ("追記", "書き足", "追加で", "付け足", "も入れて", "も書いて"))
    current = str(target.get("body") or "").strip()
    target["body"] = (current + "\n" + body).strip() if append and current else body
    target["updated"] = int(datetime.now(timezone.utc).timestamp() * 1000)
    state["notes"] = notes
    _save_app_state(project_id, feature, state)
    return f"「{_note_title(target)}」の本文を更新しました。", [{"entity_id": str(target.get("id") or "notes"), "op": "update"}], None


def _note_title(note: dict) -> str:
    title = str(note.get("title") or "").strip()
    if title:
        return title
    body = str(note.get("body") or "").strip()
    return (body.splitlines()[0][:20] if body else "無題").strip() or "無題"


def _memo_target_title(text: str, notes: list[dict]) -> str:
    quoted = _extract_quoted(text)
    if quoted:
        for note in notes:
            title = _note_title(note)
            if quoted == title or quoted in title or title in quoted:
                return title
    for note in notes:
        title = _note_title(note)
        if title and title != "無題" and title in text:
            return title
    m = re.search(r"(.+?)(?:メモ|ノート)(?:に|へ|の本文|本文)", text)
    if m:
        cand = m.group(1).strip(" 「『\"。 、")
        for note in notes:
            title = _note_title(note)
            if cand and (cand == title or cand in title or title in cand):
                return title
    return ""


def _memo_title_from_instruction(text: str) -> str:
    quoted = _extract_quoted(text)
    if quoted:
        return quoted[:40]
    m = re.search(r"(.+?)(?:メモ|ノート)(?:を|に|へ)?(?:作って|作成|新規)", text)
    if m:
        return m.group(1).strip(" 「『\"。 、")[:40]
    return ""


def _memo_body_text_from_instruction(text: str) -> str:
    t = _normalize_text(text).strip(" 。")
    for pat in (
        r"(?:本文|メモ|ノート)(?:欄)?(?:に|へ|を)\s*(.+?)(?:を)?(?:記入|入れて|書いて|追記|追加|メモして)(?:ください|して)?$",
        r"(.+?)(?:を)?(?:本文|メモ|ノート)(?:欄)?(?:に|へ)\s*(?:記入|入れて|書いて|追記|追加)(?:ください|して)?$",
    ):
        m = re.search(pat, t)
        if m:
            content = m.group(1).strip(" 。、")
            if content:
                return _draft_memo_from_request(content) or content
    content = re.sub(r"^.*?(?:本文|メモ|ノート)(?:欄)?(?:に|へ|を)?", "", t).strip(" 。、")
    content = re.sub(r"(?:を)?(?:記入|入れて|書いて|追記|追加|メモして)(?:ください|して)?$", "", content).strip(" 。、")
    if not content:
        return ""
    return _draft_memo_from_request(content) or content


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


def _default_task_manager_state_update(
    project_id: str,
    feature: str,
    text: str,
    context_id: str | None = None,
    context_label: str | None = None,
) -> tuple[str, list[dict], dict | None] | None:
    t = _normalize_text(text)
    if not t:
        return None
    detail_intent = any(w in t for w in ("詳細", "本文", "内容", "メモ", "案", "追記", "追加", "書いて", "記入"))
    if not detail_intent:
        return None
    state = _load_app_state(project_id, feature)
    if not isinstance(state, dict):
        return None
    tasks = state.get("tasks")
    if not isinstance(tasks, list):
        return None
    target = _task_context_task(tasks, context_id, context_label, state)
    if not target:
        return None
    html = _task_detail_html_from_instruction(t)
    if not html:
        return "詳細に入れる内容を読み取れませんでした。記入したい本文を教えてください。", [], None
    current = str(target.get("detail_html") or "")
    append = any(w in t for w in ("追記", "追加", "書き足", "付け足"))
    if _task_detail_is_empty(current, str(target.get("title") or "")):
        append = False
    target["detail_html"] = (current + html).strip() if append and current else html
    state["selected_task_id"] = str(target.get("id") or state.get("selected_task_id") or "")
    state["tasks"] = tasks
    _save_app_state(project_id, feature, state)
    title = str(target.get("title") or "タスク")
    return f"「{title}」の詳細を更新しました。", [{"entity_id": str(target.get("id") or "tasks"), "op": "update"}], None


def _task_context_task(tasks: list[dict], context_id: str | None, context_label: str | None, state: dict) -> dict | None:
    ctx = _context_id(context_id)
    if ctx.startswith("task_"):
        task_id = ctx.removeprefix("task_")
        for task in tasks:
            if isinstance(task, dict) and str(task.get("id") or "") == task_id:
                return task
    selected = str(state.get("selected_task_id") or "")
    if selected:
        for task in tasks:
            if isinstance(task, dict) and str(task.get("id") or "") == selected:
                return task
    label = _normalize_text(context_label or "")
    if label.startswith("詳細:"):
        name = label.split(":", 1)[1].strip()
        for task in tasks:
            title = str(task.get("title") or "")
            if title and (title == name or title in name or name in title):
                return task
    return None


def _task_detail_is_empty(html: str, title: str) -> bool:
    plain = re.sub(r"<[^>]+>", " ", html or "")
    plain = " ".join(plain.split())
    return not plain or "詳細はまだありません" in plain or plain == title


def _parse_task_add_request(text: str) -> dict | None:
    t = _normalize_text(text).strip(" 。、")
    if not t or not any(w in t for w in ("追加", "入れて", "作って", "登録")):
        return None
    split = re.search(
        r"(.+?)(?:という)?(?:タスク|やること|todo|to-do)?(?:を)?(?:追加|入れて|作って|登録)(?:して)?(?:おいて|ください)?(?:[。 、,]+|$)(.*)",
        t,
        flags=re.I,
    )
    if not split:
        return None
    title = _clean_task_title(split.group(1))
    rest = split.group(2).strip(" 。、")
    if not title:
        return None
    detail_html = _task_detail_html_from_instruction(rest)
    return {"title": title, "detail_html": detail_html}


def _clean_task_title(text: str) -> str:
    title = _normalize_text(text)
    title = re.sub(r"^(?:タスク|やること|todo|to-do)(?:に|へ|を)?", "", title, flags=re.I)
    title = re.sub(r"(?:という|といいう|と言う)$", "", title).strip()
    title = title.strip(" 「」『』\"'。 、,")
    return title[:120]


def _task_detail_html_from_instruction(text: str) -> str:
    c = _normalize_text(text).strip(" 。、")
    if not c:
        return ""
    said_content = re.search(r"(.+?)という(?:内容|本文|詳細)(?:を)?(?:追加|追記|記入|書いて|入れて)(?:して)?(?:おいて|ください)?$", c)
    if said_content:
        c = said_content.group(1).strip(" 。、")
        return f"<h2>内容</h2><p>{_html_escape_text(c)}</p>" if c else ""
    c = re.sub(r"(?:書いて|書くいて|記入して|入れて|追記して|追加して)(?:おいて|ください)?$", "", c).strip(" 。、")
    c = re.sub(r"(?:という)?(?:内容|本文|詳細|メモ)(?:を)?$", "", c).strip(" 。、")
    c = re.sub(r"(?:を|に|へ)$", "", c).strip(" 。、")
    if not c:
        return ""
    label = "詳細"
    for pat, candidate in (
        (r"^案(?:として|は|を|:|：)?\s*(.+)", "案"),
        (r"^内容(?:は|を|:|：)?\s*(.+)", "内容"),
        (r"^詳細(?:に|へ|は|を|:|：)?\s*(.+)", "詳細"),
        (r"^メモ(?:に|へ|は|を|:|：)?\s*(.+)", "メモ"),
        (r"^注意点(?:として|は|を|:|：)?\s*(.+)", "注意点"),
        (r"^持っていくもの(?:として|は|を|:|：)?\s*(.+)", "持っていくもの"),
    ):
        m = re.search(pat, c)
        if m:
            label = candidate
            c = m.group(1).strip(" 。、")
            break
    items = [x.strip(" 。、") for x in re.split(r"[;\n]+|(?:、\s*(?=[^、]{2,30}(?:する|を書く|を確認|を作る|を入れる)))", c) if x.strip(" 。、")]
    if len(items) >= 2:
        return "<h2>" + _html_escape_text(label) + "</h2><ul>" + "".join(f"<li>{_html_escape_text(item)}</li>" for item in items[:12]) + "</ul>"
    return f"<h2>{_html_escape_text(label)}</h2><p>{_html_escape_text(c)}</p>"


def _html_escape_text(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
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
        parsed_task = _parse_task_add_request(t)
        if parsed_task:
            args = {"title": parsed_task["title"]}
            if parsed_task.get("detail_html"):
                args["detail_html"] = parsed_task["detail_html"]
            return f"「{parsed_task['title']}」を追加します。", {"name": "add_task", "arguments": args}
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
        if "set_canvas_size" in names and any(w in t for w in ("画像サイズ", "キャンバスサイズ", "サイズ")):
            m = re.search(r"(\d{2,4})\s*[x×＊*]\s*(\d{2,4})", t)
            if not m:
                m = re.search(r"(?:横|幅|width)\s*(\d{2,4}).*?(?:縦|高さ|height)\s*(\d{2,4})", t, re.I)
            if m:
                width = max(160, min(4000, int(m.group(1))))
                height = max(120, min(4000, int(m.group(2))))
                return f"画像サイズを{width}x{height}pxに変更します。", {
                    "name": "set_canvas_size",
                    "arguments": {"width": width, "height": height},
                }
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
        if feature in {"task", "task_manager"}:
            task_override = _task_command_override(command, original_text)
            if task_override:
                return task_override
        return _generic_command_override(command, original_text, manifest)
    name = command.get("name")
    if name != "delete_event" and _schedule_delete_intent(original_text):
        return _default_app_command(feature, original_text, manifest) or (
            "削除したい予定の日付やタイトルを教えてください。",
            {"name": "", "arguments": {}},
        )
    return _generic_command_override(command, original_text, manifest)


def _task_command_override(command: dict, original_text: str) -> tuple[str, dict] | None:
    if not isinstance(command, dict) or command.get("name") != "add_task":
        return None
    args = command.get("arguments") or {}
    if not isinstance(args, dict):
        return None
    parsed = _parse_task_add_request(original_text)
    if not parsed:
        return None
    raw_title = _normalize_text(str(args.get("title") or ""))
    if (
        not raw_title
        or len(raw_title) > max(30, len(parsed["title"]) + 12)
        or any(w in raw_title for w in ("追加して", "入れておいて", "書いておいて", "案として", "詳細に", "メモに", "本文に"))
    ):
        next_args = {"title": parsed["title"]}
        if parsed.get("detail_html"):
            next_args["detail_html"] = parsed["detail_html"]
        return f"「{parsed['title']}」を追加します。", {"name": "add_task", "arguments": next_args}
    if parsed.get("detail_html") and not args.get("detail_html"):
        next_args = dict(args)
        next_args["title"] = parsed["title"]
        next_args["detail_html"] = parsed["detail_html"]
        return f"「{parsed['title']}」を追加し、詳細も記入します。", {"name": "add_task", "arguments": next_args}
    return None


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
        r"(?:予定|スケジュール)に\s*(.+?)\s*を(?:入れて|いれて|追加して|登録して)",
        r"[、,]\s*(.+?)\s*という予定",
        r"[、,]\s*(.+?)\s*を(?:予定|スケジュール)?(?:に)?(?:入れて|いれて|追加して|登録して)",
        r"に\s*(.+?)\s*という予定",
        r"に\s*(.+?)\s*を(?:入れて|いれて|追加して|登録して)",
    ):
        m = re.search(pat, text)
        if m:
            title = _clean_schedule_title(_strip_date_time(m.group(1)))
            if title:
                return title
    title = _clean_schedule_title(_strip_date_time(text))
    title = re.sub(r"(予定|スケジュール)?(を)?(入れて|いれて|追加して|登録して|作って)$", "", title).strip()
    return _clean_schedule_title(title)


def _clean_schedule_title(title: str) -> str:
    out = _normalize_text(title)
    out = re.sub(r"^(?:も|にも|へも|にも\s*)+", "", out).strip()
    out = re.sub(r"(?:の)?(?:予定|スケジュール)$", "", out).strip()
    out = re.sub(r"\s+", " ", out)
    return out.strip(" 。、")


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
    context_id: str | None = None,
    context_label: str | None = None,
    user_uid: str | None = None,
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
        interpretation = _interpret_app_request(
            feature,
            title,
            text,
            history,
            manifest,
            context_id=context_id,
            context_label=context_label,
            user_call_name=user_call_name,
            images=images,
        )
        operation_text = str(interpretation.get("normalized_request") or text)
        if feature == "schedule":
            structured_result = _apply_structured_schedule_plan(
                project_id,
                feature,
                interpretation,
                text,
            )
            if structured_result is not None:
                return structured_result
        state_result = None
        state_attempted = False
        if llm.enabled and _can_direct_state_edit(manifest):
            state_attempted = True
            state_result = _respond_state_content(
                project_id, feature, operation_text, history, manifest, original_text=text, images=images, user_call_name=user_call_name,
                context_id=context_id, context_label=context_label, user_uid=user_uid,
            )
            if state_result is not None:
                return state_result
        deterministic_text = text if feature == "schedule" else operation_text
        deterministic_state = _default_state_update(
            project_id,
            feature,
            deterministic_text,
            manifest,
            context_id=context_id,
            context_label=context_label,
        )
        if deterministic_state is not None:
            return deterministic_state
        if not state_attempted:
            state_result = _respond_state_content(
                project_id, feature, operation_text, history, manifest, original_text=text, images=images, user_call_name=user_call_name,
                context_id=context_id, context_label=context_label, user_uid=user_uid,
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
        runtime_context = _app_runtime_context(project_id, feature, user_uid)
        search_context = _web_search_context(text + "\n" + operation_text)
        if llm.enabled:
            prompt = (
                f"{base}\n\n"
                f"{_user_context_instruction(user_call_name)}\n\n"
                f"対象ミニアプリ: {title}（slug: {feature}）。あなたは専門ワーカーとして、宣言されたツールだけでこのアプリの中身を操作します。\n"
                f"今日の日付（Asia/Tokyo）: {_today_context()}\n"
                f"現在のアプリ画面/作業文脈: id={context_id or 'default'}, label={context_label or context_id or 'default'}\n"
                f"利用可能ツール(MCP形式 name/description/inputSchema): {json.dumps(tools, ensure_ascii=False)}\n"
                f"{_app_worker_operation_manual(feature, title, tools, manifest, runtime_context)}\n"
                f"{search_context}"
                f"直近の会話: {json.dumps(history[-6:], ensure_ascii=False)}\n"
                + ("【添付画像あり】画像内のテキストも読み取って指示の対象にすること。\n" if images else "")
                + f"ユーザーの元の指示: {text}\n"
                + f"解釈済みの作業指示: {operation_text}\n\n"
                "判定して JSON のみで出力:\n"
                '{"category":"content|structure|chat","reply":"<日本語の短い返答>",'
                '"command":{"name":"<toolsのname>","arguments":{<inputSchemaに沿った引数>}}}\n\n'
                "判断ルール:\n"
                "0. まずユーザーの依頼を意味単位に分解し、暗黙の対象・目的・本文を補って、操作しやすい構造へ言い換える。"
                "そのうえで意図を classify する: add/create, update/change, delete/remove, toggle, clear/reset, query/chat, structure。"
                "固定文言への一致判定だけで処理せず、利用可能APIから最も近いものを選ぶ。\n"
                "1. ユーザーの指示が利用可能ツールのどれかで意味的に実行できるなら、必ず category=content にする。"
                "ツール名や引数名をユーザーが正確に言っていなくても、意味から最も近いツールを選ぶ。\n"
                "2. 日付・時刻・数量・タイトル・本文などは、inputSchema に合う形へ正規化する。"
                "例:『6月22日の12:00』→ date='YYYY-06-22', time='12:00'。年が無ければ今日の日付の年を使う。\n"
                "3. 存在しない時刻や不自然な値は勝手に登録しない。例:『15:65』は"
                " category=chat とし、『16:05 の意味でよろしいですか？』のように確認する。\n"
                "4. 削除語があるのに追加APIを選ぶ、追加語があるのに削除APIを選ぶ等、意図とAPIが矛盾する出力は禁止。\n"
                "5. 翻訳・要約・抽出・本文/メモ/詳細更新など、ツールの引数に生成テキストが必要な場合は、"
                "そのまま転記せず、ラベル・箇条書き・短い見出しで整理した本文を arguments に入れる。\n"
                "6. UI/項目/新ボタン追加など、アプリそのものの構造変更は category=structure。\n"
                "7. 純粋な質問・相談・原因調査・接続失敗の診断・一般仕様/設計相談で操作しない場合は category=chat。"
                "明示的に『直して』『修正して』『実装して』と言われていない調査依頼を category=structure にしない。\n"
                "8. category=chat の reply は、分からない点を1つずつ具体的に聞く。"
                "例:『何日の予定ですか？』『どの予定のメモを変更しますか？』"
            )
            data = _safe_json(
                llm,
                prompt,
                images=images,
                tier=_specialist_model_tier(text + "\n" + operation_text, has_images=bool(images)),
            )
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
    data = _safe_json(
        llm,
        prompt,
        images=images,
        tier=_specialist_model_tier(text, has_images=bool(images)),
    )
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


def _safe_json(
    llm,
    prompt: str,
    images: list | None = None,
    tier: ModelTier = ModelTier.FLASH,
) -> dict:
    """Run the LLM and parse its JSON, tolerating a ```json fence. {} on failure.
    `images` (attachments) are passed for vision (e.g. translating text in a photo)."""
    try:
        raw = llm.generate(prompt, tier=tier, images=images or None).strip()
        if raw.startswith("```"):
            raw = raw.strip("`").split("\n", 1)[-1]
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return {}
