"""Runtime configuration for the AgentForge core API.

Values come from environment variables (12-factor). In local Docker dev they are
injected by docker-compose; on Cloud Run they come from the service config /
Secret Manager. Nothing secret is hard-coded here.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- GCP ---
    google_cloud_project: str = "agentforge-498808"
    google_cloud_region: str = "asia-northeast1"

    # --- Firestore ---
    # When set (local dev), google-cloud-firestore talks to the emulator and
    # skips real credentials. Unset on Cloud Run -> uses the runtime SA.
    firestore_emulator_host: str | None = None

    # --- Gemini (wired in Phase 2; key lives in Secret Manager, never here) ---
    gemini_api_key: str | None = None
    gemini_flash_model: str = "gemini-flash-latest"
    gemini_pro_model: str = "gemini-pro-latest"

    # --- HTTP / CORS ---
    # Comma-separated list of allowed origins for the browser SPA. Includes the
    # Firebase Hosting domains so the deployed app can call the API directly if
    # ever served cross-origin (the /api rewrite makes it same-origin in practice).
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "https://agentforge-498808.web.app,https://agentforge-498808.firebaseapp.com"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
