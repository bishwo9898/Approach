"""Development-only video storage, on top of the object store.

Exists so the upload path can be exercised without Cloudinary credentials. It
is refused outside development by `Settings._guard_production`, because serving
minors' footage from an unauthenticated route is only acceptable on a laptop.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from bsa.integrations.media.base import StoredMedia
from bsa.integrations.storage import ObjectStore


class LocalMediaStore:
    name = "local"

    def __init__(self, store: ObjectStore, public_base: str = "/api/v1/media") -> None:
        self._store = store
        self._base = public_base.rstrip("/")

    def upload(self, data: bytes, *, filename: str, folder: str) -> StoredMedia:
        suffix = Path(filename).suffix or ".mp4"
        key = f"{folder}/{uuid.uuid4().hex}{suffix}"
        self._store.put(key, data, content_type="video/mp4")
        return StoredMedia(
            asset_id=key,
            url=f"{self._base}/{key}",
            byte_size=len(data),
        )

    def playback_url(self, asset_id: str, *, fallback: str) -> str:
        return f"{self._base}/{asset_id}"

    def delete(self, asset_id: str) -> None:
        # The local object store has no delete; a development file left behind
        # costs nothing and the directory is disposable.
        return None
