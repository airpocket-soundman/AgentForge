"""Control Plane — the registries that govern what exists and its lifecycle.

Per the design specs, agents never mutate live services directly; they *register
intent* here (status=pending) and a human approves promotion to active. This
module is the Firestore-backed write surface for that.

Collections (subset implemented for Phase 2):
- task_runs/{task_id}           : run status the browser subscribes to live
- work_plans/{task_id}          : the Orchestrator's plan
- api_registry/{api_id}         : generated APIs (pending -> active)
- ui_view_registry/{view_id}    : generated views (pending -> active)
- approval_requests/{approval_id}: human approval gates
- audit_logs/{log_id}           : append-only record of every control action
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.firestore import get_db
from app.models.orchestrator import WorkPlan


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit(action: str, target: str, detail: dict | None = None) -> None:
    log_id = f"log_{uuid.uuid4().hex[:12]}"
    get_db().collection("audit_logs").document(log_id).set(
        {
            "log_id": log_id,
            "action": action,
            "target": target,
            "detail": detail or {},
            "actor": "orchestrator",  # SA-scoped actor; refined in Phase 5
            "created_at": _now_iso(),
        }
    )


def create_task_run(plan: WorkPlan, current_step: str, progress_message: str) -> None:
    get_db().collection("task_runs").document(plan.task_id).set(
        {
            "task_id": plan.task_id,
            "project_id": plan.project_id,
            "status": "planned",
            "current_step": current_step,
            "progress_message": progress_message,
            "goal": plan.goal,
            "feature": plan.feature,
            "approval_required": plan.approval_required_before_active,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
    )
    _audit("task_run.created", plan.task_id, {"feature": plan.feature})


def save_work_plan(plan: WorkPlan) -> None:
    get_db().collection("work_plans").document(plan.task_id).set(plan.model_dump(mode="json"))
    _audit("work_plan.saved", plan.task_id, {"steps": len(plan.plan)})


def register_pending_apis(plan: WorkPlan) -> None:
    batch = get_db().batch()
    col = get_db().collection("api_registry")
    for api in plan.planned_apis:
        ref = col.document(api.api_id)
        batch.set(
            ref,
            {
                **api.model_dump(mode="json"),
                "status": "pending",  # promoted to active only after approval
                "created_by_task": plan.task_id,
                "created_at": _now_iso(),
            },
        )
    batch.commit()
    for api in plan.planned_apis:
        _audit("api_registry.pending", api.api_id, {"path": api.path, "method": api.method})


def register_pending_views(plan: WorkPlan) -> None:
    col = get_db().collection("ui_view_registry")
    for view in plan.planned_views:
        col.document(view.view_id).set(
            {
                **view.model_dump(mode="json"),
                "status": "pending",
                "created_by_task": plan.task_id,
                "created_at": _now_iso(),
            }
        )
        _audit("ui_view_registry.pending", view.view_id, {"route": view.route})


def create_approval_request(plan: WorkPlan) -> str:
    approval_id = f"appr_{uuid.uuid4().hex[:12]}"
    get_db().collection("approval_requests").document(approval_id).set(
        {
            "approval_id": approval_id,
            "task_id": plan.task_id,
            "project_id": plan.project_id,
            "kind": "promote_to_active",
            "status": "pending_user_approval",
            "summary": f"「{plan.goal}」の生成物を有効化してよいか",
            "target_apis": [a.api_id for a in plan.planned_apis],
            "target_views": [v.view_id for v in plan.planned_views],
            "created_at": _now_iso(),
        }
    )
    _audit("approval_request.created", approval_id, {"task_id": plan.task_id})
    return approval_id


def register_plan(plan: WorkPlan) -> str:
    """Atomically-ish register a full plan as pending. Returns the approval_id."""
    save_work_plan(plan)
    create_task_run(plan, current_step="planned", progress_message="作業計画を作成し、生成物を pending 登録しました")
    register_pending_apis(plan)
    register_pending_views(plan)
    return create_approval_request(plan)
