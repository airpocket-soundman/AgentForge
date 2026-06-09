"""Gemini provider (prod default). Key lives in Secret Manager (prod) or
backend/.env (local); never in source. No key -> enabled=False -> callers fall
back to deterministic output."""
from __future__ import annotations

from app.config import get_settings
from app.llm.base import ModelTier


class GeminiProvider:
    name = "gemini"

    def __init__(self) -> None:
        s = get_settings()
        self._api_key = s.gemini_api_key
        self._models = {
            ModelTier.FLASH: s.gemini_flash_model,
            ModelTier.PRO: s.gemini_pro_model,
        }
        self._client = None  # lazily created on first real call (cold-start friendly)

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def _ensure_client(self):
        if self._client is None:
            from google import genai  # local import keeps module import cheap

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def generate(self, prompt: str, tier: ModelTier = ModelTier.FLASH, images=None) -> str:
        if not self.enabled:
            return f"[gemini-stub:{tier.value}] (no API key configured) :: {prompt[:120]}"
        contents: list = [prompt]
        if images:
            import base64

            from google.genai import types  # local import keeps module import cheap

            for img in images:
                try:
                    raw = base64.b64decode(img.get("data", ""))
                    contents.append(types.Part.from_bytes(data=raw, mime_type=img.get("mime", "image/png")))
                except Exception:  # noqa: BLE001 — skip a bad image, keep the text request
                    continue
        resp = self._ensure_client().models.generate_content(
            model=self._models[tier], contents=contents
        )
        return (resp.text or "").strip()
