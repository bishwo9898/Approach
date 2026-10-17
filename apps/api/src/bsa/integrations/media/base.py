"""Where athlete video actually lives, behind an adapter.

Hosting video is real infrastructure -- transcoding, bandwidth, and access
control on footage of minors -- so it is delegated rather than built. What stays
ours is the record of which athlete a clip is of and who may see it.

Two rules this boundary exists to keep:

* **The database never holds the bytes.** It holds a reference, and the
  provider's own id for the asset, which is what a takedown needs.
* **A playback URL is produced at read time, not stored.** A provider that can
  expire links should be allowed to, and a URL saved in a row would outlive
  whatever permission produced it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class StoredMedia:
    """What a provider returns once it has the file."""

    #: The provider's own identifier, and the only thing a delete needs.
    asset_id: str
    #: A URL that plays it. May be short-lived -- see `playback_url`.
    url: str
    thumbnail_url: str | None = None
    duration_seconds: float | None = None
    byte_size: int | None = None


class MediaUploadError(RuntimeError):
    """The provider refused or could not be reached."""


@runtime_checkable
class MediaStore(Protocol):
    name: str

    def upload(self, data: bytes, *, filename: str, folder: str) -> StoredMedia:
        """Store a video and return where it went."""
        ...

    def playback_url(self, asset_id: str, *, fallback: str) -> str:
        """A URL that plays this asset now.

        Regenerated per request so a provider can hand out links that expire.
        `fallback` is the URL recorded at upload time, used when the asset
        predates this provider or the provider has no opinion.
        """
        ...

    def delete(self, asset_id: str) -> None:
        """Remove the asset. Silent when it is already gone."""
        ...
