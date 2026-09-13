"""Object store abstraction for raw source payloads.

Raw TrackMan files are kept forever so ingestion can be replayed after the
parser changes. Development writes to disk; production writes to GCS. The
`object_key` stored on `raw_imports` is opaque -- rows never contain a
filesystem path or bucket URL, so the backend can change without a data
migration.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ObjectStore(Protocol):
    def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str:
        """Store `data` at `key`. Returns the key actually written."""
        ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...


def build_object_key(
    organization_slug: str, provider: str, checksum: str, filename: str | None
) -> str:
    """Content-addressed key.

    The checksum is in the path, so storing the same bytes twice is naturally
    idempotent, and a key can be verified against its content later.
    """
    safe_name = (filename or "payload").replace("/", "_").replace("\\", "_")[-120:]
    return f"{organization_slug}/{provider}/{checksum[:2]}/{checksum}/{safe_name}"
