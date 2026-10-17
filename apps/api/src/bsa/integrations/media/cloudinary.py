"""Cloudinary-backed video storage.

Uploads as `authenticated`, not `upload`. The difference matters: a default
Cloudinary URL is public to anyone who has it, and this is footage of minors.
An authenticated asset is only reachable through a signed URL, and this module
mints one per request with a short life rather than storing a permanent link.
"""

from __future__ import annotations

import time
from typing import Any

from bsa.core.logging import get_logger
from bsa.integrations.media.base import MediaUploadError, StoredMedia

log = get_logger(__name__)

#: How long a playback link stays valid. Long enough to watch a session clip,
#: short enough that a copied URL is not a permanent handout.
SIGNED_URL_TTL_SECONDS = 2 * 60 * 60


class CloudinaryMediaStore:
    name = "cloudinary"

    def __init__(self, cloud_name: str, api_key: str, api_secret: str) -> None:
        self._config = {
            "cloud_name": cloud_name,
            "api_key": api_key,
            "api_secret": api_secret,
        }

    def _cloudinary(self) -> Any:
        try:
            import cloudinary
            import cloudinary.uploader
            import cloudinary.utils
        except ImportError as exc:  # pragma: no cover -- dependency missing
            raise MediaUploadError(
                "the cloudinary package is not installed; add it to the API dependencies"
            ) from exc
        cloudinary.config(secure=True, **self._config)
        return cloudinary

    def upload(self, data: bytes, *, filename: str, folder: str) -> StoredMedia:
        cloudinary = self._cloudinary()
        try:
            result = cloudinary.uploader.upload(
                data,
                resource_type="video",
                folder=folder,
                # Not reachable without a signature. See the module docstring.
                type="authenticated",
                filename=filename,
                use_filename=True,
                unique_filename=True,
                overwrite=False,
            )
        except Exception as exc:  # pragma: no cover -- network or credentials
            raise MediaUploadError(f"Cloudinary refused the upload: {exc}") from exc

        asset_id = str(result["public_id"])
        return StoredMedia(
            asset_id=asset_id,
            url=self.playback_url(asset_id, fallback=str(result.get("secure_url", ""))),
            thumbnail_url=self._thumbnail(asset_id),
            duration_seconds=_float(result.get("duration")),
            byte_size=_int(result.get("bytes")),
        )

    def playback_url(self, asset_id: str, *, fallback: str) -> str:
        cloudinary = self._cloudinary()
        url, _ = cloudinary.utils.cloudinary_url(
            asset_id,
            resource_type="video",
            type="authenticated",
            sign_url=True,
            expires_at=int(time.time()) + SIGNED_URL_TTL_SECONDS,
        )
        return str(url) if url else fallback

    def _thumbnail(self, asset_id: str) -> str | None:
        cloudinary = self._cloudinary()
        url, _ = cloudinary.utils.cloudinary_url(
            asset_id,
            resource_type="video",
            type="authenticated",
            format="jpg",
            sign_url=True,
            expires_at=int(time.time()) + SIGNED_URL_TTL_SECONDS,
            transformation=[{"width": 480, "crop": "scale"}],
        )
        return str(url) if url else None

    def delete(self, asset_id: str) -> None:
        cloudinary = self._cloudinary()
        try:
            cloudinary.uploader.destroy(asset_id, resource_type="video", type="authenticated")
        except Exception as exc:  # pragma: no cover -- network
            log.warning("media.delete_failed", asset_id=asset_id, error=str(exc))


def _float(value: Any) -> float | None:
    """Cloudinary omits duration for some containers, so this is best effort."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
