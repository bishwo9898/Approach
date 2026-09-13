"""The selector stored in `MetricDefinition.spec`.

A deliberately small, closed vocabulary -- not a query language. It can express
"the maximum velocity_mph of pitches whose pitch_type is FASTBALL" and little
else, which is exactly the surface a coach-configurable metric needs. Anything
requiring real expressiveness should become a new aggregation with a name and a
test, not a more powerful DSL that nobody can reason about.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FilterOp(StrEnum):
    EQ = "eq"
    NEQ = "neq"
    IN = "in"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IS_TRUE = "is_true"
    IS_NOT_NULL = "is_not_null"


class MetricFilter(BaseModel):
    """One predicate applied to a normalized event."""

    model_config = ConfigDict(extra="forbid")

    field: str
    op: FilterOp
    value: Any = None

    def matches(self, event: dict[str, Any]) -> bool:
        actual = event.get(self.field)
        match self.op:
            case FilterOp.IS_NOT_NULL:
                return actual is not None
            case FilterOp.IS_TRUE:
                return actual is True
            case FilterOp.EQ:
                return bool(actual == self.value)
            case FilterOp.NEQ:
                return bool(actual != self.value)
            case FilterOp.IN:
                return actual in (self.value or [])
        # Ordered comparisons: a missing measurement is not a match. Treating
        # None as 0 here would silently drag averages down.
        if actual is None or self.value is None:
            return False
        match self.op:
            case FilterOp.GT:
                return bool(actual > self.value)
            case FilterOp.GTE:
                return bool(actual >= self.value)
            case FilterOp.LT:
                return bool(actual < self.value)
            case FilterOp.LTE:
                return bool(actual <= self.value)
        return False


class MetricSpec(BaseModel):
    """How to turn a bag of normalized events into one number."""

    model_config = ConfigDict(extra="forbid")

    #: Event attribute to aggregate. Omitted for COUNT, which counts rows.
    field: str | None = None

    #: Events that do not satisfy every filter are excluded from both the value
    #: and the sample size.
    filters: list[MetricFilter] = Field(default_factory=list)

    #: For RATE only: the numerator predicate, applied to events that already
    #: passed `filters`. Result is a percentage of the filtered population.
    numerator_filters: list[MetricFilter] = Field(default_factory=list)

    #: Dimensions echoed into MetricObservation.context so the UI can label a
    #: value ("Fastball only") without re-reading the spec.
    context_dimensions: dict[str, str] = Field(default_factory=dict)

    #: Physically implausible readings are dropped rather than allowed to
    #: become a personal record. A 132 mph "fastball" is a tracking artifact.
    min_value: float | None = None
    max_value: float | None = None

    #: Rounding applied to the final value only, never to inputs.
    round_to: int = 2

    def select(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [e for e in events if all(f.matches(e) for f in self.filters)]


def parse_spec(raw: dict[str, Any] | None) -> MetricSpec:
    """Validate a stored spec. Invalid specs fail loudly at calculation time."""
    return MetricSpec.model_validate(raw or {})


SpecSource = Literal["pitch", "hit"]
