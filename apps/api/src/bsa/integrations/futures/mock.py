"""In-memory Futures provider for tests and local development.

Records what would have been sent so the sync pipeline can be exercised
end to end without inventing a vendor API. Never used outside tests and dev.
"""

from __future__ import annotations

from bsa.integrations.futures.base import MetricPush, PushResult


class MockFuturesProvider:
    name = "futures"

    def __init__(self, *, fail_on: set[str] | None = None) -> None:
        self.pushed: list[MetricPush] = []
        self.mappings: dict[str, dict[str, str]] = {}
        #: Destination fields to reject, for exercising the failure path.
        self._fail_on = fail_on or set()

    def get_player_mapping(self, external_player_id: str) -> dict[str, str] | None:
        return self.mappings.get(external_player_id)

    def update_player_metric(self, push: MetricPush) -> PushResult:
        if push.destination_field in self._fail_on:
            return PushResult(accepted=False, message="mock: destination rejected the value")
        self.pushed.append(push)
        return PushResult(accepted=True, message="mock: accepted")
