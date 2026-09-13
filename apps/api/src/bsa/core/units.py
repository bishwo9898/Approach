"""Canonical units and the only place conversions are allowed to live.

Rule: a raw measurement is converted to its canonical unit exactly once, at the
vendor adapter boundary. Everything downstream -- storage, metrics, PRs, API,
UI -- speaks canonical units. No conversion may appear anywhere else.

A stored number without a declared unit is a bug, so `MetricDefinition.unit` is
NOT NULL and event columns carry their unit in the column name (`velocity_mph`).
"""

from __future__ import annotations

from enum import StrEnum


class Unit(StrEnum):
    """Canonical units. The value is what we display."""

    MPH = "mph"
    RPM = "rpm"
    INCHES = "in"
    DEGREES = "deg"
    FEET = "ft"
    COUNT = "count"
    PERCENT = "%"
    SECONDS = "s"


#: Conversion factors *into* the canonical unit, keyed by (from_unit, canonical).
#: Deliberately explicit rather than a general-purpose units library: the set of
#: conversions a TrackMan feed can require is small and we want every one of
#: them reviewed.
_FACTORS: dict[tuple[str, Unit], float] = {
    # velocity
    ("mph", Unit.MPH): 1.0,
    ("m/s", Unit.MPH): 2.2369362920544,
    ("km/h", Unit.MPH): 0.621371192237334,
    ("kph", Unit.MPH): 0.621371192237334,
    # spin
    ("rpm", Unit.RPM): 1.0,
    # movement / length
    ("in", Unit.INCHES): 1.0,
    ("inch", Unit.INCHES): 1.0,
    ("ft", Unit.INCHES): 12.0,
    ("cm", Unit.INCHES): 0.393700787401575,
    ("m", Unit.INCHES): 39.3700787401575,
    # distance
    ("ft", Unit.FEET): 1.0,
    ("m", Unit.FEET): 3.28083989501312,
    ("yd", Unit.FEET): 3.0,
    # angles
    ("deg", Unit.DEGREES): 1.0,
    ("degrees", Unit.DEGREES): 1.0,
    # dimensionless
    ("count", Unit.COUNT): 1.0,
    ("%", Unit.PERCENT): 1.0,
    ("s", Unit.SECONDS): 1.0,
    ("ms", Unit.SECONDS): 0.001,
}


class UnitConversionError(ValueError):
    """Raised when a conversion is not explicitly supported.

    Guessing a conversion is worse than failing the import: a silently wrong
    factor produces plausible-looking numbers that nobody catches.
    """


def convert(value: float, from_unit: str, to_unit: Unit) -> float:
    """Convert `value` from `from_unit` into the canonical `to_unit`."""
    key = (from_unit.strip().lower(), to_unit)
    factor = _FACTORS.get(key)
    if factor is None:
        raise UnitConversionError(f"no supported conversion from {from_unit!r} to {to_unit.value}")
    return value * factor


def supports(from_unit: str, to_unit: Unit) -> bool:
    return (from_unit.strip().lower(), to_unit) in _FACTORS


def format_value(value: float, unit: Unit, decimals: int | None = None) -> str:
    """Render a measurement for display, always with its unit attached."""
    if decimals is None:
        decimals = 0 if unit in (Unit.COUNT, Unit.RPM) else 1
    if unit is Unit.PERCENT:
        return f"{value:.{decimals}f}%"
    if unit is Unit.COUNT:
        return f"{value:.{decimals}f}"
    return f"{value:.{decimals}f} {unit.value}"
