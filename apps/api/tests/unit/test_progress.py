"""Hitting performance over a window of time.

The arithmetic is `hitting_report`'s and is tested there. What is tested here
is the windowing, the bucketing, and above all what the summary says when it
does not have enough to say anything -- which is the normal case for a facility
that has just started collecting data.
"""

from __future__ import annotations

from datetime import date

import pytest

from bsa.domain.analytics import DateWindow, TimeRange
from bsa.domain.hitting_report import FacedPitch
from bsa.domain.progress import (
    MIN_BUCKETS_FOR_A_TREND,
    Grain,
    SessionPitches,
    bucket_spans,
    bucket_start,
    grain_for,
    summarize_period,
)


def batted(exit_velocity: float, launch_angle: float = 18.0) -> FacedPitch:
    return FacedPitch(
        event_number=1,
        pitch_velocity_mph=75.0,
        exit_velocity_mph=exit_velocity,
        launch_angle_deg=launch_angle,
    )


def unmeasured() -> FacedPitch:
    """A recorded pitch with no batted-ball reading."""
    return FacedPitch(event_number=1, pitch_velocity_mph=75.0)


def session(day: date, *pitches: FacedPitch) -> SessionPitches:
    return SessionPitches(session_id=day.isoformat(), session_date=day, pitches=list(pitches))


def summarize(  # type: ignore[no-untyped-def]
    sessions: list[SessionPitches],
    previous: list[SessionPitches] | None = None,
    *,
    time_range: TimeRange = TimeRange.LAST_30,
    window: DateWindow | None = None,
):
    return summarize_period(
        sessions,
        previous or [],
        time_range=time_range,
        window=window or DateWindow(date(2026, 9, 1), date(2026, 9, 30)),
    )


# -- grain -------------------------------------------------------------------


class TestGrain:
    """One control. The viewer picks a window; the bucket size follows.

    Thirty daily buckets is mostly empty space for an athlete who trains twice
    a week, and twelve monthly buckets says nothing about the last fortnight.
    """

    @pytest.mark.parametrize(
        ("time_range", "expected"),
        [
            (TimeRange.TODAY, Grain.DAY),
            (TimeRange.LAST_7, Grain.DAY),
            (TimeRange.LAST_30, Grain.WEEK),
            (TimeRange.LAST_90, Grain.WEEK),
            (TimeRange.YEAR, Grain.MONTH),
            (TimeRange.ALL_TIME, Grain.MONTH),
        ],
    )
    def test_each_window_reads_at_a_sensible_size(self, time_range, expected) -> None:  # type: ignore[no-untyped-def]
        assert grain_for(time_range) is expected

    def test_every_window_has_one(self) -> None:
        """A new TimeRange must not reach the UI without a decision here."""
        for time_range in TimeRange:
            assert isinstance(grain_for(time_range), Grain)


class TestBucketStart:
    def test_a_day_is_its_own_bucket(self) -> None:
        assert bucket_start(date(2026, 9, 17), Grain.DAY) == date(2026, 9, 17)

    def test_a_week_starts_on_monday(self) -> None:
        """Thursday the 17th belongs to the week beginning Monday the 14th."""
        assert bucket_start(date(2026, 9, 17), Grain.WEEK) == date(2026, 9, 14)

    def test_a_monday_is_its_own_week_start(self) -> None:
        assert bucket_start(date(2026, 9, 14), Grain.WEEK) == date(2026, 9, 14)

    def test_a_month_starts_on_the_first(self) -> None:
        assert bucket_start(date(2026, 9, 17), Grain.MONTH) == date(2026, 9, 1)


class TestBucketSpans:
    def test_buckets_cover_the_whole_window(self) -> None:
        spans = bucket_spans(DateWindow(date(2026, 9, 1), date(2026, 9, 30)), Grain.WEEK)
        assert spans[0][0] == date(2026, 9, 1)
        assert spans[-1][1] == date(2026, 9, 30)

    def test_the_edges_are_clipped_to_the_window(self) -> None:
        """A label must never claim to cover days outside the period shown."""
        spans = bucket_spans(DateWindow(date(2026, 9, 3), date(2026, 9, 20)), Grain.WEEK)
        assert spans[0] == (date(2026, 9, 3), date(2026, 9, 6))
        assert spans[-1] == (date(2026, 9, 14), date(2026, 9, 20))

    def test_daily_buckets_are_one_per_day(self) -> None:
        spans = bucket_spans(DateWindow(date(2026, 9, 1), date(2026, 9, 7)), Grain.DAY)
        assert len(spans) == 7

    def test_monthly_buckets_handle_a_year_boundary(self) -> None:
        spans = bucket_spans(DateWindow(date(2026, 11, 15), date(2027, 2, 3)), Grain.MONTH)
        assert [s[0] for s in spans] == [
            date(2026, 11, 15),
            date(2026, 12, 1),
            date(2027, 1, 1),
            date(2027, 2, 1),
        ]

    def test_a_single_day_window_yields_one_bucket(self) -> None:
        spans = bucket_spans(DateWindow(date(2026, 9, 7), date(2026, 9, 7)), Grain.DAY)
        assert spans == [(date(2026, 9, 7), date(2026, 9, 7))]


# -- the summary -------------------------------------------------------------


class TestTotals:
    def test_the_window_total_is_the_session_report_over_every_pitch(self) -> None:
        """Deliberately the same definition, not a second one that can drift."""
        summary = summarize(
            [
                session(date(2026, 9, 3), batted(90.0), unmeasured()),
                session(date(2026, 9, 17), batted(95.0), batted(80.0)),
            ]
        )
        assert summary.totals.batted_balls == 3
        assert summary.totals.best_exit_velocity_mph == 95.0
        assert summary.totals.pitches_faced == 4
        assert summary.sessions == 2

    def test_it_reports_the_span_of_real_sessions_not_the_window(self) -> None:
        """ "3 sessions, Sep 3 to Sep 17" is the honest caption, not the window
        edges, which say nothing about when the athlete actually batted."""
        summary = summarize(
            [session(date(2026, 9, 3), batted(90.0)), session(date(2026, 9, 17), batted(92.0))]
        )
        assert summary.first_session == date(2026, 9, 3)
        assert summary.last_session == date(2026, 9, 17)


class TestNotEnoughData:
    """The normal case for a facility that has just started.

    The view must exist and be honest rather than be hidden or invented.
    """

    def test_an_empty_window_reports_no_data(self) -> None:
        summary = summarize([])
        assert summary.sessions == 0
        assert not summary.has_data
        assert not summary.has_trend
        assert summary.first_session is None
        assert summary.totals.batted_balls == 0

    def test_an_empty_window_invents_no_measurements(self) -> None:
        """Zero batted balls is not a zero exit velocity."""
        summary = summarize([])
        assert summary.totals.best_exit_velocity_mph is None
        assert summary.totals.average_exit_velocity_mph is None
        assert summary.totals.sweet_spot_rate is None

    def test_one_session_is_a_measurement_not_a_trend(self) -> None:
        summary = summarize([session(date(2026, 9, 3), batted(90.0))])
        assert summary.has_data
        assert not summary.has_trend
        assert summary.totals.best_exit_velocity_mph == 90.0

    def test_two_sessions_in_different_buckets_are_a_trend(self) -> None:
        summary = summarize(
            [session(date(2026, 9, 3), batted(90.0)), session(date(2026, 9, 17), batted(92.0))]
        )
        assert summary.has_trend
        assert summary.populated_buckets == 2
        assert MIN_BUCKETS_FOR_A_TREND == 2

    def test_two_sessions_in_one_bucket_are_still_one_point(self) -> None:
        """A trend needs two points to join, and these aggregate into one."""
        summary = summarize(
            [session(date(2026, 9, 1), batted(90.0)), session(date(2026, 9, 2), batted(96.0))]
        )
        assert summary.sessions == 2
        assert summary.populated_buckets == 1
        assert not summary.has_trend


class TestBuckets:
    @pytest.fixture
    def summary(self):  # type: ignore[no-untyped-def]
        # Sessions in week 1 and week 3; week 2 and week 4 are blank.
        return summarize(
            [
                session(date(2026, 9, 2), batted(90.0), batted(88.0)),
                session(date(2026, 9, 16), batted(95.0)),
            ]
        )

    def test_a_week_with_no_session_is_kept_as_a_gap(self, summary) -> None:  # type: ignore[no-untyped-def]
        """Dropping it would redraw the axis and make an inconsistent athlete
        look consistent."""
        assert len(summary.buckets) == 5
        assert [b.sessions for b in summary.buckets] == [1, 0, 1, 0, 0]

    def test_an_empty_bucket_carries_no_measurements(self, summary) -> None:  # type: ignore[no-untyped-def]
        """Zero would be a measurement. The athlete did not bat."""
        blank = summary.buckets[1]
        assert blank.is_empty
        assert blank.best_exit_velocity_mph is None
        assert blank.average_exit_velocity_mph is None
        assert blank.sweet_spot_rate is None
        assert blank.batted_balls == 0

    def test_a_populated_bucket_summarizes_only_its_own_sessions(self, summary) -> None:  # type: ignore[no-untyped-def]
        first = summary.buckets[0]
        assert first.sessions == 1
        assert first.batted_balls == 2
        assert first.best_exit_velocity_mph == 90.0
        assert first.average_exit_velocity_mph == 89.0

    def test_buckets_are_in_calendar_order(self, summary) -> None:  # type: ignore[no-untyped-def]
        starts = [b.start for b in summary.buckets]
        assert starts == sorted(starts)

    def test_two_sessions_in_one_bucket_are_combined(self) -> None:
        summary = summarize(
            [
                session(date(2026, 9, 1), batted(90.0)),
                session(date(2026, 9, 2), batted(96.0)),
            ]
        )
        assert summary.buckets[0].sessions == 2
        assert summary.buckets[0].best_exit_velocity_mph == 96.0


class TestComparison:
    def test_it_compares_against_the_preceding_window(self) -> None:
        summary = summarize(
            [session(date(2026, 9, 17), batted(95.0))],
            [session(date(2026, 8, 17), batted(90.0))],
        )
        comparison = summary.comparison("best_exit_velocity_mph")
        assert comparison.current == 95.0
        assert comparison.previous == 90.0
        assert comparison.delta == 5.0

    def test_sample_sizes_travel_with_the_values(self) -> None:
        """ "Up 3 mph" off two batted balls and off forty are different claims."""
        summary = summarize(
            [session(date(2026, 9, 17), batted(95.0), batted(80.0))],
            [session(date(2026, 8, 17), batted(90.0))],
        )
        comparison = summary.comparison("best_exit_velocity_mph")
        assert comparison.current_sample == 2
        assert comparison.previous_sample == 1

    def test_no_previous_window_means_no_delta_rather_than_a_zero(self) -> None:
        """A first month has not improved by zero; it has nothing to compare."""
        summary = summarize([session(date(2026, 9, 17), batted(95.0))])
        comparison = summary.comparison("best_exit_velocity_mph")
        assert summary.previous is None
        assert comparison.previous is None
        assert comparison.delta is None
        assert comparison.percent_change is None


def test_all_time_uses_monthly_buckets_without_running_away() -> None:
    """A long all-time window must stay bounded rather than emit one bucket
    per month since the epoch."""
    summary = summarize(
        [session(date(2024, 3, 2), batted(90.0))],
        time_range=TimeRange.ALL_TIME,
        window=DateWindow(date(2024, 1, 1), date(2026, 12, 31)),
    )
    assert summary.grain is Grain.MONTH
    assert len(summary.buckets) == 36
