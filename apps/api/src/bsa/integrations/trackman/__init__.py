"""TrackMan integration."""

from __future__ import annotations

from pathlib import Path

from bsa.core.config import Settings
from bsa.core.errors import IntegrationNotConfiguredError
from bsa.integrations.trackman.base import TrackmanProvider
from bsa.integrations.trackman.csv_provider import TrackmanCsvProvider

__all__ = ["TrackmanCsvProvider", "TrackmanProvider", "get_trackman_provider"]


def get_trackman_provider(
    settings: Settings, *, source_dir: Path | None = None
) -> TrackmanProvider:
    kind = settings.trackman_provider.lower()
    if kind == "csv":
        return TrackmanCsvProvider(source_dir)
    if kind == "ftp":
        from bsa.integrations.trackman.pending_providers import TrackmanFtpProvider

        return TrackmanFtpProvider(None, None, None)
    if kind == "api":
        # Deliberately not constructed: there is no implementation to return,
        # and returning a stub that satisfies the Protocol shape while doing
        # nothing would let a misconfiguration reach production silently.
        raise IntegrationNotConfiguredError(
            "The TrackMan Data API integration is not implemented. It will be built once "
            "API access and official documentation are available -- see "
            "docs/TRACKMAN_INTEGRATION.md."
        )
    raise IntegrationNotConfiguredError(f"unknown TrackMan provider {kind!r}")
