"""Metric calculation engine."""

from __future__ import annotations

import pytest

from bsa.domain.enums import Aggregation, MetricDataType
from bsa.domain.metric_spec import parse_spec
from bsa.domain.metrics_engine import MetricCalculationError, MetricConfig, calculate


def config(aggregation: Aggregation, spec: dict, **kwargs: object) -> MetricConfig:
    return MetricConfig(
        key="test.metric",
        aggregation=aggregation,
        spec=parse_spec(spec),
        unit="mph",
        **kwargs,  # type: ignore[arg-type]
    )


PITCHES = [
    {"pitch_type": "FASTBALL", "velocity_mph": 86.0, "is_strike": True},
    {"pitch_type": "FASTBALL", "velocity_mph": 88.4, "is_strike": False},
    {"pitch_type": "FASTBALL", "velocity_mph": 87.1, "is_strike": True},
    {"pitch_type": "SLIDER", "velocity_mph": 78.2, "is_strike": True},
    {"pitch_type": "CURVEBALL", "velocity_mph": 73.9, "is_strike": None},
]


def test_max_respects_filters() -> None:
    result = calculate(
        config(
            Aggregation.MAX,
            {
                "field": "velocity_mph",
                "filters": [{"field": "pitch_type", "op": "eq", "value": "FASTBALL"}],
            },
        ),
        PITCHES,
    )

    assert result is not None
    assert result.value == 88.4
    # The slider and curveball are excluded from the sample as well as the
    # value -- they were never evidence about fastball velocity.
    assert result.sample_size == 3


def test_avg_is_computed_over_filtered_events_only() -> None:
    result = calculate(
        config(
            Aggregation.AVG,
            {
                "field": "velocity_mph",
                "filters": [{"field": "pitch_type", "op": "eq", "value": "FASTBALL"}],
                "round_to": 2,
            },
        ),
        PITCHES,
    )

    assert result is not None
    assert result.value == pytest.approx(87.17, abs=0.01)


def test_missing_readings_are_skipped_not_treated_as_zero() -> None:
    events = [
        {"velocity_mph": 90.0},
        {"velocity_mph": None},
        {"velocity_mph": 92.0},
        {},
    ]

    result = calculate(config(Aggregation.AVG, {"field": "velocity_mph"}), events)

    assert result is not None
    assert result.value == 91.0
    assert result.sample_size == 2


def test_out_of_range_values_are_discarded() -> None:
    """An impossible reading must never become a personal record."""
    events = [{"velocity_mph": 88.0}, {"velocity_mph": 268.0}, {"velocity_mph": 89.0}]

    result = calculate(
        config(Aggregation.MAX, {"field": "velocity_mph", "max_value": 110.0}), events
    )

    assert result is not None
    assert result.value == 89.0
    assert result.sample_size == 2


def test_below_minimum_sample_returns_none_not_zero() -> None:
    """ "No data" and "a value of zero" are different claims."""
    result = calculate(
        config(Aggregation.MAX, {"field": "velocity_mph"}, min_sample_size=5),
        [{"velocity_mph": 90.0}],
    )

    assert result is None


def test_count_counts_qualifying_events() -> None:
    result = calculate(
        config(
            Aggregation.COUNT,
            {"filters": [{"field": "pitch_type", "op": "eq", "value": "FASTBALL"}]},
        ),
        PITCHES,
    )

    assert result is not None
    assert result.value == 3.0


def test_rate_excludes_events_with_no_verdict() -> None:
    """A pitch put in play is neither a strike nor a ball for this metric."""
    result = calculate(
        config(
            Aggregation.RATE,
            {
                "filters": [{"field": "is_strike", "op": "is_not_null"}],
                "numerator_filters": [{"field": "is_strike", "op": "is_true"}],
            },
            min_sample_size=1,
        ),
        PITCHES,
    )

    assert result is not None
    # 3 strikes out of the 4 pitches with a verdict; the None is excluded.
    assert result.value == 75.0
    assert result.sample_size == 4


def test_integer_metrics_are_whole_numbers() -> None:
    result = calculate(
        config(
            Aggregation.AVG,
            {"field": "velocity_mph"},
            data_type=MetricDataType.INTEGER,
        ),
        [{"velocity_mph": 10.0}, {"velocity_mph": 11.0}, {"velocity_mph": 12.4}],
    )

    assert result is not None
    assert result.value == 11.0


def test_context_dimensions_are_echoed_for_labelling() -> None:
    result = calculate(
        config(
            Aggregation.MAX,
            {"field": "velocity_mph", "context_dimensions": {"pitch_type": "FASTBALL"}},
        ),
        PITCHES,
    )

    assert result is not None
    assert result.context["pitch_type"] == "FASTBALL"


def test_misconfigured_metric_fails_loudly() -> None:
    with pytest.raises(MetricCalculationError, match="no field"):
        calculate(config(Aggregation.MAX, {}), PITCHES)

    with pytest.raises(MetricCalculationError, match="numerator"):
        calculate(config(Aggregation.RATE, {}), PITCHES)


def test_training_context_is_filterable() -> None:
    """Phase 8 groundwork: drill-level filtering already works."""
    events = [
        {"velocity_mph": 88.0, "ctx.drill": "Velo Block"},
        {"velocity_mph": 84.0, "ctx.drill": "Command Ladder"},
    ]

    result = calculate(
        config(
            Aggregation.MAX,
            {
                "field": "velocity_mph",
                "filters": [{"field": "ctx.drill", "op": "eq", "value": "Velo Block"}],
            },
        ),
        events,
    )

    assert result is not None
    assert result.value == 88.0
    assert result.sample_size == 1
