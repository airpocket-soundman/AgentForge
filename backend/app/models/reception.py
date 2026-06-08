"""Pydantic models for the Reception module (Phase 1).

Field names mirror the Firestore schema in the design specs
(see agentforge_contest_submission_spec_audited.md and the control-plane spec).
"""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MessageIn(BaseModel):
    """A message sent by the user from the Web Shell chat."""

    project_id: str = Field(default="default", description="Project scope for the conversation")
    text: str = Field(min_length=1, max_length=4000)


class ChatMessage(BaseModel):
    """One stored chat message (user or assistant)."""

    role: Literal["user", "assistant", "system"]
    text: str
    created_at: datetime = Field(default_factory=_now)


class ReceptionReply(BaseModel):
    """The Reception agent's immediate response to the browser."""

    conversation_id: str
    reply: ChatMessage
    # Set when Reception recognises an app-building intent and hands it to the
    # Orchestrator. task_id/approval_id are present once a plan is registered.
    detected_intent: str | None = None
    task_id: str | None = None
    approval_id: str | None = None
