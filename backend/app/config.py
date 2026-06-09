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

    # --- LLM Provider Gateway (IMPLEMENTATION_GUIDE.md §2.6) ---
    # app_env: "prod" (default) | "local". docker-compose.dev sets "local".
    app_env: str = "prod"
    # llm_provider: "" = auto by env (local->claude-cli, else gemini).
    # Or force one of: "gemini" | "claude-cli" | "stub".
    llm_provider: str = ""
    # claude-cli talks to a host bridge wrapping `claude -p` (LOCAL only; saves
    # Gemini cost). Not reachable on Cloud Run. See scripts/claude_bridge.py.
    claude_bridge_url: str = "http://host.docker.internal:8765/generate"
    claude_flash_model: str = ""  # "" = bridge/session default
    claude_pro_model: str = ""    # "" = bridge/session default
    llm_timeout_seconds: int = 180

    # --- HTTP / CORS ---
    # Comma-separated list of allowed origins for the browser SPA. Includes the
    # Firebase Hosting domains so the deployed app can call the API directly if
    # ever served cross-origin (the /api rewrite makes it same-origin in practice).
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "https://agentforge-498808.web.app,https://agentforge-498808.firebaseapp.com"
    )

    # --- Access control ---
    # Allowlist of permitted login emails. EMPTY = enforcement OFF (open, e.g. local
    # dev). Set in prod (ALLOWED_EMAILS) to restrict who can use the app. Separate
    # multiple with ';' or space (NOT comma — gcloud --set-env-vars uses comma).
    # The admin page can ADD more allowed emails at runtime (stored in Firestore);
    # this env value is the bootstrap set.
    allowed_emails: str = ""
    # Admin allowlist (separate, smaller). Only these accounts reach the admin page
    # and can edit the user allowlist / feature flags. Admins are always allowed in.
    admin_emails: str = "yamashita.3154@gmail.com"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_email_list(self) -> list[str]:
        import re

        return [e.strip().lower() for e in re.split(r"[;,\s]+", self.allowed_emails) if e.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
