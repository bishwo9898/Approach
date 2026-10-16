"""Hitting performance over a period, rather than in a single session.

The athlete's page answers "how did that session go". A coach also needs "how
is this going", which is the same question asked of a window of time. That is
what this module builds.

It deliberately adds no new metrics. `hitting_report.build_report` is a pure
function over a list of pitches, so the summary for a month is literally the
same report built from every pitch in that month. One definition of "best exit
velocity", used everywhere, is worth more than a second one that drifts.

What a period genuinely adds is three things:

* **Movement.** A single number for a month hides whether it was rising or
  falling, so the window is also cut into buckets -- days, weeks or months
  depending on how long it is.
* **A baseline.** "87 mph" means little; "87 mph, up 1.4 from the previous
  thirty days" is a coaching point. The comparison window is always the same
  length as the one it is compared against, which `preceding_window` enforces.
* **An honest account of how little is known.** One session in a window is a
  measurement, not a trend, and this module says which it has rather than
  drawing a confident line through a single point.

The last of those is the reason empty buckets are generated at all. A week with
no session must appear as a gap. Dropping it would silently redraw the x-axis
and make an inconsistent athlete look like a consistent one; filling it with
zero would be worse, because zero is a measurement and "did not bat" is not.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum

from bsa.domain.analytics import Comparison, DateWindow, TimeRange
from bsa.domain.hitting_report import FacedPitch, HittingReport, build_report

#: Below this many *populated buckets* a window is a measurement, not a trend.
#:
#: Counted in buckets rather than sessions on purpose: two sessions in the same
#: week aggregate into one point, and one point is not a line no matter how
#: many sessions produced it.
MIN_BUCKETS_FOR_A_TREND = 2


class Grain(StrEnum):
    """How a window is cut up for the trend."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"

    @property
    def label(self) -> str:
        return {Grain.DAY: "by day", Grain.WEEK: "by week", Grain.MONTH: "by month"}[self]


def grain_for(time_range: TimeRange) -> Grain:
    """The bucket size a window is read at.

    Derived rather than chosen by the viewer, because the useful answer is a
    function of the window: thirty daily buckets is mostly empty space for an
    athlete who trains twice a week, and twelve monthly buckets says nothing
    about the last fortnight. One control, no wrong combinations.
    """
    return {
        TimeRange.TODAY: Grain.DAY,
        TimeRange.LAST_7: Grain.DAY,
        TimeRange.LAST_30: Grain.WEEK,
        TimeRange.LAST_90: Grain.WEEK,
        TimeRange.YEAR: Grain.MONTH,
        TimeRange.ALL_TIME: Grain.MONTH,
    }[time_range]


@dataclass(frozen=True, slots=True)
class SessionPitches:
    """One session the athlete batted in, and every pitch they saw in it."""

    session_id: object
    session_date: date
    pitches: list[FacedPitch]


@dataclass(frozen=True, slots=True)
class TrendBucket:
    """One point on the trend. Empty buckets are kept and say so.

    Every metric is None when `sessions` is zero. A caller rendering this must
    leave a gap rather than plot zero -- the athlete did not hit zero, they did
    not bat.
    """

    start: date
    end: date
    label: str
    sessions: int
    pitches_faced: int
    batted_balls: int
    best_exit_velocity_mph: float | None
    average_exit_velocity_mph: float | None
    sweet_spot_rate: float | None

    @property
    def is_empty(self) -> bool:
        return self.sessions == 0


@dataclass(frozen=True, slots=True)
class PeriodSummary:
    """Everything the period view shows, already decided."""

    time_range: TimeRange
    window: DateWindow
    grain: Grain

    sessions: int
    first_session: date | None
    last_session: date | None

    #: The same report the session view uses, over every pitch in the window.
    totals: HittingReport
    #: And over the equally-long window immediately before it.
    previous: HittingReport | None

    buckets: list[TrendBucket] = field(default_factory=list)

    @property
    def has_data(self) -> bool:
        return self.sessions > 0

    @property
    def populated_buckets(self) -> int:
        return sum(1 for bucket in self.buckets if not bucket.is_empty)

    @property
    def has_trend(self) -> bool:
        """Whether there is movement to show, as opposed to one measurement.

        A trend needs two points to join. Two sessions in one week are one
        point, so sessions are the wrong thing to count here.
        """
        return self.populated_buckets >= MIN_BUCKETS_FOR_A_TREND

    def comparison(self, metric: str) -> Comparison:
        """Current versus the preceding window, for one headline metric.

        Sample sizes travel with the values, because "up 3 mph" off two batted
        balls and off forty are not the same claim and must not render alike.
        """
        current = getattr(self.totals, metric, None)
        previous = getattr(self.previous, metric, None) if self.previous else None
        return Comparison(
            current=current,
            previous=previous,
            current_sample=self.totals.batted_balls,
            previous_sample=self.previous.batted_balls if self.previous else 0,
        )


# -- bucketing ---------------------------------------------------------------


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _next_month(day: date) -> date:
    year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return date(year, month, 1)


def bucket_start(day: date, grain: Grain) -> date:
    """The first day of the bucket `day` falls in."""
    if grain is Grain.DAY:
        return day
    if grain is Grain.WEEK:
        # ISO weeks start on Monday, which is also how a training week is
        # usually described out loud.
        return day - timedelta(days=day.weekday())
    return _month_start(day)


def _bucket_end(start: date, grain: Grain) -> date:
    if grain is Grain.DAY:
        return start
    if grain is Grain.WEEK:
        return start + timedelta(days=6)
    return start.replace(day=calendar.monthrange(start.year, start.month)[1])


def _advance(start: date, grain: Grain) -> date:
    if grain is Grain.DAY:
        return start + timedelta(days=1)
    if grain is Grain.WEEK:
        return start + timedelta(days=7)
    return _next_month(start)


def _label(start: date, grain: Grain) -> str:
    if grain is Grain.MONTH:
        return start.strftime("%b %Y")
    return start.strftime("%b %-d")


def bucket_spans(window: DateWindow, grain: Grain) -> list[tuple[date, date]]:
    """Every bucket covering the window, in order, including empty ones.

    The first and last are clipped to the window so a label never claims to
    cover days outside the period being shown.
    """
    spans: list[tuple[date, date]] = []
    cursor = bucket_start(window.start, grain)
    # A guard, not a limit anyone should reach: all-time at daily grain on a
    # corrupt earliest-date would otherwise loop for years of empty buckets.
    while cursor <= window.end and len(spans) < 400:
        end = _bucket_end(cursor, grain)
        spans.append((max(cursor, window.start), min(end, window.end)))
        cursor = _advance(cursor, grain)
    return spans


# -- summarizing -------------------------------------------------------------


def _bucket(span: tuple[date, date], sessions: list[SessionPitches], grain: Grain) -> TrendBucket:
    start, end = span
    inside = [s for s in sessions if start <= s.session_date <= end]
    pitches = [pitch for session in inside for pitch in session.pitches]
    report = build_report(pitches) if pitches else None

    return TrendBucket(
        start=start,
        end=end,
        label=_label(bucket_start(start, grain), grain),
        sessions=len(inside),
        pitches_faced=report.pitches_faced if report else 0,
        batted_balls=report.batted_balls if report else 0,
        best_exit_velocity_mph=report.best_exit_velocity_mph if report else None,
        average_exit_velocity_mph=report.average_exit_velocity_mph if report else None,
        sweet_spot_rate=report.sweet_spot_rate if report else None,
    )


def summarize_period(
    sessions: list[SessionPitches],
    previous_sessions: list[SessionPitches],
    *,
    time_range: TimeRange,
    window: DateWindow,
) -> PeriodSummary:
    """Build the period view from the sessions in it.

    Both lists are already windowed by the caller -- this function does no
    date filtering of its own beyond bucketing, so what it summarizes is
    exactly what it was handed.
    """
    grain = grain_for(time_range)
    in_window = sorted(sessions, key=lambda s: s.session_date)
    all_pitches = [pitch for session in in_window for pitch in session.pitches]
    previous_pitches = [pitch for session in previous_sessions for pitch in session.pitches]

    return PeriodSummary(
        time_range=time_range,
        window=window,
        grain=grain,
        sessions=len(in_window),
        first_session=in_window[0].session_date if in_window else None,
        last_session=in_window[-1].session_date if in_window else None,
        totals=build_report(all_pitches),
        previous=build_report(previous_pitches) if previous_pitches else None,
        buckets=[_bucket(span, in_window, grain) for span in bucket_spans(window, grain)],
    )
