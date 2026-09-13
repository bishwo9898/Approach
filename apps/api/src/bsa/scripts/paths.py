"""Locating the repository root from inside the package.

Counting `.parents[n]` by hand at each call site has been wrong twice already,
in two different scripts, and the failure is quiet -- files get written to a
plausible-looking directory nobody looks in. Resolved once, here, by finding a
marker rather than counting levels, so moving a module cannot break it.
"""

from __future__ import annotations

from pathlib import Path

#: Files that only ever exist at the repository root.
_MARKERS = ("pnpm-workspace.yaml", "docker-compose.yml")


def repo_root() -> Path:
    """Walk upward to the repository root."""
    for candidate in Path(__file__).resolve().parents:
        if any((candidate / marker).exists() for marker in _MARKERS):
            return candidate
    raise RuntimeError(
        f"could not locate the repository root: none of {_MARKERS} was found above {__file__}"
    )


def samples_dir() -> Path:
    return repo_root() / "samples" / "trackman"


def shared_dir() -> Path:
    return repo_root() / "packages" / "shared"
