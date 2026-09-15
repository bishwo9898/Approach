"""Trend arithmetic.

Small on purpose. The product claim is "our application generates insight", and
the insight a coach actually asked for is: what is it now, how has it moved, and
is it a record. That is three numbers, not a statistics package.

Nothing here interprets a change. A velocity drop is reported as a change in
velocity; this system does not make medical or injury claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum


class TimeRange(StrEnum):
    """Windows the dashboards offer."""

    TODAY = "today"
    LAST_7 = "7d"
    LAST_30 = "30d"
    LAST_90 = "90d"
    YEAR = "1y"
    ALL_TIME = "all"

    @property
    def days(self) -> int | None:
        """Window length, or None for all-time."""
        return {
            TimeRange.TODAY: 1,
            TimeRange.LAST_7: 7,
            TimeRange.LAST_30: 30,
            TimeRange.LAST_90: 90,
            TimeRange.YEAR: 365,
            TimeRange.ALL_TIME: None,
        }[self]


@dataclass(frozen=True, slots=True)
class DateWindow:
    """Inclusive on both ends -- these are calendar days, not timestamps."""

    start: date
    end: date

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end


def window_for(time_range: TimeRange, today: date, earliest: date | None = None) -> DateWindow:
    days = time_range.days
    if days is None:
        return DateWindow(earliest or date(1970, 1, 1), today)
    return DateWindow(today - timedelta(days=days - 1), today)


def preceding_window(window: DateWindow) -> DateWindow:
    """The equally-long window immediately before `window`.

    "Last 30 days vs the 30 before that" only means something if both windows
    are the same length, so it is derived rather than passed in.
    """
    length = (window.end - window.start).days + 1
    end = window.start - timedelta(days=1)
    return DateWindow(end - timedelta(days=length - 1), end)


@dataclass(frozen=True, slots=True)
class Comparison:
    """A value alongside what it is being compared against."""

    current: float | None
    previous: float | None
    current_sample: int = 0
    previous_sample: int = 0
    current_source_status: str | None = None
    previous_source_status: str | None = None

    @property
    def delta(self) -> float | None:
        if self.current is None or self.previous is None:
            return None
        return round(self.current - self.previous, 4)

    @property
    def percent_change(self) -> float | None:
        """Omitted when the baseline is zero -- an infinite percentage is noise."""
        if self.current is None or self.previous is None or self.previous == 0:
            return None
        return round(100.0 * (self.current - self.previous) / abs(self.previous), 2)
