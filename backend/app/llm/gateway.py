"""LLM Provider Gateway: selects the active provider (IMPLEMENTATION_GUIDE.md §2.6).

Selection order:
  1. settings.llm_provider  (explicit: "gemini" | "claude-cli" | "stub")
  2. else by environment:    app_env == "local" -> "claude-cli", otherwise "gemini"

The switching mechanism ships in prod too, but the *available* providers differ by
environment (claude-cli only works locally where the host bridge runs).

Call sites import everything from here:  from app.llm.gateway import get_llm, ModelTier
"""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.llm.base import LLMProvider, ModelTier  # noqa: F401  (re-exported)
from app.llm.providers.claude_cli import ClaudeCliProvider
from app.llm.providers.gemini import GeminiProvider
from app.llm.providers.stub import StubProvider

_REGISTRY = {
    "gemini": GeminiProvider,
    "claude-cli": ClaudeCliProvider,
    "stub": StubProvider,
}


def select_provider_name(llm_provider: str, app_env: str) -> str:
    """Pure selection logic (testable without touching settings/env)."""
    if llm_provider:
        return llm_provider.strip().lower()
    return "claude-cli" if app_env.strip().lower() == "local" else "gemini"


@lru_cache
def get_llm() -> LLMProvider:
    s = get_settings()
    name = select_provider_name(s.llm_provider, s.app_env)
    provider_cls = _REGISTRY.get(name, GeminiProvider)
    return provider_cls()


def model_label(tier: ModelTier) -> str:
    """Human-readable model in use for a tier, e.g. "claude-cli:pro:sonnet" or
    "gemini:flash:gemini-flash-latest". Used by the status monitor."""
    llm = get_llm()
    model_for = getattr(llm, "model_for", None)
    model = (model_for(tier) if callable(model_for) else "") or "default"
    return f"{llm.name}:{tier.value}:{model}"
