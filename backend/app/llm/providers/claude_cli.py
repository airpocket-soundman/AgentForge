"""claude-cli provider (LOCAL/dev default — saves Gemini cost).

Calls a host-side bridge that wraps `claude -p` (uses the host's Claude Code
session). Not available on Cloud Run (no claude CLI there); the gateway only
selects this provider in local/dev. See scripts/claude_bridge.py.
"""
from __future__ import annotations

from app.config import get_settings
from app.llm.base import ModelTier


class ClaudeCliProvider:
    name = "claude-cli"

    def __init__(self) -> None:
        s = get_settings()
        self._url = s.claude_bridge_url
        self._timeout = float(s.llm_timeout_seconds)
        self._models = {
            ModelTier.FLASH: s.claude_flash_model,
            ModelTier.PRO: s.claude_pro_model,
        }

    @property
    def enabled(self) -> bool:
        return bool(self._url)

    def generate(self, prompt: str, tier: ModelTier = ModelTier.FLASH) -> str:
        import httpx  # local import keeps module import cheap

        payload = {"prompt": prompt, "tier": tier.value}
        model = self._models.get(tier)
        if model:
            payload["model"] = model
        # Fast connect timeout so a missing bridge fails immediately (callers then
        # fall back to deterministic output) instead of hanging.
        timeout = httpx.Timeout(connect=5.0, read=self._timeout, write=10.0, pool=5.0)
        resp = httpx.post(self._url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return (resp.json().get("text") or "").strip()
