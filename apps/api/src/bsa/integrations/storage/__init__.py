"""Object store selection."""

from __future__ import annotations

from bsa.core.config import Settings
from bsa.core.errors import IntegrationNotConfiguredError
from bsa.integrations.storage.base import ObjectStore, build_object_key
from bsa.integrations.storage.local import LocalObjectStore

__all__ = ["LocalObjectStore", "ObjectStore", "build_object_key", "get_object_store"]


def get_object_store(settings: Settings) -> ObjectStore:
    backend = settings.object_store_backend.lower()
    if backend == "local":
        return LocalObjectStore(settings.object_store_local_root)
    if backend == "gcs":
        from bsa.integrations.storage.gcs import GcsObjectStore

        if not settings.gcs_bucket:
            raise IntegrationNotConfiguredError("BSA_GCS_BUCKET is not set")
        return GcsObjectStore(settings.gcs_bucket)
    raise IntegrationNotConfiguredError(f"unknown object store backend {backend!r}")
