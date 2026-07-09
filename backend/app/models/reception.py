"""Pydantic models for the Reception module (Phase 1).

Field names mirror the Firestore schema in the design specs
(see agentforge_contest_submission_spec_audited.md and the control-plane spec).
"""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Attachment(BaseModel):
    """A file/image attached to a chat message.

    - kind="text": `content` is the decoded file text (CSV/JSON/code/…) — inlined
      into the request so the AI reads it.
    - kind="image": `content` is base64 (no data: prefix) — passed to the LLM for
      vision (e.g. "build a tool like this screenshot").
    """

    name: str = ""
    mime: str = ""
    kind: Literal["image", "text"] = "text"
    content: str = ""


class MessageIn(BaseModel):
    """A message sent by the user from the Web Shell chat."""

    project_id: str = Field(default="default", description="Project scope for the conversation")
    text: str = Field(min_length=1, max_length=4000)
    attachments: list[Attachment] = Field(default_factory=list)
    user_call_name: str | None = Field(default=None, max_length=80)
    context_id: str = Field(default="default", max_length=80)


class ChatMessage(BaseModel):
    """One stored chat message (user or assistant)."""

    role: Literal["user", "assistant", "system"]
    text: str
    # Optional inline SVG image (e.g., the plan-stage screen mock) — the frontend
    # renders it as an <img> data URI, so scripts can never execute.
    svg: str | None = None
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
    # Set when a conversational command changed feature state, so the UI can react.
    activated_feature: str | None = None
    disabled_feature: str | None = None
    deleted_feature: str | None = None
    deleted_features: list[str] = Field(default_factory=list)
    # True when a background design was kicked off; the browser then polls /state.
    building: bool = False
