"""Orchestrator — turns an ambiguous NL request into a structured work plan.

This is the "AIエージェントの必然性" showcase (審査基準1): deciding *what* to build,
*how* to decompose it, and *which* workers to assign is non-deterministic judgement,
so it routes to Gemini Pro. When no API key is reachable (local dev / CI), it falls
back to deterministic feature templates so the whole pipeline stays exercisable.
"""
from __future__ import annotations

import json
import uuid

from app.control_plane import registry
from app.firestore import get_db
from app.llm.gateway import ModelTier, get_llm
from app.models.orchestrator import (
    PlannedApi,
    PlannedView,
    PlanRequest,
    PlanResponse,
    PlanStep,
    WorkPlan,
)

_FEATURE_KEYWORDS = {
    "task": ("タスク", "todo", "task"),
    "pdf_memo": ("pdf", "メモ", "memo", "要約"),
}


def infer_feature(goal: str) -> str:
    lowered = goal.lower()
    for feature, kws in _FEATURE_KEYWORDS.items():
        if any(k in lowered for k in kws):
            return feature
    return "unknown"


# --- Request routing: new feature vs. edit existing (Orchestrator's call) ----
# The Orchestrator owns the new-vs-edit decision so BOTH the main chat and a
# feature screen feed the SAME pipeline. It only CLASSIFIES — it never rewrites
# the user's text; the original instruction flows verbatim to the generator, and
# any detailing happens additively downstream (plan/design), so intent can be
# enriched along the pipeline but never degraded.

_EDIT_HINT_KEYWORDS = (
    "修正", "直", "なお", "変更", "編集", "改善", "変えて", "調整", "増やして",
    "減らして", "大きく", "小さく", "追加して", "やめて削", "fix", "edit", "change",
)
_BUILD_HINT_KEYWORDS = ("作って", "つくって", "作成", "ほしい", "欲しい", "新しく", "create", "build", "make", "新規")


def active_features(project_id: str) -> dict[str, str]:
    """Active features as {slug: title} (meta keys filtered out)."""
    snap = get_db().collection("feature_states").document(project_id).get()
    states = (snap.to_dict() or {}) if snap.exists else {}
    out: dict[str, str] = {}
    for k, v in states.items():
        if v == "active" and not any(k.endswith(s) for s in ("_worker", "_theme", "_title")) and k != "updated_at":
            out[k] = states.get(f"{k}_title") or k
    return out


def _recent_messages(project_id: str, n: int = 8) -> list[dict]:
    """Recent conversation turns so the Orchestrator can decide WITH context."""
    snap = get_db().collection("conversations").document(f"conv_{project_id}").get()
    data = (snap.to_dict() or {}) if snap.exists else {}
    return (data.get("messages") or [])[-n:]


def _classify_stub(goal: str, actives: dict[str, str], hint_feature: str | None) -> dict:
    text = goal.lower()
    # An explicitly named existing feature → edit it.
    for slug, title in actives.items():
        if (title and title in goal) or slug in text:
            return {"action": "edit", "feature": slug}
    is_edit = any(k in text for k in _EDIT_HINT_KEYWORDS)
    is_build = any(k in text for k in _BUILD_HINT_KEYWORDS)
    if hint_feature and hint_feature in actives and is_edit and not is_build:
        return {"action": "edit", "feature": hint_feature}
    if is_build:
        return {"action": "create", "feature": None}
    if is_edit and len(actives) == 1:
        return {"action": "edit", "feature": next(iter(actives))}
    if is_edit and hint_feature in actives:
        return {"action": "edit", "feature": hint_feature}
    return {"action": "chat", "feature": None}


def classify_request(project_id: str, goal: str, hint_feature: str | None = None) -> dict:
    """Read recent conversation context, then decide what to flow into the pipeline.

    Returns {"action": "create"|"edit"|"chat", "feature": slug|None, "context_note": str}.

    The Orchestrator reads the recent history so it can resolve references (e.g.
    「それをもっと大きく」 → the feature just discussed) and route correctly. It does
    NOT rewrite the user's instruction — `context_note` only CLARIFIES the target /
    premise from history (additive). Callers append it to the verbatim original, so
    intent is enriched along the pipeline but never degraded.

    LLM-driven over the active-feature list + history; deterministic keyword
    fallback when no model is reachable. `hint_feature` (the screen the user is on)
    biases toward editing that feature but never forces it.
    """
    actives = active_features(project_id)
    llm = get_llm()
    if not llm.enabled:
        return {**_classify_stub(goal, actives, hint_feature), "context_note": ""}
    history = _recent_messages(project_id)
    history_text = "\n".join(f"{m.get('role')}: {(m.get('text') or '')[:200]}" for m in history) or "（履歴なし）"
    feature_lines = "\n".join(f"- {slug}: {title}" for slug, title in actives.items()) or "（まだ機能はありません）"
    hint = f"\nユーザーは今「{actives.get(hint_feature, hint_feature)}」の画面にいます。" if hint_feature else ""
    prompt = (
        "あなたはオーケストレーターです。直近の会話を踏まえ、ユーザーの要求が"
        "『新しい機能の作成(create)』『既存機能の改修(edit)』『ただの会話/質問(chat)』の"
        "どれかを判定し、パイプラインに流す正しい指示を整えます。\n"
        f"現在アクティブな機能:\n{feature_lines}{hint}\n\n"
        f"直近の会話:\n{history_text}\n\n"
        f"今回のユーザーの要求（原文）: {goal}\n\n"
        "判定ルール: 既存機能の見た目/動作の変更・追加・修正なら edit（feature にその slug）。"
        "新しい別機能の作成なら create。相談・質問・使い方なら chat。"
        "画面ヒントがあっても新規作成を望む内容なら create を優先。\n"
        "context_note: 履歴から判断した『対象や前提の明確化』だけを書く（例: 指示語が指す機能、"
        "前回の続きである旨）。ユーザーの原文の言い換え・要約・改変は禁止。無ければ空文字。\n"
        'JSONのみで出力: {"action": "create|edit|chat", "feature": "<edit時のslug/空>", "context_note": "<補足/空>"}'
    )
    try:
        raw = llm.generate(prompt, tier=ModelTier.FLASH).strip()
        if raw.startswith("```"):
            raw = raw.strip("`").split("\n", 1)[-1]
        data = json.loads(raw)
        action = data.get("action")
        feature = (data.get("feature") or "").strip() or None
        note = str(data.get("context_note") or "").strip()
        if action not in ("create", "edit", "chat"):
            return {**_classify_stub(goal, actives, hint_feature), "context_note": note}
        if action == "edit" and feature not in actives:
            # Hallucinated/unknown target → fall back rather than edit the wrong thing.
            return {**_classify_stub(goal, actives, hint_feature), "context_note": note}
        return {"action": action, "feature": feature if action == "edit" else None, "context_note": note}
    except Exception:  # noqa: BLE001
        return {**_classify_stub(goal, actives, hint_feature), "context_note": ""}


# --- Deterministic feature templates (stub / fallback) -----------------------

def _task_plan(task_id: str, req: PlanRequest) -> WorkPlan:
    apis = [
        PlannedApi(api_id="task_list_api", path="/api/app/tasks", method="GET", side_effect_level="read"),
        PlannedApi(api_id="task_create_api", path="/api/app/tasks", method="POST", side_effect_level="low"),
        PlannedApi(api_id="task_update_api", path="/api/app/tasks/{task_id}", method="PATCH", side_effect_level="low"),
    ]
    view = PlannedView(
        view_id="task_list_view",
        route="/app/tasks",
        title="タスク",
        required_apis=[a.api_id for a in apis],
    )
    steps = [
        PlanStep(step=1, worker="ui_designer", instruction="タスク一覧・追加フォーム・完了切替のUIを設計する"),
        PlanStep(step=2, worker="api_designer", instruction="Task API（一覧/追加/更新）とデータ構造を設計する"),
        PlanStep(step=3, worker="programmer", instruction="API と view_manifest を実装する"),
        PlanStep(step=4, worker="test_agent", instruction="テストを生成・実行する"),
        PlanStep(step=5, worker="devops_agent", instruction="Cloud Run preview へのデプロイ計画を作成する"),
    ]
    return WorkPlan(
        task_id=task_id, project_id=req.project_id, goal="タスク管理機能を追加する",
        feature="task", plan=steps, planned_apis=apis, planned_views=[view],
    )


def _pdf_memo_plan(task_id: str, req: PlanRequest) -> WorkPlan:
    apis = [
        PlannedApi(api_id="memo_list_api", path="/api/app/memos", method="GET", side_effect_level="read"),
        PlannedApi(api_id="memo_create_api", path="/api/app/memos", method="POST", side_effect_level="low"),
        PlannedApi(api_id="pdf_summarize_api", path="/api/app/memos/summarize", method="POST", side_effect_level="medium"),
    ]
    view = PlannedView(
        view_id="memo_view", route="/app/memos", title="PDFメモ",
        required_apis=[a.api_id for a in apis],
    )
    steps = [
        PlanStep(step=1, worker="ui_designer", instruction="PDFアップロード・メモ一覧・要約表示のUIを設計する"),
        PlanStep(step=2, worker="api_designer", instruction="Memo API と要約APIを設計する"),
        PlanStep(step=3, worker="programmer", instruction="API（Gemini要約含む）と view_manifest を実装する"),
        PlanStep(step=4, worker="test_agent", instruction="テストを生成・実行する"),
        PlanStep(step=5, worker="devops_agent", instruction="Cloud Run preview へのデプロイ計画を作成する"),
    ]
    return WorkPlan(
        task_id=task_id, project_id=req.project_id, goal="PDFメモ機能を追加する",
        feature="pdf_memo", plan=steps, planned_apis=apis, planned_views=[view],
    )


def _generic_plan(task_id: str, req: PlanRequest) -> WorkPlan:
    api = PlannedApi(api_id=f"gen_{task_id[5:]}_api", path="/api/app/items", method="GET", side_effect_level="read")
    view = PlannedView(view_id=f"gen_{task_id[5:]}_view", route="/app/generated", title="生成機能", required_apis=[api.api_id])
    steps = [
        PlanStep(step=1, worker="ui_designer", instruction=f"『{req.goal}』に必要な画面を設計する"),
        PlanStep(step=2, worker="programmer", instruction="API と view_manifest を実装する"),
    ]
    return WorkPlan(
        task_id=task_id, project_id=req.project_id, goal=req.goal,
        feature="unknown", plan=steps, planned_apis=[api], planned_views=[view],
    )


def _stub_plan(task_id: str, req: PlanRequest, feature: str) -> WorkPlan:
    if feature == "task":
        return _task_plan(task_id, req)
    if feature == "pdf_memo":
        return _pdf_memo_plan(task_id, req)
    return _generic_plan(task_id, req)


# --- Gemini-generated plan (when a key is reachable) -------------------------

_SCHEMA = """出力スキーマ:
{
  "goal": "<一文の目標>",
  "feature": "task | pdf_memo | unknown",
  "plan": [{"step": 1, "worker": "ui_designer|api_designer|programmer|test_agent|devops_agent", "instruction": "<日本語>"}],
  "planned_apis": [{"api_id": "<snake_case>", "path": "/api/app/...", "method": "GET|POST|PATCH|DELETE", "side_effect_level": "read|low|medium|high"}],
  "planned_views": [{"view_id": "<snake_case>", "route": "/app/...", "title": "<日本語>", "required_apis": ["<api_id>"], "has_worker": true, "theme": "default"}]
}

見た目テーマ: theme は default / warm / forest / ocean から選ぶ。ユーザーの見た目指示が
曖昧なら内容に最も近いものを、指定が無ければ default。生のCSS/HTMLは出力しない。"""


def _build_plan_prompt(goal: str) -> str:
    """Assemble the Orchestrator prompt from repo-managed instruction files."""
    from app import agents

    return "\n\n".join(
        [agents.load("orchestrator"), agents.policy(), f"ユーザー要求: {goal}", _SCHEMA]
    )


def _gemini_plan(task_id: str, req: PlanRequest) -> WorkPlan:
    raw = get_llm().generate(_build_plan_prompt(req.goal), tier=ModelTier.PRO)
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1]  # drop a leading ```json fence
    data = json.loads(text)
    return WorkPlan(
        task_id=task_id,
        project_id=req.project_id,
        goal=data["goal"],
        feature=data.get("feature", infer_feature(req.goal)),
        plan=[PlanStep(**s) for s in data["plan"]],
        planned_apis=[PlannedApi(**a) for a in data.get("planned_apis", [])],
        planned_views=[PlannedView(**v) for v in data.get("planned_views", [])],
        generated_by="gemini",
    )


# --- Public entrypoint -------------------------------------------------------

# If the request explicitly opts out of a managing worker.
_NO_WORKER_KEYWORDS = ("ワーカー不要", "ワーカーなし", "ワーカー無し", "ワーカーいらない", "no worker", "without worker")


def _wants_no_worker(goal: str) -> bool:
    lowered = goal.lower()
    return any(k.lower() in lowered for k in _NO_WORKER_KEYWORDS)


def generate_plan(req: PlanRequest) -> WorkPlan:
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    feature = req.feature or infer_feature(req.goal)
    if get_llm().enabled:
        try:
            plan = _gemini_plan(task_id, req)
        except Exception:  # noqa: BLE001 — any LLM/parse failure -> deterministic plan
            plan = _stub_plan(task_id, req, feature)
    else:
        plan = _stub_plan(task_id, req, feature)

    # Standard spec: feature screens get a managing AI worker unless opted out.
    if _wants_no_worker(req.goal):
        for view in plan.planned_views:
            view.has_worker = False
    return plan


def _summarize(plan: WorkPlan, manifest=None) -> str:
    if manifest is not None:
        desc = f"{manifest.description}\n" if manifest.description else ""
        return (
            f"🤖「{manifest.title}」を作りました（生成: {manifest.generated_by}）。\n"
            f"{desc}"
            f"・ご依頼の内容を、実際に動くアプリとしてAIが実装しました。\n"
            f"よければ「反映して」と承認してください。左メニューに追加されてすぐ使えます。"
        )
    apis = "、".join(a.api_id for a in plan.planned_apis) or "なし"
    views = "、".join(v.view_id for v in plan.planned_views) or "なし"
    return (
        f"「{plan.goal}」の作業計画を作成しました（{plan.generated_by}）。\n"
        f"・ステップ: {len(plan.plan)}（{ '→'.join(s.worker for s in plan.plan) }）\n"
        f"・生成予定API: {apis}\n"
        f"・生成予定画面: {views}\n"
        f"これらを pending 登録しました。「反映して」で承認すると有効化されます。"
    )


def build_app(req: PlanRequest, design_plan: dict | None = None, feedback: str | None = None):
    """Generate the app (the single PRO call). Returns a ViewManifest, unregistered.

    `feedback` (Tester/Reviewer findings) is appended to the goal so a re-build
    fixes the cited issues — the deploy-time gate's revision loop uses this."""
    from app.workers import ui_designer

    goal = req.goal
    if feedback:
        goal = f"{req.goal}\n\n[前回の検証・レビュー指摘（必ず修正すること）]\n{feedback}"
    return ui_designer.design(goal, plan=design_plan)


def register_app(req: PlanRequest, manifest) -> PlanResponse:
    """Register an already-built manifest (pending) in the Control Plane.

    The WorkPlan skeleton is built DETERMINISTICALLY (no LLM): the approved design
    proposal already captured the design; views/feature/theme are taken from the
    generated manifest."""
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    feature = req.feature or infer_feature(req.goal)
    plan = _stub_plan(task_id, req, feature)
    if _wants_no_worker(req.goal):
        for view in plan.planned_views:
            view.has_worker = False
    plan.feature = manifest.feature  # the slug the designer chose
    if plan.planned_views:
        v = plan.planned_views[0]
        v.view_id = f"{manifest.feature}_view"
        v.route = f"/app/{manifest.feature}"
        v.title = manifest.title
        v.theme = manifest.theme  # type: ignore[assignment]

    approval_id = registry.register_plan(plan)
    registry.register_generated_view(req.project_id, manifest)

    return PlanResponse(
        task_id=plan.task_id, approval_id=approval_id, plan=plan, summary=_summarize(plan, manifest)
    )


def plan_and_register(req: PlanRequest, design_plan: dict | None = None) -> PlanResponse:
    """Build + register in one shot (no deploy-time gate). Used by the low-level
    /api/orchestrator/plan endpoint. The chat pipeline (_run_codegen) instead calls
    build_app → Tester/Reviewer gate → register_app so generation is verified."""
    manifest = build_app(req, design_plan)
    return register_app(req, manifest)
