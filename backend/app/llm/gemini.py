"""Gemini client with graceful stub fallback + model routing.

Design (IMPLEMENTATION_GUIDE.md §2.5):
- Cheap understanding/structuring -> Flash. Heavy planning/codegen -> Pro.
- The API key lives in Secret Manager (prod) or backend/.env (local dev), never
  in source. When no key is configured, `generate()` returns a deterministic stub
  so the whole pipeline is exercisable offline and in CI.
"""
from __future__ import annotations

from enum import Enum
from functools import lru_cache

from app.config import get_settings


class ModelTier(str, Enum):
    FLASH = "flash"  # cheap, fast: understanding / structuring / routing
    PRO = "pro"      # capable: planning / code generation


class GeminiClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.gemini_api_key
        self._models = {
            ModelTier.FLASH: settings.gemini_flash_model,
            ModelTier.PRO: settings.gemini_pro_model,
        }
        self._client = None  # lazily created on first real call (cold-start friendly)

    @property
    def enabled(self) -> bool:
        """True when a real API key is configured. False -> stub responses."""
        return bool(self._api_key)

    def _ensure_client(self):
        if self._client is None:
            from google import genai  # local import keeps module import cheap

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def generate(self, prompt: str, tier: ModelTier = ModelTier.FLASH) -> str:
        if not self.enabled:
            return self._stub(prompt, tier)
        client = self._ensure_client()
        resp = client.models.generate_content(
            model=self._models[tier],
            contents=prompt,
        )
        return (resp.text or "").strip()

    @staticmethod
    def _stub(prompt: str, tier: ModelTier) -> str:
        # Deterministic placeholder so callers can run end-to-end without a key.
        return f"[gemini-stub:{tier.value}] (no API key configured) :: {prompt[:120]}"


@lru_cache
def get_gemini() -> GeminiClient:
    return GeminiClient()
