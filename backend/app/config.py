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

    # --- Worker tools ---
    # Server-side web search for Specialist Workers. Generated HTML must still
    # not fetch arbitrary URLs; workers may use this controlled read-only tool to
    # gather current public info and write summaries into app state.
    web_search_enabled: bool = True
    web_search_user_agent: str = "AgentForge/0.1 (+https://agentforge-devops.web.app)"

    # --- LLM Provider Gateway (IMPLEMENTATION_GUIDE.md §2.6) ---
    # app_env:
    # - "prod"  = production infrastructure and Firebase auth
    # - "demo"  = production-like Firebase auth, local emulators/data
    # - "local" = open local development
    # - "test"  = unit tests; Firestore use must be explicitly stubbed/emulated
    app_env: str = "prod"
    # llm_provider: "" = auto by env (local->claude-cli, else gemini).
    # Or force one of: "gemini" | "claude-cli" | "codex" | "stub".
    llm_provider: str = ""
    # claude-cli talks to a host bridge wrapping `claude -p` (LOCAL only; saves
    # Gemini cost). Not reachable on Cloud Run. See scripts/claude_bridge.py.
    claude_bridge_url: str = "http://host.docker.internal:8765/generate"
    # Capability tiers (canonical): FLASH = haiku, PRO = opus (matches Gemini
    # Flash/Pro). docker-compose.dev sets these explicitly (PRO=opus, FLASH=haiku)
    # so dev quality matches prod's tier; opus is slower but the LLM timeout is
    # generous and the user controls waiting.
    claude_flash_model: str = ""  # "" = bridge/session default (canonical: haiku)
    claude_pro_model: str = ""    # "" = bridge/session default (canonical: opus)
    # codex talks to a host bridge wrapping `codex exec` (LOCAL/demo only).
    codex_bridge_url: str = "http://host.docker.internal:8766/generate"
    codex_flash_model: str = ""
    codex_pro_model: str = ""
    # Read timeout for an LLM call. High-capability models (PRO) trade quality for
    # time: full-app generation legitimately takes minutes, and the deploy-time
    # gate adds more calls. Keep this generous (and >= the host bridge's
    # CLAUDE_TIMEOUT) so we don't give up on a good-but-slow result and stub it.
    # Long thinking is expected; the user controls stopping ("もう少し待つ"), not a
    # tight auto-timeout (workers.html §3(b)).
    llm_timeout_seconds: int = 600

    # --- HTTP / CORS ---
    # Comma-separated list of allowed origins for the browser SPA. Includes the
    # Firebase Hosting domains so the deployed app can call the API directly if
    # ever served cross-origin (the /api rewrite makes it same-origin in practice).
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "https://agentforge-498808.web.app,https://agentforge-498808.firebaseapp.com"
    )

    # --- Access control ---
    # Allowlist of permitted login emails. Prod is closed by default; an empty
    # value means only ADMIN_EMAILS can enter. Local dev is open via APP_ENV=local.
    # Separate multiple with ';' or space (NOT comma — gcloud --set-env-vars uses comma).
    # The admin page can ADD more allowed emails at runtime (stored in Firestore);
    # this env value is the bootstrap set.
    allowed_emails: str = "airpocket.soundman@gmail.com"
    # Admin allowlist (separate, smaller). Only these accounts reach the admin page
    # and can edit the user allowlist / feature flags. Admins are always allowed in.
    admin_emails: str = "yamashita.3154@gmail.com"
    # Optional contest/demo guest access. Keep off by default; enable on Cloud Run
    # with GUEST_ACCESS_ENABLED=true for review periods. Guests are non-admin users.
    guest_access_enabled: bool = False
    guest_email: str = "guest@agentforge.local"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_email_list(self) -> list[str]:
        import re

        return [e.strip().lower() for e in re.split(r"[;,\s]+", self.allowed_emails) if e.strip()]

    @property
    def is_local(self) -> bool:
        return self.app_env.strip().lower() == "local"

    @property
    def app_env_name(self) -> str:
        return self.app_env.strip().lower()

    @property
    def uses_production_infra(self) -> bool:
        return self.app_env_name == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
