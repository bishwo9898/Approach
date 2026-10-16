"""The rate limit on unauthenticated endpoints."""

from __future__ import annotations

import pytest

from bsa.core.throttle import RateLimitedError, SlidingWindowLimiter


def test_requests_within_the_budget_pass() -> None:
    limiter = SlidingWindowLimiter(limit=3, window_seconds=60)
    for _ in range(3):
        limiter.check("1.2.3.4")


def test_the_budget_is_enforced() -> None:
    limiter = SlidingWindowLimiter(limit=3, window_seconds=60)
    for _ in range(3):
        limiter.check("1.2.3.4")
    with pytest.raises(RateLimitedError) as caught:
        limiter.check("1.2.3.4")
    assert caught.value.status_code == 429
    assert caught.value.details["retry_after_seconds"] > 0


def test_budgets_are_per_key() -> None:
    """One person mistyping a password must not lock out everybody else."""
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60)
    limiter.check("1.2.3.4")
    limiter.check("5.6.7.8")


def test_the_window_slides(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [1000.0]
    monkeypatch.setattr("bsa.core.throttle.time.monotonic", lambda: clock[0])

    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)
    limiter.check("k")
    limiter.check("k")
    with pytest.raises(RateLimitedError):
        limiter.check("k")

    clock[0] += 61
    limiter.check("k")  # the earlier two have aged out


def test_idle_keys_are_forgotten(monkeypatch: pytest.MonkeyPatch) -> None:
    """Otherwise a long-running process keeps one entry per address ever tried."""
    clock = [1000.0]
    monkeypatch.setattr("bsa.core.throttle.time.monotonic", lambda: clock[0])

    limiter = SlidingWindowLimiter(limit=5, window_seconds=10)
    for index in range(600):
        limiter.check(f"key-{index}")

    clock[0] += 3600
    limiter.check("fresh")
    assert len(limiter._hits) < 600
