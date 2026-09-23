"""The hitting session report.

The report is shown to a teenager who will act on it, so the tests here are
mostly about what it must refuse to claim.
"""

from __future__ import annotations

from bsa.domain.enums import SwingResult
from bsa.domain.hitting_report import (
    FacedPitch,
    InsightKind,
    PitchGroup,
    build_report,
)


def faced(
    *,
    swing: SwingResult | None = SwingResult.TAKEN,
    ivb: float | None = 15.0,
    ev: float | None = None,
    la: float | None = None,
    velo: float | None = 78.0,
) -> FacedPitch:
    return FacedPitch(
        event_number=1,
        swing_result=swing,
        pitch_velocity_mph=velo,
        induced_vertical_break_in=ivb,
        exit_velocity_mph=ev,
        launch_angle_deg=la,
    )


def headlines(report) -> str:  # type: ignore[no-untyped-def]
    return " | ".join(i.headline for i in report.insights)


def test_counts_takes_swings_whiffs_and_contact() -> None:
    report = build_report(
        [
            faced(swing=SwingResult.TAKEN),
            faced(swing=SwingResult.TAKEN),
            faced(swing=SwingResult.SWING_MISS),
            faced(swing=SwingResult.IN_PLAY, ev=90.0, la=15.0),
        ]
    )

    assert report.pitches_faced == 4
    assert report.taken == 2
    assert report.swings == 2
    assert report.whiffs == 1
    assert report.batted_balls == 1
    assert report.whiff_rate == 50.0


def test_a_ball_in_play_without_a_measurement_is_not_a_batted_ball() -> None:
    """Exit velocity is what makes contact measurable. No reading, no claim."""
    report = build_report([faced(swing=SwingResult.IN_PLAY, ev=None)])

    assert report.swings == 1
    assert report.batted_balls == 0
    assert report.best_exit_velocity_mph is None
    assert report.sweet_spot_rate is None


def test_rates_are_none_rather_than_zero_when_there_is_nothing_to_divide() -> None:
    """A 0% whiff rate off no swings would read as perfect contact."""
    report = build_report([faced(swing=SwingResult.TAKEN)])

    assert report.whiff_rate is None
    assert report.sweet_spot_rate is None
    assert report.best_exit_velocity_mph is None


def test_sweet_spot_window_is_inclusive_at_both_ends() -> None:
    report = build_report(
        [
            faced(swing=SwingResult.IN_PLAY, ev=80.0, la=8.0),
            faced(swing=SwingResult.IN_PLAY, ev=80.0, la=32.0),
            faced(swing=SwingResult.IN_PLAY, ev=80.0, la=7.9),
            faced(swing=SwingResult.IN_PLAY, ev=80.0, la=32.1),
        ]
    )

    assert report.sweet_spot_count == 2
    assert report.sweet_spot_rate == 50.0


def test_pitches_are_grouped_by_measured_movement() -> None:
    """The export does not label pitch types, so movement is all we have."""
    report = build_report(
        [
            faced(ivb=15.0),
            faced(ivb=8.0),
            faced(ivb=-5.0),
            faced(ivb=None),
        ]
    )

    by_group = {g.group: g for g in report.groups}
    assert by_group[PitchGroup.FASTBALL].seen == 2
    assert by_group[PitchGroup.OFFSPEED].seen == 1
    assert by_group[PitchGroup.UNCLASSIFIED].seen == 1


def test_a_pitch_group_is_not_characterized_on_too_few_swings() -> None:
    """The guard that matters most.

    Four swings against breaking balls is not evidence of a weakness against
    breaking balls, however tempting the percentage looks.
    """
    pitches = [faced(swing=SwingResult.IN_PLAY, ivb=15.0, ev=85.0, la=12.0) for _ in range(20)]
    pitches += [faced(swing=SwingResult.SWING_MISS, ivb=-6.0) for _ in range(4)]

    report = build_report(pitches)

    offspeed = next(g for g in report.groups if g.group is PitchGroup.OFFSPEED)
    assert offspeed.whiff_rate == 100.0
    assert not offspeed.has_enough_swings_to_judge
    # Despite a 100% whiff rate, no insight claims a weakness.
    assert "trouble" not in headlines(report)


def test_a_pitch_group_is_characterized_once_there_are_enough_swings() -> None:
    pitches = [faced(swing=SwingResult.IN_PLAY, ivb=15.0, ev=85.0, la=12.0) for _ in range(12)]
    pitches += [faced(swing=SwingResult.SWING_MISS, ivb=-6.0) for _ in range(10)]

    report = build_report(pitches)

    assert "trouble" in headlines(report)


def test_thin_contact_samples_are_called_out_explicitly() -> None:
    pitches = [faced(swing=SwingResult.IN_PLAY, ivb=15.0, ev=85.0, la=12.0) for _ in range(10)]
    pitches += [faced(swing=SwingResult.IN_PLAY, ivb=-6.0, ev=80.0, la=10.0) for _ in range(2)]

    report = build_report(pitches)

    notes = [i for i in report.insights if i.kind is InsightKind.NOTE]
    assert any("Only 2 batted balls" in i.headline for i in notes)


def test_a_consistency_gap_is_reported_as_consistency_not_power() -> None:
    pitches = [faced(swing=SwingResult.IN_PLAY, ev=95.0, la=15.0)]
    pitches += [faced(swing=SwingResult.IN_PLAY, ev=60.0, la=15.0) for _ in range(5)]

    report = build_report(pitches)

    gap = next(i for i in report.insights if "below your best" in i.headline)
    assert gap.kind is InsightKind.WORK_ON
    assert "consistency rather than power" in gap.detail


def test_every_report_says_it_is_only_one_session() -> None:
    """A single day must never read as a trend."""
    report = build_report([faced(swing=SwingResult.IN_PLAY, ev=90.0, la=15.0)])

    assert any(i.headline == "This is one session" for i in report.insights)


def test_the_report_makes_no_medical_or_injury_claim() -> None:
    pitches = [faced(swing=SwingResult.SWING_MISS) for _ in range(30)]
    pitches += [faced(swing=SwingResult.IN_PLAY, ev=45.0, la=-20.0) for _ in range(6)]

    report = build_report(pitches)

    text = " ".join(f"{i.headline} {i.detail}" for i in report.insights).lower()
    for word in ("injur", "risk", "fatigue", "health", "medical"):
        assert word not in text, word


def test_an_empty_session_produces_no_false_claims() -> None:
    report = build_report([])

    assert report.pitches_faced == 0
    assert report.groups == []
    assert report.best_exit_velocity_mph is None
    # Only the honesty note survives.
    assert all(i.kind is InsightKind.NOTE for i in report.insights)
