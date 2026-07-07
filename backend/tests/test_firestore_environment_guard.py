import pytest

from app.config import get_settings
from app.firestore import _validate_firestore_target


def _set_env(monkeypatch: pytest.MonkeyPatch, app_env: str, emulator: str | None) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    if emulator is None:
        monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    else:
        monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", emulator)
    get_settings.cache_clear()


def test_prod_rejects_firestore_emulator(monkeypatch):
    _set_env(monkeypatch, "prod", "localhost:8081")

    with pytest.raises(RuntimeError, match="APP_ENV=prod"):
        _validate_firestore_target()

    get_settings.cache_clear()


@pytest.mark.parametrize("app_env", ["local", "demo", "test"])
def test_non_prod_requires_firestore_emulator(monkeypatch, app_env):
    _set_env(monkeypatch, app_env, None)

    with pytest.raises(RuntimeError, match="requires FIRESTORE_EMULATOR_HOST"):
        _validate_firestore_target()

    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("app_env", "emulator"),
    [("prod", None), ("local", "localhost:8081"), ("demo", "localhost:8081"), ("test", "localhost:8081")],
)
def test_valid_firestore_targets(monkeypatch, app_env, emulator):
    _set_env(monkeypatch, app_env, emulator)

    _validate_firestore_target()

    get_settings.cache_clear()
