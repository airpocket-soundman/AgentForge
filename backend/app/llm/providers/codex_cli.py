"""codex provider (LOCAL/demo only).

Calls a host-side bridge that wraps `codex exec`. The container never shells out
to Codex directly; it sends a text generation request to the bridge, matching the
claude-cli provider shape.
"""
from __future__ import annotations

from app.config import get_settings
from app.llm.base import ModelTier


class CodexCliProvider:
    name = "codex"

    def __init__(self) -> None:
        s = get_settings()
        self._url = s.codex_bridge_url
        self._timeout = float(s.llm_timeout_seconds)
        self._models = {
            ModelTier.FLASH: s.codex_flash_model,
            ModelTier.PRO: s.codex_pro_model,
        }

    @property
    def enabled(self) -> bool:
        return bool(self._url)

    def model_for(self, tier: ModelTier) -> str:
        """Configured Codex model id for a tier ("" when using CLI default)."""
        return self._models.get(tier) or ""

    def generate(self, prompt: str, tier: ModelTier = ModelTier.FLASH, images=None) -> str:
        import httpx

        payload: dict = {"prompt": prompt, "tier": tier.value}
        model = self._models.get(tier)
        if model:
            payload["model"] = model
        if images:
            payload["images"] = images
        timeout = httpx.Timeout(connect=5.0, read=self._timeout, write=10.0, pool=5.0)
        resp = httpx.post(self._url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return (resp.json().get("text") or "").strip()
