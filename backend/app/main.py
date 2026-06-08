"""AgentForge core API — Cloud Run entrypoint.

Phase 0: minimal deployable skeleton (health check only).
Reception / Orchestrator / Control Plane modules are added in later phases.
"""
from fastapi import FastAPI

app = FastAPI(title="AgentForge Core API", version="0.0.1")


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "agentforge-core-api"}


@app.get("/")
def root():
    return {"message": "AgentForge core API is running."}
