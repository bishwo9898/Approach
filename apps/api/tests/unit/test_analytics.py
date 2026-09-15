"""Window-level dashboard aggregation."""

from __future__ import annotations

import pytest

from bsa.domain.enums import Aggregation
from bsa.services.analytics import _aggregate


def test_average_weights_sessions_by_their_sample_size() -> None:
    """A five-pitch bullpen must not count as much as a forty-pitch bullpen."""
    result = _aggregate([(80.0, 5), (90.0, 40)], Aggregation.AVG)

    assert result == pytest.approx((80.0 * 5 + 90.0 * 40) / 45)


def test_rate_weights_sessions_by_their_sample_size() -> None:
    result = _aggregate([(100.0, 5), (50.0, 15)], Aggregation.RATE)

    assert result == pytest.approx(62.5)


@pytest.mark.parametrize(
    ("aggregation", "expected"),
    [
        (Aggregation.MAX, 90.0),
        (Aggregation.MIN, 80.0),
        (Aggregation.COUNT, 170.0),
        (Aggregation.SUM, 170.0),
    ],
)
def test_non_average_rollups_keep_their_declared_semantics(
    aggregation: Aggregation, expected: float
) -> None:
    assert _aggregate([(80.0, 5), (90.0, 40)], aggregation) == expected


def test_weighted_rollup_ignores_values_without_evidence() -> None:
    assert _aggregate([(99.0, 0), (88.0, 10)], Aggregation.AVG) == 88.0
