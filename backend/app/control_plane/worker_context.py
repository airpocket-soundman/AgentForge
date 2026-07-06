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
_SUMMARY_LIMIT = 8000
_MESSAGE_TEXT_LIMIT = 500


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


def _message_line(message: dict) -> str:
    role = str(message.get("role") or "?")
    text = " ".join(str(message.get("text") or "").split())
    if len(text) > _MESSAGE_TEXT_LIMIT:
        text = text[:_MESSAGE_TEXT_LIMIT] + "..."
    created = str(message.get("created_at") or "")[:19]
    prefix = f"{created} " if created else ""
    return f"- {prefix}{role}: {text}"


def compact_message_history(
    current_messages: list[dict],
    new_messages: list[dict],
    *,
    summary: str = "",
    keep_recent: int = 80,
    summary_limit: int = _SUMMARY_LIMIT,
) -> tuple[list[dict], str, bool]:
    """Append messages and compact old raw history into a bounded summary.

    This is intentionally deterministic: compaction must still work when the LLM
    provider is down. The summary is an audit-friendly digest, not a replacement
    for long-term logs.
    """
    combined = list(current_messages or []) + list(new_messages or [])
    to_fold, keep = plan_compaction(combined, keep_recent)
    if not to_fold:
        return combined, summary or "", False

    folded = "\n".join(_message_line(m) for m in to_fold if isinstance(m, dict))
    next_summary = (summary or "").strip()
    if folded:
        block = "[compacted messages]\n" + folded
        next_summary = f"{next_summary}\n\n{block}".strip() if next_summary else block
    if len(next_summary) > summary_limit:
        next_summary = "...(older compacted summary truncated)\n" + next_summary[-summary_limit:]
    return keep, next_summary, True


def summary_message(summary: str) -> dict | None:
    """Synthetic chat message used by UI/API readers before recent messages."""
    if not (summary or "").strip():
        return None
    return {
        "role": "system",
        "text": "以前の会話要約:\n" + summary.strip(),
        "created_at": "",
    }


def append_messages_compacted(
    doc_ref,
    new_payloads: list[dict],
    *,
    keep_recent: int,
    base_fields: dict | None = None,
) -> None:
    """Atomically append messages to a chat document, compacting old history.

    Compaction needs read-modify-write, which would lose concurrent appends (the
    pipeline writes progress from background threads while the user posts), so the
    whole cycle runs inside a Firestore transaction — contention retries instead of
    dropping messages.
    """
    from google.cloud import firestore  # local import keeps module import cheap

    db = get_db()

    @firestore.transactional
    def _txn(transaction) -> None:
        snap = doc_ref.get(transaction=transaction)
        data = (snap.to_dict() or {}) if snap.exists else {}
        messages, summary, compacted = compact_message_history(
            data.get("messages", []),
            new_payloads,
            summary=str(data.get("compacted_summary") or ""),
            keep_recent=keep_recent,
        )
        transaction.set(
            doc_ref,
            {
                **(base_fields or {}),
                "messages": messages,
                "compacted_summary": summary,
                "compacted": compacted or bool(data.get("compacted")),
                "updated_at": _now_iso(),
            },
            merge=True,
        )

    _txn(db.transaction())
