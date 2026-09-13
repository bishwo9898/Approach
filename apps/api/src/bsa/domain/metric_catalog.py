"""The starter metric set.

These are *seed data*, not code. They are written into `metric_definitions` on
first setup and are expected to change once the coach reviews them -- which is
the entire point of storing metrics as rows. Nothing in the engine, the API or
the dashboard knows any of these keys by name.

Record direction is chosen conservatively. Where "better" is genuinely
coach- and athlete-dependent (spin rate is the clear case), the metric is
tracked and charted but produces no personal record, rather than asserting a
direction the facility has not agreed to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bsa.core.units import Unit
from bsa.domain.enums import (
    Aggregation,
    EventSource,
    MetricCategory,
    MetricDataType,
    RecordDirection,
)
from bsa.domain.vocabulary import PitchType

_FASTBALL_FILTER = [{"field": "pitch_type", "op": "eq", "value": PitchType.FASTBALL.value}]
_FASTBALL_CONTEXT = {"pitch_type": PitchType.FASTBALL.value}


@dataclass(frozen=True, slots=True)
class MetricSeed:
    key: str
    display_name: str
    category: MetricCategory
    event_source: EventSource
    aggregation: Aggregation
    unit: Unit
    spec: dict[str, Any]
    record_direction: RecordDirection = RecordDirection.NONE
    data_type: MetricDataType = MetricDataType.FLOAT
    min_sample_size: int = 1
    display_precision: int = 1
    is_headline: bool = False
    sort_order: int = 100
    description: str = ""


STARTER_METRICS: list[MetricSeed] = [
    MetricSeed(
        key="pitch.fastball.max_velocity",
        display_name="Fastball Max Velocity",
        description=(
            "Highest fastball release velocity in the scope. Requires at least three "
            "tracked fastballs so a single mis-tracked pitch cannot set a record."
        ),
        category=MetricCategory.PITCHING,
        event_source=EventSource.PITCH,
        aggregation=Aggregation.MAX,
        unit=Unit.MPH,
        record_direction=RecordDirection.HIGHER_IS_BETTER,
        min_sample_size=3,
        is_headline=True,
        sort_order=10,
        spec={
            "field": "velocity_mph",
            "filters": _FASTBALL_FILTER,
            "context_dimensions": _FASTBALL_CONTEXT,
            "min_value": 40.0,
            "max_value": 105.0,
            "round_to": 1,
        },
    ),
    MetricSeed(
        key="pitch.fastball.avg_velocity",
        display_name="Fastball Average Velocity",
        description=(
            "Mean fastball release velocity. More stable than the maximum and the "
            "better indicator of a change in stuff."
        ),
        category=MetricCategory.PITCHING,
        event_source=EventSource.PITCH,
        aggregation=Aggregation.AVG,
        unit=Unit.MPH,
        record_direction=RecordDirection.HIGHER_IS_BETTER,
        min_sample_size=5,
        is_headline=True,
        sort_order=20,
        spec={
            "field": "velocity_mph",
            "filters": _FASTBALL_FILTER,
            "context_dimensions": _FASTBALL_CONTEXT,
            "min_value": 40.0,
            "max_value": 105.0,
            "round_to": 1,
        },
    ),
    MetricSeed(
        key="pitch.fastball.avg_spin_rate",
        display_name="Fastball Average Spin Rate",
        description=(
            "Mean fastball spin rate. Tracked but deliberately not a personal record: "
            "whether higher spin is better depends on the pitch shape a coach wants."
        ),
        category=MetricCategory.PITCHING,
        event_source=EventSource.PITCH,
        aggregation=Aggregation.AVG,
        unit=Unit.RPM,
        record_direction=RecordDirection.NONE,
        min_sample_size=5,
        display_precision=0,
        sort_order=30,
        spec={
            "field": "spin_rate_rpm",
            "filters": _FASTBALL_FILTER,
            "context_dimensions": _FASTBALL_CONTEXT,
            "min_value": 500.0,
            "max_value": 3500.0,
            "round_to": 0,
        },
    ),
    MetricSeed(
        key="pitch.strike_percentage",
        display_name="Strike Percentage",
        description=(
            "Share of tracked pitches called or swung on for a strike, fouls included. "
            "Pitches put in play or hit by pitch are excluded from both sides."
        ),
        category=MetricCategory.PITCHING,
        event_source=EventSource.PITCH,
        aggregation=Aggregation.RATE,
        unit=Unit.PERCENT,
        record_direction=RecordDirection.HIGHER_IS_BETTER,
        min_sample_size=10,
        sort_order=40,
        spec={
            "filters": [{"field": "is_strike", "op": "is_not_null"}],
            "numerator_filters": [{"field": "is_strike", "op": "is_true"}],
            "round_to": 1,
        },
    ),
    MetricSeed(
        key="pitch.count",
        display_name="Pitch Count",
        description=(
            "Tracked pitches thrown. Training volume, not an achievement -- it produces "
            "no personal record."
        ),
        category=MetricCategory.PITCHING,
        event_source=EventSource.PITCH,
        aggregation=Aggregation.COUNT,
        unit=Unit.COUNT,
        record_direction=RecordDirection.NONE,
        data_type=MetricDataType.INTEGER,
        display_precision=0,
        sort_order=50,
        spec={"round_to": 0},
    ),
    MetricSeed(
        key="hit.max_exit_velocity",
        display_name="Max Exit Velocity",
        description="Hardest tracked batted ball in the scope.",
        category=MetricCategory.HITTING,
        event_source=EventSource.HIT,
        aggregation=Aggregation.MAX,
        unit=Unit.MPH,
        record_direction=RecordDirection.HIGHER_IS_BETTER,
        min_sample_size=3,
        is_headline=True,
        sort_order=60,
        spec={
            "field": "exit_velocity_mph",
            "min_value": 30.0,
            "max_value": 125.0,
            "round_to": 1,
        },
    ),
    MetricSeed(
        key="hit.avg_exit_velocity",
        display_name="Average Exit Velocity",
        description="Mean exit velocity across tracked batted balls.",
        category=MetricCategory.HITTING,
        event_source=EventSource.HIT,
        aggregation=Aggregation.AVG,
        unit=Unit.MPH,
        record_direction=RecordDirection.HIGHER_IS_BETTER,
        min_sample_size=5,
        is_headline=True,
        sort_order=70,
        spec={
            "field": "exit_velocity_mph",
            "min_value": 30.0,
            "max_value": 125.0,
            "round_to": 1,
        },
    ),
    MetricSeed(
        key="hit.max_distance",
        display_name="Max Distance",
        description="Longest tracked batted ball.",
        category=MetricCategory.HITTING,
        event_source=EventSource.HIT,
        aggregation=Aggregation.MAX,
        unit=Unit.FEET,
        record_direction=RecordDirection.HIGHER_IS_BETTER,
        min_sample_size=3,
        display_precision=0,
        sort_order=80,
        spec={"field": "distance_ft", "min_value": 0.0, "max_value": 550.0, "round_to": 0},
    ),
    MetricSeed(
        key="hit.tracked_batted_balls",
        display_name="Tracked Batted Balls",
        description="Batted balls measured. Training volume, not an achievement.",
        category=MetricCategory.HITTING,
        event_source=EventSource.HIT,
        aggregation=Aggregation.COUNT,
        unit=Unit.COUNT,
        record_direction=RecordDirection.NONE,
        data_type=MetricDataType.INTEGER,
        display_precision=0,
        sort_order=90,
        spec={"round_to": 0},
    ),
]


@dataclass(frozen=True, slots=True)
class FuturesMappingSeed:
    """Which metrics the coach currently re-types into The Futures App.

    Field labels are the facility's own naming as described to us. They are not
    read from any Futures API -- no such access is confirmed.
    """

    metric_key: str
    destination_field: str
    destination_unit: Unit | None = None
    destination_precision: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


STARTER_FUTURES_MAPPINGS: list[FuturesMappingSeed] = [
    FuturesMappingSeed("pitch.fastball.max_velocity", "Fastball Velocity", Unit.MPH, 1),
    FuturesMappingSeed("hit.max_exit_velocity", "Exit Velocity", Unit.MPH, 1),
    FuturesMappingSeed("hit.max_distance", "Max Distance", Unit.FEET, 0),
]
