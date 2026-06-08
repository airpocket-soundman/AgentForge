"""Backward-compat shim.

The Gemini implementation now lives in `app.llm.providers.gemini` and the active
provider is chosen by the gateway (IMPLEMENTATION_GUIDE.md §2.6). Prefer:

    from app.llm.gateway import get_llm, ModelTier

`get_gemini` here aliases `get_llm` (returns the *selected* provider, which may be
claude-cli/stub locally) — kept so older imports keep working.
"""
from app.llm.base import ModelTier  # noqa: F401
from app.llm.gateway import get_llm as get_gemini  # noqa: F401
