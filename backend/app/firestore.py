"""Firestore client provider.

The client is created lazily so the container starts fast (cold-start friendly)
and so the module imports cleanly even when Firestore libs aren't reachable yet.
When ``FIRESTORE_EMULATOR_HOST`` is set, the google client auto-targets the
emulator with anonymous credentials — no service account needed in local dev.
"""
from functools import lru_cache

from google.cloud import firestore

from app.config import get_settings


@lru_cache
def get_db() -> firestore.Client:
    settings = get_settings()
    # firestore.Client reads FIRESTORE_EMULATOR_HOST from the environment itself,
    # but we pass project explicitly so the emulator namespaces documents correctly.
    return firestore.Client(project=settings.google_cloud_project)
