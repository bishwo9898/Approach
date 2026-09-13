"""The metric engine: normalized events in, one number out.

Pure functions over plain dicts. No SQLAlchemy, no session, no I/O -- which is
what lets the whole calculation be tested without a database, and what lets the
same code serve ingestion, backfills and ad-hoc recalculation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bsa.domain.enums import Aggregation, MetricDataType
from bsa.domain.metric_spec import MetricSpec, parse_spec


@dataclass(frozen=True, slots=True)
class MetricConfig:
    """The subset of a MetricDefinition the engine needs.

    A snapshot rather than the ORM object, so the engine cannot accidentally
    depend on lazy-loaded relationships or a live session.
    """

    key: str
    aggregation: Aggregation
    spec: MetricSpec
    unit: str
    data_type: MetricDataType = MetricDataType.FLOAT
    min_sample_size: int = 1
    calculation_version: int = 1

    @classmethod
    def from_definition(cls, definition: Any) -> MetricConfig:
        return cls(
            key=definition.key,
            aggregation=definition.aggregation,
            spec=parse_spec(definition.spec),
            unit=definition.unit,
            data_type=definition.data_type,
            min_sample_size=definition.min_sample_size,
            calculation_version=definition.calculation_version,
        )


@dataclass(frozen=True, slots=True)
class MetricResult:
    """A calculated value and the evidence behind it."""

    value: float
    sample_size: int
    context: dict[str, Any]


class MetricCalculationError(ValueError):
    """A metric is configured in a way that cannot be evaluated."""


def _numeric_values(events: list[dict[str, Any]], field: str) -> list[float]:
    """Extract usable numbers, dropping missing and non-numeric readings.

    Missing is not zero. A pitch with no spin reading contributes nothing to
    average spin rather than dragging it toward zero.
    """
    out: list[float] = []
    for event in events:
        raw = event.get(field)
        if raw is None or isinstance(raw, bool):
            continue
        if isinstance(raw, int | float):
            out.append(float(raw))
    return out


def calculate(config: MetricConfig, events: list[dict[str, Any]]) -> MetricResult | None:
    """Evaluate one metric over one scope.

    Returns None -- rather than 0 -- when the metric does not apply: no
    qualifying events, or fewer than `min_sample_size`. "No data" and "a value of
    zero" are different claims and must never be conflated.
    """
    spec = config.spec
    qualifying = spec.select(events)

    if config.aggregation is Aggregation.COUNT:
        sample = len(qualifying)
        if sample < config.min_sample_size:
            return None
        return MetricResult(float(sample), sample, dict(spec.context_dimensions))

    if config.aggregation is Aggregation.RATE:
        sample = len(qualifying)
        if sample < config.min_sample_size:
            return None
        if not spec.numerator_filters:
            raise MetricCalculationError(
                f"metric {config.key!r} uses RATE but defines no numerator_filters"
            )
        hits = sum(1 for e in qualifying if all(f.matches(e) for f in spec.numerator_filters))
        value = round(100.0 * hits / sample, spec.round_to)
        return MetricResult(value, sample, {**spec.context_dimensions, "numerator": hits})

    if not spec.field:
        raise MetricCalculationError(
            f"metric {config.key!r} uses {config.aggregation} but defines no field"
        )

    values = _numeric_values(qualifying, spec.field)

    # Range guards run after extraction so an out-of-range reading is excluded
    # from the sample size too -- it was never credible evidence.
    if spec.min_value is not None:
        values = [v for v in values if v >= spec.min_value]
    if spec.max_value is not None:
        values = [v for v in values if v <= spec.max_value]

    sample = len(values)
    if sample == 0 or sample < config.min_sample_size:
        return None

    match config.aggregation:
        case Aggregation.MAX:
            value = max(values)
        case Aggregation.MIN:
            value = min(values)
        case Aggregation.AVG:
            value = sum(values) / sample
        case Aggregation.SUM:
            value = sum(values)
        case _:  # pragma: no cover -- exhausted above
            raise MetricCalculationError(f"unsupported aggregation {config.aggregation}")

    value = round(value, spec.round_to)
    if config.data_type is MetricDataType.INTEGER:
        value = float(round(value))

    return MetricResult(value, sample, dict(spec.context_dimensions))


def calculate_many(
    configs: list[MetricConfig],
    events_by_source: dict[str, list[dict[str, Any]]],
    source_of: dict[str, str],
) -> dict[str, MetricResult]:
    """Evaluate several metrics over one scope.

    `source_of` maps metric key -> event source key, so pitching metrics never
    see batted balls and vice versa.
    """
    results: dict[str, MetricResult] = {}
    for config in configs:
        events = events_by_source.get(source_of[config.key], [])
        result = calculate(config, events)
        if result is not None:
            results[config.key] = result
    return results
