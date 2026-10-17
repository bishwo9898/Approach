"""What a hitter should take away from one session.

Deliberately narrow, and narrower than it used to be. A TrackMan live at-bat
export gives us, per pitch, a pitch speed and its movement, and -- when the ball
was put in play and the radar got a reading -- an exit speed and a launch angle.
Everything in this report is built from exactly those.

What was removed, and why it matters
------------------------------------
This module previously reported swings, takes and whiffs, derived from the
export's `marker_shape` column by assuming a square meant a ball in play, a
crossed circle a swing and miss, and a circle a take. That mapping was an
inference, not something TrackMan publishes, and a coach reading "13 of your 34
swings missed" correctly objected that TrackMan does not track that.

So it is gone. Nothing here counts a swing, because we cannot tell a swing from
a take: a pitch with no exit speed may have been taken, fouled off, missed, or
hit without the radar getting a reading, and those are indistinguishable in
this export. `marker_shape` is still *stored* with the raw row -- raw source
data is never discarded -- but nothing derives a number from it.

Two rules this module follows and states out loud:

* **Compare the athlete to themselves.** We have no benchmark for this level,
  so "below average" would be invented. The honest comparison is
  best-versus-typical, which is also the more useful coaching point.
* **Never hide the sample size.** Four batted balls is not evidence of
  anything, and the report says so rather than quietly rendering a percentage.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from enum import StrEnum

#: Launch angles that produce line drives. The one external benchmark used
#: anywhere in this report, and it earns its place by being a physical property
#: of a batted ball -- the angles that carry for a hit -- rather than a
#: judgement about a level of play. TrackMan measures the angle; this band only
#: names a range of it.
LINE_DRIVE_MIN_DEG = 8.0
LINE_DRIVE_MAX_DEG = 32.0

#: Below this many measured batted balls, a rate is shown but never
#: characterized as a strength or a weakness.
MIN_BATTED_BALLS_FOR_A_CLAIM = 5


class InsightKind(StrEnum):
    STRENGTH = "STRENGTH"
    WORK_ON = "WORK_ON"
    NOTE = "NOTE"


@dataclass(frozen=True, slots=True)
class FacedPitch:
    """One pitch the hitter saw, as TrackMan measured it.

    There is deliberately no field for what the hitter *did* with it. The
    export does not say, and a nullable `exit_velocity_mph` already carries the
    only distinction we can defend: the radar either measured a batted ball or
    it did not.
    """

    event_number: int | None
    pitch_velocity_mph: float | None = None
    induced_vertical_break_in: float | None = None
    exit_velocity_mph: float | None = None
    launch_angle_deg: float | None = None

    @property
    def is_batted_ball(self) -> bool:
        """A measured batted ball. Its absence is not evidence of a miss."""
        return self.exit_velocity_mph is not None

    @property
    def in_line_drive_window(self) -> bool:
        angle = self.launch_angle_deg
        return angle is not None and LINE_DRIVE_MIN_DEG <= angle <= LINE_DRIVE_MAX_DEG


@dataclass(frozen=True, slots=True)
class Insight:
    kind: InsightKind
    headline: str
    detail: str


@dataclass(frozen=True, slots=True)
class HittingReport:
    #: Pitches TrackMan recorded for this hitter. Not a count of swings.
    pitches_faced: int
    #: Pitches that produced a measured batted ball.
    batted_balls: int

    best_exit_velocity_mph: float | None
    average_exit_velocity_mph: float | None
    average_launch_angle_deg: float | None
    #: Launch angle of the hardest ball, so the headline number has a shape.
    hardest_ball_launch_angle_deg: float | None
    sweet_spot_count: int
    #: Average speed of the pitches recorded. Context for the numbers above,
    #: and measured rather than inferred.
    average_pitch_velocity_mph: float | None

    insights: list[Insight] = field(default_factory=list)

    @property
    def sweet_spot_rate(self) -> float | None:
        """Share of *measured batted balls* in the line-drive window.

        Denominated in batted balls, never in pitches: we do not know how many
        of the other pitches were even swung at.
        """
        if self.batted_balls == 0:
            return None
        return round(100.0 * self.sweet_spot_count / self.batted_balls, 1)

    @property
    def measured_rate(self) -> float | None:
        """Share of recorded pitches that produced a measured batted ball.

        Reported as data coverage, never as a contact rate. A pitch without an
        exit speed may have been taken, fouled, missed, or simply not picked up
        by the radar, and this export cannot tell those apart.
        """
        if self.pitches_faced == 0:
            return None
        return round(100.0 * self.batted_balls / self.pitches_faced, 1)


def _mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 1) if values else None


def build_report(pitches: list[FacedPitch]) -> HittingReport:
    """Summarize one session for the hitter who batted in it."""
    batted = [p for p in pitches if p.is_batted_ball]
    exit_velocities = [p.exit_velocity_mph for p in batted if p.exit_velocity_mph is not None]
    launch_angles = [p.launch_angle_deg for p in batted if p.launch_angle_deg is not None]
    pitch_velocities = [p.pitch_velocity_mph for p in pitches if p.pitch_velocity_mph is not None]

    hardest = max(batted, key=lambda p: p.exit_velocity_mph or 0.0) if batted else None

    report = HittingReport(
        pitches_faced=len(pitches),
        batted_balls=len(batted),
        best_exit_velocity_mph=round(max(exit_velocities), 1) if exit_velocities else None,
        average_exit_velocity_mph=_mean(exit_velocities),
        average_launch_angle_deg=_mean(launch_angles),
        hardest_ball_launch_angle_deg=hardest.launch_angle_deg if hardest else None,
        sweet_spot_count=sum(1 for p in batted if p.in_line_drive_window),
        average_pitch_velocity_mph=_mean(pitch_velocities),
    )
    return HittingReport(
        **{f: getattr(report, f) for f in report.__dataclass_fields__ if f != "insights"},
        insights=_insights(report, batted),
    )


def _insights(report: HittingReport, batted: list[FacedPitch]) -> list[Insight]:
    """Turn the measurements into things a coach would actually say.

    Every claim is about a measured batted ball, and every rate is guarded by a
    sample size. Nothing here characterizes a pitch the hitter did not put in
    play, because the export does not say what happened to it.
    """
    out: list[Insight] = []

    best = report.best_exit_velocity_mph
    average = report.average_exit_velocity_mph

    if best is not None:
        angle = report.hardest_ball_launch_angle_deg
        shape = ""
        if angle is not None:
            placing = "in" if LINE_DRIVE_MIN_DEG <= angle <= LINE_DRIVE_MAX_DEG else "outside"
            shape = f" at {angle:.0f}°, which is {placing} the line-drive window"
        out.append(
            Insight(
                InsightKind.STRENGTH,
                f"Your hardest ball left the bat at {best:.1f} mph",
                f"That is your ceiling in this session{shape}. The swing that "
                "produced it is the one worth repeating.",
            )
        )

    sweet_rate = report.sweet_spot_rate
    if sweet_rate is not None and report.batted_balls >= MIN_BATTED_BALLS_FOR_A_CLAIM:
        if sweet_rate >= 50:
            out.append(
                Insight(
                    InsightKind.STRENGTH,
                    f"{report.sweet_spot_count} of {report.batted_balls} measured balls "
                    "were in the line-drive window",
                    f"Launch angles between {LINE_DRIVE_MIN_DEG:.0f}° and "
                    f"{LINE_DRIVE_MAX_DEG:.0f}° are the ones that fall in. "
                    f"You were there {sweet_rate:.0f}% of the time.",
                )
            )
        else:
            grounders = sum(
                1
                for p in batted
                if p.launch_angle_deg is not None and p.launch_angle_deg < LINE_DRIVE_MIN_DEG
            )
            out.append(
                Insight(
                    InsightKind.WORK_ON,
                    f"Only {report.sweet_spot_count} of {report.batted_balls} measured "
                    "balls were in the line-drive window",
                    f"{grounders} came off the bat below {LINE_DRIVE_MIN_DEG:.0f}°. "
                    "Getting the ball off the ground is worth more than swinging harder.",
                )
            )

    if (
        best is not None
        and average is not None
        and best - average >= 10
        and report.batted_balls >= MIN_BATTED_BALLS_FOR_A_CLAIM
    ):
        out.append(
            Insight(
                InsightKind.WORK_ON,
                f"Your typical ball ({average:.1f} mph) is well below your best ({best:.1f} mph)",
                "A gap that size is consistency rather than power -- the strength "
                "is already there in your best swings.",
            )
        )

    if 0 < report.batted_balls < MIN_BATTED_BALLS_FOR_A_CLAIM:
        out.append(
            Insight(
                InsightKind.NOTE,
                f"Only {report.batted_balls} measured ball"
                f"{'' if report.batted_balls == 1 else 's'} in this session",
                "The numbers above are real but thin. They describe these balls, not a tendency.",
            )
        )

    return out
