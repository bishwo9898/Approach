"""Media provider selection."""

from __future__ import annotations

from bsa.core.config import Settings
from bsa.core.errors import IntegrationNotConfiguredError
from bsa.integrations.media.base import MediaStore, MediaUploadError, StoredMedia
from bsa.integrations.storage import get_object_store

__all__ = [
    "MediaStore",
    "MediaUploadError",
    "StoredMedia",
    "get_media_store",
]


def get_media_store(settings: Settings) -> MediaStore:
    kind = settings.media_provider.lower()
    if kind == "local":
        from bsa.integrations.media.local import LocalMediaStore

        return LocalMediaStore(get_object_store(settings))
    if kind == "cloudinary":
        from bsa.integrations.media.cloudinary import CloudinaryMediaStore

        missing = [
            name
            for name, value in (
                ("BSA_CLOUDINARY_CLOUD_NAME", settings.cloudinary_cloud_name),
                ("BSA_CLOUDINARY_API_KEY", settings.cloudinary_api_key),
                ("BSA_CLOUDINARY_API_SECRET", settings.cloudinary_api_secret),
            )
            if not value
        ]
        if missing:
            raise IntegrationNotConfiguredError(
                f"Cloudinary is selected but {', '.join(missing)} are not set."
            )
        return CloudinaryMediaStore(
            settings.cloudinary_cloud_name or "",
            settings.cloudinary_api_key or "",
            settings.cloudinary_api_secret or "",
        )
    raise IntegrationNotConfiguredError(f"unknown media provider {kind!r}")
