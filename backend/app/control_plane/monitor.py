"""Status monitor — what is actually running right now, and a global stop.

In the non-resident model a "running worker" is a conversation whose build record
is `status=designing` (a background plan/codegen/edit thread). This scans for them
so the UI can show the live worker list, and `stop_all` releases every one (an
admin escape hatch so a stuck/looping run never locks the whole system).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.firestore import get_db

_CONVERSATIONS = "conversations"
# Mirror reception.service phase budgets so health here matches the chat's reply.
_PHASE_BUDGET = {"planning": 40, "revising": 40, "codegen": 130, "editing": 130}
_STUCK_FACTOR = 2.5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _age_sec(iso: str | None) -> float:
    if not iso:
        return 0.0
    try:
        then = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return 0.0
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - then).total_seconds())


def _health(phase: str | None, total: float) -> str:
    budget = _PHASE_BUDGET.get(phase or "planning", 90)
    if total > budget * _STUCK_FACTOR:
        return "stuck"
    if total > budget:
        return "slow"
    return "progressing"


def running_workers() -> list[dict]:
    """All in-flight background workers across sessions (status=designing)."""
    out: list[dict] = []
    for doc in get_db().collection(_CONVERSATIONS).stream():
        data = doc.to_dict() or {}
        build = data.get("build") or {}
        if build.get("status") != "designing":
            continue
        total = int(_age_sec(build.get("started_at") or build.get("updated_at")))
        out.append({
            "conversation_id": doc.id,
            "project_id": doc.id[len("conv_"):] if doc.id.startswith("conv_") else doc.id,
            "phase": build.get("phase"),
            "goal": (build.get("goal") or "")[:80],
            "total_sec": total,
            "health": _health(build.get("phase"), total),
            "model": build.get("model"),
        })
    out.sort(key=lambda w: w["total_sec"], reverse=True)
    return out


def stop_all() -> dict:
    """Stop every running background worker (release all locked chats)."""
    db = get_db()
    stopped: list[str] = []
    for doc in db.collection(_CONVERSATIONS).stream():
        data = doc.to_dict() or {}
        build = data.get("build") or {}
        if build.get("status") == "designing":
            doc.reference.set(
                {"build": {"status": "error", "error": "stopped by user (stop-all)", "updated_at": _now_iso()}},
                merge=True,
            )
            stopped.append(doc.id)
    return {"stopped": len(stopped), "conversations": stopped}
