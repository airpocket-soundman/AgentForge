"""Orchestrator HTTP surface.

POST /api/orchestrator/plan generates a work plan and registers it (pending) in
the Control Plane. In Phase 3 this becomes a Cloud Tasks-triggered async worker;
for the MVP it runs synchronously.
"""
from fastapi import APIRouter

from app.models.orchestrator import PlanRequest, PlanResponse
from app.orchestrator import service

router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator"])


@router.get("/health")
def orchestrator_health() -> dict:
    return {"status": "ok", "module": "orchestrator"}


@router.post("/plan", response_model=PlanResponse)
def create_plan(body: PlanRequest) -> PlanResponse:
    return service.plan_and_register(body)
