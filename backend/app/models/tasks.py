"""Models for the generated Task feature (the first 'living feature').

Per IMPLEMENTATION_GUIDE.md §2.5: the skeleton is a *deterministic* CRUD API
(no LLM). These are the request/response shapes for that API.
"""
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TaskIn(BaseModel):
    project_id: str = "default"
    title: str = Field(min_length=1, max_length=500)
    due_date: str | None = None  # ISO date string, optional


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    done: bool | None = None
    due_date: str | None = None


class Task(BaseModel):
    task_id: str
    project_id: str
    title: str
    done: bool = False
    due_date: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
