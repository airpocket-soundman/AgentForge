"""AgentForge core API — Cloud Run entrypoint.

Modular monolith: reception / orchestrator / control-plane / tool-gateway are
separate packages mounted onto one FastAPI app (one Cloud Run service), per
IMPLEMENTATION_GUIDE.md §2. Later phases add more routers here.
"""
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.admin.router import router as admin_router
from app import audit_context
from app.auth import require_allowed_user
from app.config import get_settings
from app.connectors.router import router as connectors_router
from app.control_plane.router import router as control_plane_router
from app.generated_app.features import router as feature_worker_router
from app.generated_app.generic import router as generic_router
from app.generated_app.tasks import router as task_router
from app.orchestrator.router import router as orchestrator_router
from app.product import active_product
from app.reception.router import router as reception_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A dev reload / crash kills in-flight build threads; without this, their
    # 'designing' records stay locked forever while the chat claims progress.
    from app.reception import service as reception_service

    n = reception_service.recover_orphaned_builds()
    if n:
        print(f"[startup] reaped {n} orphaned build(s) left by the previous process")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AgentForge Core API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def audit_request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:12]}"
        request_token = audit_context.set_request_context(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            origin=request.headers.get("origin"),
            referer=request.headers.get("referer"),
        )
        actor_token = audit_context.clear_actor_context()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            audit_context.reset_actor_context(actor_token)
            audit_context.reset_request_context(request_token)

    # NOTE: Cloud Run's Google Front End intercepts "/healthz", so health lives at
    # "/health" (see memory cloud-run-reserved-healthz / HANDOFF.md §4).
    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "agentforge-core-api"}

    @app.get("/")
    def root() -> dict:
        product = active_product()
        return {
            "message": "AgentForge core API is running.",
            "framework": product.framework_name,
            "product": {"id": product.product_id, "display_name": product.display_name},
        }

    # All app/data routers require an allowlisted user in prod. /health and /
    # stay open for Cloud Run probes; APP_ENV=local keeps development open.
    # Admin module carries its own per-endpoint auth (current_user / require_admin),
    # so it is mounted without the blanket user guard. /api/me identifies the caller;
    # /api/admin/* require the separate admin allowlist.
    app.include_router(admin_router)

    guard = [Depends(require_allowed_user)]
    app.include_router(reception_router, dependencies=guard)
    app.include_router(orchestrator_router, dependencies=guard)
    app.include_router(control_plane_router, dependencies=guard)
    app.include_router(task_router, dependencies=guard)
    app.include_router(generic_router, dependencies=guard)
    app.include_router(feature_worker_router, dependencies=guard)
    app.include_router(connectors_router, dependencies=guard)
    return app


app = create_app()
