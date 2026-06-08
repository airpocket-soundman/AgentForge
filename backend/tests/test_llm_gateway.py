"""Unit tests for the LLM Provider Gateway (IMPLEMENTATION_GUIDE.md §2.6).

Pure / offline: no network, no API keys. Verifies provider selection and the
enabled/deterministic contract that the rest of the pipeline relies on.
"""
from app.llm.base import ModelTier
from app.llm.gateway import select_provider_name
from app.llm.providers.gemini import GeminiProvider
from app.llm.providers.stub import StubProvider


def test_select_provider_name_by_env():
    # No explicit provider -> chosen by environment.
    assert select_provider_name("", "prod") == "gemini"
    assert select_provider_name("", "local") == "claude-cli"


def test_select_provider_name_explicit_wins():
    assert select_provider_name("stub", "local") == "stub"
    assert select_provider_name("GEMINI", "local") == "gemini"  # case-insensitive


def test_stub_disabled_and_deterministic():
    p = StubProvider()
    assert p.enabled is False  # -> callers use their deterministic fallbacks
    assert "stub" in p.generate("hello", ModelTier.FLASH)


def test_gemini_disabled_without_key():
    # In CI/local test env no GEMINI_API_KEY -> disabled -> deterministic text.
    p = GeminiProvider()
    assert p.enabled is False
    assert p.generate("hi", ModelTier.PRO).startswith("[gemini-stub")
