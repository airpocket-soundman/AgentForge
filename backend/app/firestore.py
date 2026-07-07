"""Firestore client provider.

The client is created lazily so the container starts fast (cold-start friendly)
and so the module imports cleanly even when Firestore libs aren't reachable yet.
When ``FIRESTORE_EMULATOR_HOST`` is set, the google client auto-targets the
emulator with anonymous credentials — no service account needed in local dev.
"""
from functools import lru_cache

from google.cloud import firestore

from app.config import get_settings


def _validate_firestore_target() -> None:
    settings = get_settings()
    env = settings.app_env_name
    emulator = bool(settings.firestore_emulator_host)

    if env == "prod" and emulator:
        raise RuntimeError(
            "Invalid Firestore configuration: APP_ENV=prod must not use "
            "FIRESTORE_EMULATOR_HOST. Use APP_ENV=demo for auth-enabled local demos."
        )

    if env in {"local", "demo", "test"} and not emulator:
        raise RuntimeError(
            f"Invalid Firestore configuration: APP_ENV={env} requires "
            "FIRESTORE_EMULATOR_HOST so development/test code cannot touch production Firestore."
        )


@lru_cache
def get_db() -> firestore.Client:
    settings = get_settings()
    _validate_firestore_target()
    # firestore.Client reads FIRESTORE_EMULATOR_HOST from the environment itself,
    # but we pass project explicitly so the emulator namespaces documents correctly.
    return firestore.Client(project=settings.google_cloud_project)
