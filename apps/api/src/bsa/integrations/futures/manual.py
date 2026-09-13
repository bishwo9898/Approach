"""The provider that reflects reality today: a human types the value.

This is not a placeholder that does nothing. Every push it declines becomes a
row on the coach's "Futures updates pending" worklist with the athlete, the
field and the exact value to enter -- which removes the part the coach actually
finds painful (working out *which* numbers changed) even with zero automation.
"""

from __future__ import annotations

from bsa.integrations.futures.base import MetricPush, PushResult


class ManualFuturesProvider:
    name = "futures"

    def get_player_mapping(self, external_player_id: str) -> dict[str, str] | None:
        return None

    def update_player_metric(self, push: MetricPush) -> PushResult:
        return PushResult(
            accepted=False,
            requires_manual_entry=True,
            message=(
                f"No confirmed Futures ingestion method. Enter {push.destination_field} "
                f"= {push.value:g} {push.unit} manually, then mark it updated."
            ),
        )
