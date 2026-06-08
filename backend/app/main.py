"""AgentForge core API — Cloud Run entrypoint.

Modular monolith: reception / orchestrator / control-plane / tool-gateway are
separate packages mounted onto one FastAPI app (one Cloud Run service), per
IMPLEMENTATION_GUIDE.md §2. Later phases add more routers here.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.orchestrator.router import router as orchestrator_router
from app.reception.router import router as reception_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AgentForge Core API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # NOTE: Cloud Run's Google Front End intercepts "/healthz", so health lives at
    # "/health" (see memory cloud-run-reserved-healthz / HANDOFF.md §4).
    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "agentforge-core-api"}

    @app.get("/")
    def root() -> dict:
        return {"message": "AgentForge core API is running."}

    app.include_router(reception_router)
    app.include_router(orchestrator_router)
    return app


app = create_app()
