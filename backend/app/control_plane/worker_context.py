"""Per-worker context persistence (spec §9).

Workers are non-resident, so they don't hold context in memory: they save it to
Firestore and rehydrate the minimum on start. To bound growth, old raw entries
are compacted (folded into a maintained summary), mirroring the Specialist
Worker's "organized summary" pattern (generated_app/task_worker.py).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.firestore import get_db

_COLLECTION = "worker_contexts"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ctx_id(worker_type: str, project_id: str) -> str:
    return f"{worker_type}:{project_id}"


def save_context(worker_type: str, project_id: str, data: dict) -> None:
    """Persist (merge) a worker's context."""
    get_db().collection(_COLLECTION).document(_ctx_id(worker_type, project_id)).set(
        {**data, "worker_type": worker_type, "project_id": project_id, "updated_at": _now_iso()},
        merge=True,
    )


def load_context(worker_type: str, project_id: str) -> dict:
    """Rehydrate a worker's context (empty dict if none)."""
    snap = get_db().collection(_COLLECTION).document(_ctx_id(worker_type, project_id)).get()
    return (snap.to_dict() or {}) if snap.exists else {}


def plan_compaction(items: list, keep_recent: int) -> tuple[list, list]:
    """Pure: split a log into (to_fold_into_summary, to_keep_verbatim).

    When the log exceeds `keep_recent`, the older entries are returned for folding
    into the running summary and dropped from the raw log; the most recent
    `keep_recent` are kept verbatim. No-op (nothing to fold) when within budget."""
    if keep_recent < 0:
        keep_recent = 0
    if len(items) <= keep_recent:
        return [], list(items)
    return list(items[:-keep_recent]) if keep_recent else list(items), \
        list(items[-keep_recent:]) if keep_recent else []
