"""Generated Task feature — the deterministic CRUD skeleton (no LLM).

Gated by the Control Plane: every route requires the 'task' feature to be active
for the project (i.e. the user approved it). Before approval the same endpoints
return 409 — this is what makes the approval step meaningful in the demo.

Tasks are stored in Firestore `app_tasks/{task_id}`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.control_plane.approvals import require_feature_active
from app.firestore import get_db
from app.models.tasks import Task, TaskIn, TaskUpdate

router = APIRouter(prefix="/api/app/tasks", tags=["generated-app:task"])

_COLLECTION = "app_tasks"
_FEATURE = "task"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("")
def list_tasks(project_id: str = "default") -> dict:
    require_feature_active(project_id, _FEATURE)
    docs = get_db().collection(_COLLECTION).where("project_id", "==", project_id).stream()
    tasks = [d.to_dict() for d in docs]
    tasks.sort(key=lambda t: t.get("created_at", ""))
    return {"tasks": tasks}


@router.post("")
def create_task(body: TaskIn) -> Task:
    require_feature_active(body.project_id, _FEATURE)
    task_id = f"t_{uuid.uuid4().hex[:12]}"
    task = Task(task_id=task_id, project_id=body.project_id, title=body.title, due_date=body.due_date)
    get_db().collection(_COLLECTION).document(task_id).set(task.model_dump(mode="json"))
    return task


@router.patch("/{task_id}")
def update_task(task_id: str, body: TaskUpdate) -> Task:
    ref = get_db().collection(_COLLECTION).document(task_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="task が見つかりません")
    current = snap.to_dict()
    require_feature_active(current["project_id"], _FEATURE)

    patch = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    patch["updated_at"] = _now_iso()
    ref.set(patch, merge=True)
    return Task(**{**current, **patch})
