"""Extension points for TrackMan paths we do not yet have access to.

These are deliberately non-functional. We have not been given FTP credentials or
Data API documentation, and writing speculative request code against an API
whose shape we have not seen would produce something that looks finished, passes
nothing, and has to be thrown away.

Each class below fails loudly with what is actually missing, and documents
exactly which methods need bodies once access exists. `parse` is already
inherited work: the CSV provider's parser is reused wherever the payload is
delimited text, which is why parsing was separated from retrieval in
`TrackmanProvider`.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from bsa.core.errors import IntegrationNotConfiguredError
from bsa.integrations.trackman.csv_provider import TrackmanCsvProvider
from bsa.integrations.trackman.schema import ParseResult, SourcePayload


class TrackmanFtpProvider:
    """Automated retrieval from a TrackMan organization FTP drop.

    To implement, once credentials exist:
      * `discover_sessions` -- list the remote directory, filter by date, and
        skip references whose checksum is already in `raw_imports`.
      * `fetch_payload` -- download to memory and return the bytes untouched.
    `parse` delegates to the CSV parser; only the mapping in
    `integrations/trackman/mapping.py` should need a new entry.
    """

    name = "trackman"

    def __init__(self, host: str | None, username: str | None, password: str | None) -> None:
        if not (host and username and password):
            raise IntegrationNotConfiguredError(
                "TrackMan FTP credentials are not provisioned. Set BSA_TRACKMAN_FTP_HOST, "
                "BSA_TRACKMAN_FTP_USER and BSA_TRACKMAN_FTP_PASSWORD (Secret Manager in "
                "production), then implement discover_sessions/fetch_payload."
            )
        self._host = host
        self._username = username
        self._password = password

    def discover_sessions(
        self, *, since: date | None = None, until: date | None = None
    ) -> Iterable[str]:
        raise IntegrationNotConfiguredError("TrackMan FTP discovery is not implemented yet")

    def fetch_payload(self, reference: str) -> SourcePayload:
        raise IntegrationNotConfiguredError("TrackMan FTP retrieval is not implemented yet")

    def parse(self, payload: SourcePayload) -> ParseResult:
        return TrackmanCsvProvider().parse(payload)


class TrackmanApiProvider:
    """The TrackMan Data API.

    Not implemented: we have neither credentials nor the API documentation, and
    its request/response shapes are not something to invent. When access is
    granted, `httpx` and `tenacity` are already dependencies for the retry-safe
    client, and the JSON-to-domain mapping belongs beside the CSV mapping.
    """

    name = "trackman"

    def __init__(self, base_url: str | None, client_id: str | None, client_secret: str | None):
        raise IntegrationNotConfiguredError(
            "The TrackMan Data API integration is not implemented. It will be built "
            "once API access and official documentation are available -- see "
            "docs/TRACKMAN_INTEGRATION.md for the open questions."
        )
