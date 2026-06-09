"""Runaway / loop guard — caps token waste from workers re-running in a loop.

Non-resident workers each cost an LLM call; a misbehaving cycle (auto-retrigger,
repeated regeneration) could burn tokens unbounded. We record every HEAVY worker
start (plan / codegen / edit) per project and refuse once the rolling run-rate
cap is exceeded, so a loop trips the breaker instead of spending more tokens.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.firestore import get_db

_COL = "usage_counters"
_WINDOW_SEC = 600   # rolling window
_MAX_RUNS = 25      # max heavy worker starts per project per window


def _fresh(runs: list[str], now: datetime) -> list[str]:
    out = []
    for ts in runs:
        try:
            t = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        if (now - t).total_seconds() <= _WINDOW_SEC:
            out.append(ts)
    return out


def record_and_check(project_id: str) -> tuple[bool, int]:
    """Record a heavy worker run; return (allowed, runs_in_window).

    allowed=False means the rolling cap is hit (likely a loop) — the caller should
    refuse to start more work. The run is NOT counted when blocked.
    """
    ref = get_db().collection(_COL).document(project_id)
    snap = ref.get()
    data = snap.to_dict() if snap.exists else {}
    now = datetime.now(timezone.utc)
    fresh = _fresh(data.get("runs", []), now)
    if len(fresh) >= _MAX_RUNS:
        ref.set(
            {"runs": fresh, "blocked_at": now.isoformat(), "total_blocked": data.get("total_blocked", 0) + 1},
            merge=True,
        )
        return False, len(fresh)
    fresh.append(now.isoformat())
    ref.set(
        {"runs": fresh, "updated_at": now.isoformat(), "total_runs": data.get("total_runs", 0) + 1},
        merge=True,
    )
    return True, len(fresh)


def usage(project_id: str) -> dict:
    snap = get_db().collection(_COL).document(project_id).get()
    data = snap.to_dict() if snap.exists else {}
    now = datetime.now(timezone.utc)
    return {
        "runs_in_window": len(_fresh(data.get("runs", []), now)),
        "max_runs": _MAX_RUNS,
        "window_sec": _WINDOW_SEC,
        "total_runs": data.get("total_runs", 0),
        "total_blocked": data.get("total_blocked", 0),
    }
