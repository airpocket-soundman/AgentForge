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
        if manifest.kind == "app":
            return (
                f"🤖「{manifest.title}」を作ります（実コード生成: {manifest.generated_by}）。\n"
                f"{desc}"
                f"・AIが実際に動く HTML/JS/CSS を書きました（サンドボックスで安全に実行）。\n"
                f"よければ「反映して」と承認してください。左メニューに追加されて使えます。"
            )
        cols = "、".join(f.label for f in manifest.fields) or "なし"
        present = [
            name
            for name, ok in [
                ("KPI集計", manifest.stats),
                ("グラフ", manifest.charts),
                ("ガント", manifest.gantt),
                ("カレンダー", manifest.calendar),
            ]
            if ok
        ]
        extra = f"・ビュー: {('、'.join(present))}\n" if present else ""
        return (
            f"🤖「{manifest.title}」を作ります（設計: {manifest.generated_by}）。\n"
            f"{desc}"
            f"・入力項目: {cols}\n"
            f"{extra}"
            f"・入力したデータは保存され、一覧で見られます。\n"
            f"よければ「反映して」と承認してください。左メニューに追加されて実際に使えます。"
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


def plan_and_register(req: PlanRequest) -> PlanResponse:
    """Generate a plan and register it (pending) in the Control Plane.

    For the built-in `task` feature we keep the polished hard-coded screen. For ANY
    other request the UI Designer worker actually runs and designs a real view_manifest
    that the Generated View Renderer draws (true self-expansion)."""
    plan = generate_plan(req)
    # EVERY feature is really generated by the UI Designer worker — including task
    # management. No hard-coded screens; the design varies with the instruction.
    from app.workers import ui_designer

    manifest = ui_designer.design(req.goal)
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
