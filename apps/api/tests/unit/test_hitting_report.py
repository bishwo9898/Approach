"""The session report.

The governing rule, and the reason this module was rewritten: **nothing here
may count something TrackMan did not measure.** The export reports a pitch and
its movement, and, when the radar read a batted ball, an exit speed and a
launch angle. It does not report swings, takes or misses, so neither does this.
"""

from __future__ import annotations

import pytest

from bsa.domain.hitting_report import (
    LINE_DRIVE_MAX_DEG,
    LINE_DRIVE_MIN_DEG,
    MIN_BATTED_BALLS_FOR_A_CLAIM,
    FacedPitch,
    InsightKind,
    build_report,
)


def batted(exit_velocity: float, launch_angle: float, pitch: float = 75.0) -> FacedPitch:
    return FacedPitch(
        event_number=1,
        pitch_velocity_mph=pitch,
        exit_velocity_mph=exit_velocity,
        launch_angle_deg=launch_angle,
    )


def unmeasured(pitch: float = 75.0) -> FacedPitch:
    """A recorded pitch with no batted-ball reading.

    Taken, fouled, missed, or simply not picked up by the radar -- the export
    does not say which, and nothing in the report may assume.
    """
    return FacedPitch(event_number=1, pitch_velocity_mph=pitch)


class TestWhatIsCounted:
    def test_a_batted_ball_is_one_with_a_measured_exit_speed(self) -> None:
        report = build_report([batted(90.0, 15.0), unmeasured(), unmeasured()])
        assert report.batted_balls == 1
        assert report.pitches_faced == 3

    def test_pitches_faced_counts_every_recorded_pitch(self) -> None:
        """Not swings. The hitter faced them; what they did is unknown."""
        report = build_report([unmeasured() for _ in range(10)])
        assert report.pitches_faced == 10
        assert report.batted_balls == 0

    def test_an_empty_session_measures_nothing_rather_than_zero(self) -> None:
        report = build_report([])
        assert report.batted_balls == 0
        assert report.best_exit_velocity_mph is None
        assert report.average_exit_velocity_mph is None
        assert report.sweet_spot_rate is None
        assert report.measured_rate is None


class TestNoSwingArithmetic:
    """The regression this rewrite exists to prevent.

    A coach was shown "13 of your 34 swings missed". TrackMan does not track
    that; it came from reading the export's marker shapes as swing outcomes.
    """

    @pytest.mark.parametrize(
        "attribute", ["swings", "whiffs", "whiff_rate", "taken", "swing_rate", "groups"]
    )
    def test_the_report_exposes_no_swing_derived_quantity(self, attribute: str) -> None:
        report = build_report([batted(90.0, 15.0), unmeasured()])
        assert not hasattr(report, attribute), (
            f"{attribute} is back; the export does not support it"
        )

    def test_a_faced_pitch_carries_no_swing_result(self) -> None:
        assert not hasattr(FacedPitch(event_number=1), "swing_result")
        assert not hasattr(FacedPitch(event_number=1), "swung")

    def test_no_insight_mentions_a_swing_being_missed(self) -> None:
        report = build_report([batted(90.0, 15.0)] + [unmeasured() for _ in range(30)])
        wording = " ".join(i.headline + " " + i.detail for i in report.insights).lower()
        for banned in ("missed", "whiff", "swings missed", "took"):
            assert banned not in wording, f"insight claims {banned!r} from unmeasured data"


class TestMeasuredRate:
    def test_it_is_coverage_not_a_contact_rate(self) -> None:
        """16 of 66 pitches produced a measurement. Why the other 50 did not is
        unknown, so this is reported as coverage and nothing else."""
        report = build_report([batted(90.0, 15.0)] * 16 + [unmeasured()] * 50)
        assert report.measured_rate == pytest.approx(24.2, abs=0.1)


class TestExitVelocity:
    def test_best_and_typical_come_from_measured_balls_only(self) -> None:
        report = build_report([batted(90.0, 15.0), batted(80.0, 15.0), unmeasured()])
        assert report.best_exit_velocity_mph == 90.0
        assert report.average_exit_velocity_mph == 85.0

    def test_the_hardest_ball_carries_its_launch_angle(self) -> None:
        report = build_report([batted(80.0, 5.0), batted(95.0, 22.0)])
        assert report.best_exit_velocity_mph == 95.0
        assert report.hardest_ball_launch_angle_deg == 22.0


class TestLineDriveWindow:
    @pytest.mark.parametrize(
        ("angle", "inside"),
        [(-5.0, False), (7.9, False), (8.0, True), (20.0, True), (32.0, True), (32.1, False)],
    )
    def test_the_band_is_inclusive_at_both_ends(self, angle: float, inside: bool) -> None:
        assert (
            FacedPitch(
                event_number=1, exit_velocity_mph=90.0, launch_angle_deg=angle
            ).in_line_drive_window
            is inside
        )

    def test_the_rate_is_denominated_in_measured_balls(self) -> None:
        """Never in pitches: we do not know how many of the rest were swung at."""
        report = build_report(
            [batted(90.0, 15.0), batted(90.0, 40.0), *[unmeasured() for _ in range(20)]]
        )
        assert report.sweet_spot_count == 1
        assert report.sweet_spot_rate == 50.0

    def test_a_ball_with_no_launch_angle_is_not_counted_as_inside(self) -> None:
        report = build_report([FacedPitch(event_number=1, exit_velocity_mph=90.0)])
        assert report.batted_balls == 1
        assert report.sweet_spot_count == 0


class TestPitchContext:
    def test_average_pitch_speed_uses_every_recorded_pitch(self) -> None:
        """Measured on every row, including ones with no batted ball."""
        report = build_report([batted(90.0, 15.0, pitch=80.0), unmeasured(pitch=70.0)])
        assert report.average_pitch_velocity_mph == 75.0

    def test_a_pitch_with_no_speed_is_skipped_rather_than_zeroed(self) -> None:
        report = build_report([FacedPitch(event_number=1), batted(90.0, 15.0, pitch=80.0)])
        assert report.average_pitch_velocity_mph == 80.0


class TestInsights:
    def test_the_hardest_ball_is_always_reported(self) -> None:
        report = build_report([batted(93.4, 20.0)])
        headline = report.insights[0].headline
        assert "93.4 mph" in headline
        assert report.insights[0].kind is InsightKind.STRENGTH

    def test_the_hardest_ball_insight_places_its_launch_angle(self) -> None:
        report = build_report([batted(93.4, 20.0)])
        assert "in the line-drive window" in report.insights[0].detail

    def test_a_thin_sample_is_flagged_rather_than_characterized(self) -> None:
        report = build_report([batted(90.0, 15.0), batted(70.0, 15.0)])
        kinds = {i.kind for i in report.insights}
        assert InsightKind.NOTE in kinds
        assert not any("line-drive window" in i.headline for i in report.insights)

    def test_a_rate_is_only_characterized_once_there_are_enough_balls(self) -> None:
        enough = [batted(90.0, 15.0) for _ in range(MIN_BATTED_BALLS_FOR_A_CLAIM)]
        report = build_report(enough)
        assert any("line-drive window" in i.headline for i in report.insights)

    def test_a_wide_gap_between_best_and_typical_is_called_consistency(self) -> None:
        report = build_report([batted(100.0, 15.0), *[batted(70.0, 15.0) for _ in range(5)]])
        details = " ".join(i.detail for i in report.insights)
        assert "consistency rather than power" in details

    def test_every_insight_names_the_sample_it_rests_on(self) -> None:
        report = build_report([batted(90.0, 15.0) for _ in range(6)])
        for insight in report.insights:
            text = insight.headline + insight.detail
            assert any(ch.isdigit() for ch in text)


def test_the_line_drive_band_is_the_published_one() -> None:
    """8-32 degrees. A physical property of a batted ball, not a judgement
    about a level of play -- which is why it is the only benchmark here."""
    assert (LINE_DRIVE_MIN_DEG, LINE_DRIVE_MAX_DEG) == (8.0, 32.0)
