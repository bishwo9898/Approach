"""Google Cloud Storage object store.

Not wired up yet: `google-cloud-storage` is intentionally not a dependency until
the GCP project exists, so the dependency tree stays honest about what is
actually running. The import is local to the constructor for the same reason.
"""

from __future__ import annotations

from typing import Any

from bsa.core.errors import IntegrationNotConfiguredError


class GcsObjectStore:
    def __init__(self, bucket: str) -> None:
        try:
            from google.cloud import storage  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover -- depends on deploy extras
            raise IntegrationNotConfiguredError(
                "GCS object store requires the 'google-cloud-storage' package, "
                "which is installed only in the deployed image."
            ) from exc
        self._bucket_name = bucket
        self._client: Any = storage.Client()
        self._bucket: Any = self._client.bucket(bucket)

    def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str:
        self._bucket.blob(key).upload_from_string(data, content_type=content_type)
        return key

    def get(self, key: str) -> bytes:
        blob: bytes = self._bucket.blob(key).download_as_bytes()
        return blob

    def exists(self, key: str) -> bool:
        return bool(self._bucket.blob(key).exists())
