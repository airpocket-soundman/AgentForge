"""MCP-like inter-worker protocol (NOT the real Model Context Protocol).

A small, schema-validated request/report contract so workers exchange "instruction"
and "report" in a fixed shape (workers.html §7 "ワーカー間プロトコル（MCP 的 API）").
The shape is inspired by MCP-style tool messaging, hence "MCP-like" — it is our own
internal contract, not an MCP implementation.

Correlation: a report references the request via in_reply_to (= request.message_id)
and shares task_id. Schema validation is the gate — a request that fails validation
is rejected (never acted on).
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Intent = Literal["plan", "build", "edit", "verify", "review", "operate"]
ReportStatus = Literal["ok", "needs_revision", "rejected", "failed", "in_progress"]


class WorkerRequest(BaseModel):
    """An instruction from one worker to another."""

    model_config = ConfigDict(populate_by_name=True)

    task_id: str
    message_id: str
    sender: str = Field(alias="from")  # 'from' is reserved in Python
    to: str
    intent: Intent
    payload: dict[str, Any] = Field(default_factory=dict)
    context_refs: list[str] = Field(default_factory=list)  # minimal pointers; body in Firestore
    deadline_sec: int | None = None  # hint for the Receptor's stall judgment, not an auto-kill


class WorkerReport(BaseModel):
    """A report back to the requester."""

    model_config = ConfigDict(populate_by_name=True)

    task_id: str
    in_reply_to: str  # the request.message_id this answers
    sender: str = Field(alias="from")
    to: str
    status: ReportStatus
    result: dict[str, Any] | None = None
    findings: list[str] = Field(default_factory=list)  # Reviewer/Tester notes (needs_revision)
    error: str | None = None  # reason for rejected / failed
    usage: dict[str, Any] | None = None  # model/tokens for the audit (worker_runs)
