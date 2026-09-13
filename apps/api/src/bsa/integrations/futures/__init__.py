"""Futures integration selection."""

from __future__ import annotations

from bsa.core.config import Settings
from bsa.core.errors import IntegrationNotConfiguredError
from bsa.integrations.futures.base import FuturesProvider, MetricPush, PushResult
from bsa.integrations.futures.manual import ManualFuturesProvider
from bsa.integrations.futures.mock import MockFuturesProvider

__all__ = [
    "FuturesProvider",
    "ManualFuturesProvider",
    "MetricPush",
    "MockFuturesProvider",
    "PushResult",
    "get_futures_provider",
]


def get_futures_provider(settings: Settings) -> FuturesProvider:
    kind = settings.futures_provider.lower()
    if kind == "manual":
        return ManualFuturesProvider()
    if kind == "mock":
        if not settings.is_development:
            raise IntegrationNotConfiguredError(
                "the mock Futures provider is refused outside development"
            )
        return MockFuturesProvider()
    raise IntegrationNotConfiguredError(
        f"unknown Futures provider {kind!r}. Only 'manual' and 'mock' exist: no supported "
        "Futures ingestion method has been confirmed yet."
    )
