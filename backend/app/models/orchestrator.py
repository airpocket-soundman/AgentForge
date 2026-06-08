"""Models for the Orchestrator's work plan and the artifacts it proposes.

Schema follows the design specs (self_evolving_super_app_spec.md orchestrator
output + agentforge_contest_submission_spec_audited.md api/ui registry shapes).
"""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

SideEffectLevel = Literal["read", "low", "medium", "high"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PlanStep(BaseModel):
    step: int
    worker: str  # ui_designer | api_designer | programmer | test_agent | devops_agent
    instruction: str


class PlannedApi(BaseModel):
    """A deterministic CRUD API the plan intends to create (registered pending)."""

    api_id: str
    path: str
    method: Literal["GET", "POST", "PATCH", "PUT", "DELETE"]
    side_effect_level: SideEffectLevel = "low"
    owner_layer: str = "generated_app"


class PlannedView(BaseModel):
    """A dynamic UI view (view_manifest) the plan intends to create."""

    view_id: str
    route: str
    title: str
    required_apis: list[str] = Field(default_factory=list)


class WorkPlan(BaseModel):
    task_id: str
    project_id: str
    goal: str
    feature: str  # task | pdf_memo | unknown
    plan: list[PlanStep]
    planned_apis: list[PlannedApi] = Field(default_factory=list)
    planned_views: list[PlannedView] = Field(default_factory=list)
    rollback_required: bool = True
    approval_required_before_active: bool = True
    generated_by: Literal["gemini", "stub"] = "stub"
    created_at: datetime = Field(default_factory=_now)


class PlanRequest(BaseModel):
    project_id: str = "default"
    goal: str = Field(min_length=1, max_length=2000)
    feature: str | None = None  # if None, inferred from the goal text


class PlanResponse(BaseModel):
    task_id: str
    approval_id: str
    plan: WorkPlan
    summary: str
