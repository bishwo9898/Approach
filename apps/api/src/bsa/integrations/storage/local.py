"""Filesystem object store. Development and tests only."""

from __future__ import annotations

from pathlib import Path


class LocalObjectStore:
    """Writes payloads under a root directory.

    Refused in production by `Settings._guard_production`: Cloud Run disks are
    ephemeral, so this backend would quietly lose the raw archive.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        # Reject traversal outright rather than sanitizing: keys are generated
        # by us, so a key that escapes the root is a bug, not user input.
        candidate = (self.root / key).resolve()
        root = self.root.resolve()
        if not candidate.is_relative_to(root):
            raise ValueError(f"object key escapes store root: {key!r}")
        return candidate

    def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()
