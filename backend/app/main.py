"""AgentForge core API — Cloud Run entrypoint.

Phase 0: minimal deployable skeleton (health check only).
Reception / Orchestrator / Control Plane modules are added in later phases.
"""
from fastapi import FastAPI

app = FastAPI(title="AgentForge Core API", version="0.0.1")


# NOTE: Cloud Run's Google Front End intercepts the "/healthz" path before it
# reaches the container, so we expose the health check at "/health" instead.
@app.get("/health")
def health():
    return {"status": "ok", "service": "agentforge-core-api"}


@app.get("/")
def root():
    return {"message": "AgentForge core API is running."}
