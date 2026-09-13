"""The Futures App provider contract.

We do not know how The Futures App accepts data. API access, partner API, CSV
import, bulk ingestion and webhooks are all unconfirmed.

What we will NOT do, regardless of convenience: reverse engineer its private
endpoints, drive its UI with a scripted browser, or scrape it. Those approaches
break without warning, are very likely to violate its terms of use, and would
put the facility's account at risk.

So this interface exists, two honest implementations exist behind it (a manual
worklist and a mock for tests), and the real one gets written when a supported
method is confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class MetricPush:
    """One value destined for the external system."""

    external_player_id: str
    destination_field: str
    value: float
    unit: str
    #: Our metric key, carried for traceability in logs and audit records.
    metric_key: str


@dataclass(frozen=True, slots=True)
class PushResult:
    accepted: bool
    #: True when the value could not be delivered automatically and a person
    #: must enter it. This is the expected outcome today, not an error.
    requires_manual_entry: bool = False
    message: str | None = None


@runtime_checkable
class FuturesProvider(Protocol):
    name: str

    def get_player_mapping(self, external_player_id: str) -> dict[str, str] | None:
        """Look up the destination system's record for a mapped athlete."""
        ...

    def update_player_metric(self, push: MetricPush) -> PushResult:
        """Deliver one metric value, or report that a human must."""
        ...
