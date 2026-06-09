"""LLM provider abstraction (Model Gateway) — IMPLEMENTATION_GUIDE.md §2.6.

A single interface so the app can switch LLM providers per environment / user
without touching call sites:
  - gemini     : Gemini API (prod default)
  - claude-cli : host `claude -p` via a small bridge (local default; saves Gemini cost)
  - stub       : deterministic, no network (unit tests / no key)

Model routing tiers map to each provider's cheap/capable models:
  FLASH = cheap/fast (understanding, structuring, routing)
  PRO   = capable    (planning, code generation)
"""
from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable


class ModelTier(str, Enum):
    FLASH = "flash"
    PRO = "pro"


# An image attachment for vision: {"mime": "image/png", "data": "<base64>"}.
ImageInput = dict


@runtime_checkable
class LLMProvider(Protocol):
    """Every provider exposes a name, an `enabled` flag (False -> callers use their
    deterministic fallbacks), and a `generate(prompt, tier, images) -> str`.

    `images` is an optional list of {mime, data(base64)} for multimodal/vision
    requests; providers that can't do vision ignore them gracefully."""

    name: str

    @property
    def enabled(self) -> bool: ...

    def generate(
        self, prompt: str, tier: ModelTier = ModelTier.FLASH, images: list[ImageInput] | None = None
    ) -> str: ...
