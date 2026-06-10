"""stub provider: enabled=False so callers use their deterministic fallbacks.
Used by unit tests and when nothing is configured (fully offline)."""
from __future__ import annotations

from app.llm.base import ModelTier


class StubProvider:
    name = "stub"

    @property
    def enabled(self) -> bool:
        return False

    def model_for(self, tier: ModelTier) -> str:
        return ""

    def generate(self, prompt: str, tier: ModelTier = ModelTier.FLASH, images=None) -> str:
        return f"[stub:{tier.value}] :: {prompt[:120]}"
