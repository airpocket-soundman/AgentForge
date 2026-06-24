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

from app.audit_context import get_audit_context
from app.firestore import get_db
from app.models.orchestrator import WorkPlan


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit(action: str, target: str, detail: dict | None = None, project_id: str | None = None) -> None:
    log_id = f"log_{uuid.uuid4().hex[:12]}"
    ctx = get_audit_context()
    actor = ctx.get("actor")
    request = ctx.get("request")
    get_db().collection("audit_logs").document(log_id).set(
        {
            "log_id": log_id,
            "action": action,
            "target": target,
            "project_id": project_id,  # for the user-facing change history (filterable)
            "detail": detail or {},
            "actor": actor or {"kind": "system", "email": None, "uid": None},
            "actor_email": (actor or {}).get("email"),
            "actor_uid": (actor or {}).get("uid"),
            "source": request or {},
            "request_id": (request or {}).get("request_id"),
            "source_method": (request or {}).get("method"),
            "source_path": (request or {}).get("path"),
            "created_at": _now_iso(),
        }
    )


# --- Mini-app version snapshots (for 巻き戻し) -------------------------------
# A linear stack of published states per feature (no branching). The live state
# is the top of the stack; rollback pops it and restores the previous version.

def _versions_ref(project_id: str, feature: str):
    return get_db().collection("feature_versions").document(f"{project_id}_{feature}")


def snapshot_version(project_id: str, feature: str, manifest: dict, action: str) -> int:
    """Push the just-published manifest onto the feature's version stack."""
    ref = _versions_ref(project_id, feature)
    snap = ref.get()
    versions = (snap.to_dict() or {}).get("versions", []) if snap.exists else []
    seq = (versions[-1]["seq"] + 1) if versions else 1
    versions.append({"seq": seq, "manifest": manifest, "action": action, "created_at": _now_iso()})
    ref.set({"project_id": project_id, "feature": feature, "versions": versions}, merge=True)
    return seq


def list_versions(project_id: str, feature: str) -> list[dict]:
    snap = _versions_ref(project_id, feature).get()
    return (snap.to_dict() or {}).get("versions", []) if snap.exists else []


def pop_version(project_id: str, feature: str) -> None:
    """Remove the top (current) version after a rollback."""
    ref = _versions_ref(project_id, feature)
    snap = ref.get()
    versions = (snap.to_dict() or {}).get("versions", []) if snap.exists else []
    if versions:
        versions.pop()
        ref.set({"versions": versions}, merge=True)


def set_last_changed(project_id: str, feature: str) -> None:
    """Track the most recently created/edited feature (target of bare 「戻して」)."""
    get_db().collection("feature_states").document(project_id).set(
        {"last_changed_feature": feature, "updated_at": _now_iso()}, merge=True
    )


def get_last_changed(project_id: str) -> str | None:
    snap = get_db().collection("feature_states").document(project_id).get()
    return (snap.to_dict() or {}).get("last_changed_feature") if snap.exists else None


# --- Requirements ledger (per feature) ----------------------------------------
# Explicit user requirements only live inside the current HTML once published; a
# later regeneration can silently drop them. The ledger accumulates each
# published request (goal / acceptance items) so edit prompts can pin them.

def _requirements_ref(project_id: str, feature: str):
    return get_db().collection("feature_requirements").document(f"{project_id}_{feature}")


def append_requirements(project_id: str, feature: str, items: list[str]) -> None:
    clean = [str(x).strip()[:200] for x in items if str(x).strip()]
    if not clean:
        return
    ref = _requirements_ref(project_id, feature)
    snap = ref.get()
    cur = (snap.to_dict() or {}).get("items", []) if snap.exists else []
    for c in clean:
        if c not in cur:
            cur.append(c)
    ref.set({"project_id": project_id, "feature": feature,
             "items": cur[-30:], "updated_at": _now_iso()}, merge=True)


def get_requirements(project_id: str, feature: str) -> list[str]:
    snap = _requirements_ref(project_id, feature).get()
    return (snap.to_dict() or {}).get("items", []) if snap.exists else []


def list_history(project_id: str, limit: int = 100) -> list[dict]:
    """User-facing change history: audit log entries for a project, newest first."""
    out: list[dict] = []
    for d in get_db().collection("audit_logs").stream():
        x = d.to_dict() or {}
        target = str(x.get("target") or "")
        if x.get("project_id") == project_id or target.startswith(f"{project_id}:") or target.startswith(f"{project_id}_"):
            out.append(x)
    out.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return out[:limit]


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


def register_generated_view(project_id: str, manifest) -> None:
    """Store the UI Designer worker's REAL view_manifest (pending) for a generated
    feature, so the Generated View Renderer can draw it after approval."""
    get_db().collection("generated_views").document(f"{project_id}_{manifest.feature}").set(
        {
            **manifest.model_dump(mode="json"),
            "project_id": project_id,
            "status": "pending",
            "created_at": _now_iso(),
        }
    )
    _audit("generated_view.pending", manifest.feature, {"title": manifest.title})


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


# Collections wiped by the dev "reset to initial state" action.
_RESET_COLLECTIONS = [
    "conversations",
    "task_runs",
    "work_plans",
    "api_registry",
    "ui_view_registry",
    "approval_requests",
    "audit_logs",
    "app_tasks",
    "feature_states",
    "generated_views",
    "feature_versions",
    "feature_requirements",
    "workers",
    "worker_messages",
    "pipeline_runs",
    "safety_checks",
    "app_entities",
    "app_state",
    "feature_chats",
]


def _wipe(collection: str) -> int:
    db = get_db()
    count = 0
    while True:
        docs = list(db.collection(collection).limit(400).stream())
        if not docs:
            break
        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
        batch.commit()
        count += len(docs)
        if len(docs) < 400:
            break
    return count


def reset_all() -> dict:
    """DEV ONLY: delete all app data and return to the initial (main-chat-only) state."""
    deleted = {c: _wipe(c) for c in _RESET_COLLECTIONS}
    _audit("system.reset", "all", {"deleted": deleted})  # one fresh trace entry
    return {"status": "reset", "deleted": deleted}


def register_plan(plan: WorkPlan) -> str:
    """Atomically-ish register a full plan as pending. Returns the approval_id."""
    save_work_plan(plan)
    create_task_run(plan, current_step="planned", progress_message="作業計画を作成し、生成物を pending 登録しました")
    register_pending_apis(plan)
    register_pending_views(plan)
    return create_approval_request(plan)
