"""The TrackMan provider contract.

Business services depend on this Protocol, never on a concrete provider. CSV
today, FTP or the Data API later, with no change above this line.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Protocol, runtime_checkable

from bsa.integrations.trackman.schema import ParseResult, SourcePayload


@runtime_checkable
class TrackmanProvider(Protocol):
    """Fetches and parses TrackMan source data.

    Split deliberately into discovery, retrieval and parsing:

      * `discover_sessions` is the only part that differs between a directory
        listing, an FTP poll and an API query.
      * `fetch_payload` returns bytes we archive *before* interpreting them.
      * `parse` is pure -- bytes in, normalized objects out -- so it can be
        replayed over the archive when the mapping changes.
    """

    name: str

    def discover_sessions(
        self, *, since: date | None = None, until: date | None = None
    ) -> Iterable[str]:
        """Identify available session references not yet known to be ingested."""
        ...

    def fetch_payload(self, reference: str) -> SourcePayload:
        """Retrieve the raw bytes behind a reference."""
        ...

    def parse(self, payload: SourcePayload) -> ParseResult:
        """Interpret raw bytes into normalized, canonical-unit domain objects."""
        ...
