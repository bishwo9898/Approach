"""What a hitter should take away from one session.

Deliberately narrow. A live at-bat export measures four things reliably -- the
pitch, whether the batter swung, whether they hit it, and how hard and at what
angle. Everything here is built from exactly those, and nothing is shown that
the data cannot support.

Two rules this module follows and states out loud:

* **Compare the athlete to themselves.** We have one session and no benchmark
  for this level, so "below average" would be invented. The honest comparison
  is best-versus-typical, which is also the more useful coaching point.
* **Never hide the sample size.** Four batted balls against breaking pitches is
  not evidence of a weakness against breaking pitches, and the report says so
  rather than quietly rendering a percentage.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from enum import StrEnum

from bsa.domain.enums import SwingResult

#: Launch angles that produce line drives. This is the one external benchmark
#: used anywhere in the report, because it is a physical property of batted
#: balls rather than a judgement about a level of play.
SWEET_SPOT_MIN_DEG = 8.0
SWEET_SPOT_MAX_DEG = 32.0

#: Induced vertical break separating a carrying fastball from a pitch that
#: drops. Used only because this export does not label pitch types; the report
#: says so wherever the grouping is shown.
FASTBALL_MIN_IVB_IN = 8.0

#: Below this many events a split is described but never characterized.
MIN_SAMPLE_FOR_A_CLAIM = 8
MIN_BATTED_BALLS_FOR_A_CLAIM = 5


class PitchGroup(StrEnum):
    FASTBALL = "FASTBALL"
    OFFSPEED = "OFFSPEED"
    UNCLASSIFIED = "UNCLASSIFIED"

    @property
    def label(self) -> str:
        return {
            PitchGroup.FASTBALL: "Fastballs",
            PitchGroup.OFFSPEED: "Breaking / offspeed",
            PitchGroup.UNCLASSIFIED: "Unclassified",
        }[self]


class InsightKind(StrEnum):
    STRENGTH = "STRENGTH"
    WORK_ON = "WORK_ON"
    NOTE = "NOTE"


@dataclass(frozen=True, slots=True)
class FacedPitch:
    """One pitch the hitter saw."""

    event_number: int | None
    swing_result: SwingResult | None
    pitch_velocity_mph: float | None = None
    induced_vertical_break_in: float | None = None
    exit_velocity_mph: float | None = None
    launch_angle_deg: float | None = None

    @property
    def group(self) -> PitchGroup:
        if self.induced_vertical_break_in is None:
            return PitchGroup.UNCLASSIFIED
        return (
            PitchGroup.FASTBALL
            if self.induced_vertical_break_in >= FASTBALL_MIN_IVB_IN
            else PitchGroup.OFFSPEED
        )

    @property
    def swung(self) -> bool:
        return self.swing_result in (SwingResult.SWING_MISS, SwingResult.IN_PLAY)

    @property
    def is_batted_ball(self) -> bool:
        return self.exit_velocity_mph is not None

    @property
    def in_sweet_spot(self) -> bool:
        angle = self.launch_angle_deg
        return angle is not None and SWEET_SPOT_MIN_DEG <= angle <= SWEET_SPOT_MAX_DEG


@dataclass(frozen=True, slots=True)
class Insight:
    kind: InsightKind
    headline: str
    detail: str


@dataclass(frozen=True, slots=True)
class GroupSplit:
    """How the hitter did against one kind of pitch."""

    group: PitchGroup
    seen: int
    swings: int
    whiffs: int
    batted_balls: int
    average_pitch_velocity_mph: float | None
    average_exit_velocity_mph: float | None
    best_exit_velocity_mph: float | None

    @property
    def whiff_rate(self) -> float | None:
        """Share of swings that missed. None when there is nothing to divide."""
        return None if self.swings == 0 else round(100.0 * self.whiffs / self.swings, 1)

    @property
    def has_enough_swings_to_judge(self) -> bool:
        return self.swings >= MIN_SAMPLE_FOR_A_CLAIM

    @property
    def has_enough_contact_to_judge(self) -> bool:
        return self.batted_balls >= MIN_BATTED_BALLS_FOR_A_CLAIM


@dataclass(frozen=True, slots=True)
class HittingReport:
    pitches_faced: int
    taken: int
    swings: int
    whiffs: int
    batted_balls: int

    best_exit_velocity_mph: float | None
    average_exit_velocity_mph: float | None
    average_launch_angle_deg: float | None
    sweet_spot_count: int

    groups: list[GroupSplit] = field(default_factory=list)
    insights: list[Insight] = field(default_factory=list)

    @property
    def whiff_rate(self) -> float | None:
        return None if self.swings == 0 else round(100.0 * self.whiffs / self.swings, 1)

    @property
    def swing_rate(self) -> float | None:
        if self.pitches_faced == 0:
            return None
        return round(100.0 * self.swings / self.pitches_faced, 1)

    @property
    def sweet_spot_rate(self) -> float | None:
        if self.batted_balls == 0:
            return None
        return round(100.0 * self.sweet_spot_count / self.batted_balls, 1)


def _mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 1) if values else None


def _split(pitches: list[FacedPitch], group: PitchGroup) -> GroupSplit:
    subset = [p for p in pitches if p.group is group]
    swings = [p for p in subset if p.swung]
    batted = [p for p in subset if p.is_batted_ball]
    exit_velocities = [p.exit_velocity_mph for p in batted if p.exit_velocity_mph is not None]
    return GroupSplit(
        group=group,
        seen=len(subset),
        swings=len(swings),
        whiffs=sum(1 for p in swings if p.swing_result is SwingResult.SWING_MISS),
        batted_balls=len(batted),
        average_pitch_velocity_mph=_mean(
            [p.pitch_velocity_mph for p in subset if p.pitch_velocity_mph is not None]
        ),
        average_exit_velocity_mph=_mean(exit_velocities),
        best_exit_velocity_mph=round(max(exit_velocities), 1) if exit_velocities else None,
    )


def build_report(pitches: list[FacedPitch]) -> HittingReport:
    """Summarize one session for the hitter who batted in it."""
    swings = [p for p in pitches if p.swung]
    batted = [p for p in pitches if p.is_batted_ball]
    exit_velocities = [p.exit_velocity_mph for p in batted if p.exit_velocity_mph is not None]
    launch_angles = [p.launch_angle_deg for p in batted if p.launch_angle_deg is not None]

    groups = [split for split in (_split(pitches, g) for g in PitchGroup) if split.seen > 0]

    report = HittingReport(
        pitches_faced=len(pitches),
        taken=sum(1 for p in pitches if p.swing_result is SwingResult.TAKEN),
        swings=len(swings),
        whiffs=sum(1 for p in swings if p.swing_result is SwingResult.SWING_MISS),
        batted_balls=len(batted),
        best_exit_velocity_mph=round(max(exit_velocities), 1) if exit_velocities else None,
        average_exit_velocity_mph=_mean(exit_velocities),
        average_launch_angle_deg=_mean(launch_angles),
        sweet_spot_count=sum(1 for p in batted if p.in_sweet_spot),
        groups=groups,
    )
    return HittingReport(
        **{f: getattr(report, f) for f in report.__dataclass_fields__ if f != "insights"},
        insights=_insights(report, batted),
    )


def _insights(report: HittingReport, batted: list[FacedPitch]) -> list[Insight]:
    """Turn the numbers into things a coach would actually say.

    Every claim here is guarded by a sample size. Where the data is too thin the
    report says that instead of making the claim.
    """
    out: list[Insight] = []

    # -- contact quality ----------------------------------------------------
    best = report.best_exit_velocity_mph
    average = report.average_exit_velocity_mph
    if best is not None:
        out.append(
            Insight(
                InsightKind.STRENGTH,
                f"Your hardest ball left the bat at {best:.1f} mph",
                "That is your ceiling in this session -- the swing that produced it "
                "is the one worth repeating.",
            )
        )

    sweet_rate = report.sweet_spot_rate
    if sweet_rate is not None and report.batted_balls >= MIN_BATTED_BALLS_FOR_A_CLAIM:
        if sweet_rate >= 50:
            out.append(
                Insight(
                    InsightKind.STRENGTH,
                    f"{report.sweet_spot_count} of {report.batted_balls} balls were "
                    f"in the line-drive window",
                    f"Launch angles between {SWEET_SPOT_MIN_DEG:.0f}° and "
                    f"{SWEET_SPOT_MAX_DEG:.0f}° are the ones that fall in. "
                    f"You were there {sweet_rate:.0f}% of the time.",
                )
            )
        else:
            grounders = sum(
                1
                for p in batted
                if p.launch_angle_deg is not None and p.launch_angle_deg < SWEET_SPOT_MIN_DEG
            )
            out.append(
                Insight(
                    InsightKind.WORK_ON,
                    f"Only {report.sweet_spot_count} of {report.batted_balls} balls "
                    f"were in the line-drive window",
                    f"{grounders} were hit below {SWEET_SPOT_MIN_DEG:.0f}°. Getting "
                    "the ball off the ground is worth more than swinging harder.",
                )
            )

    if best is not None and average is not None and best - average >= 10:
        out.append(
            Insight(
                InsightKind.WORK_ON,
                f"Your typical ball ({average:.1f} mph) is well below your best ({best:.1f} mph)",
                "A gap that size is consistency rather than power -- the strength "
                "is already there in your best swings.",
            )
        )

    # -- swing decisions ----------------------------------------------------
    whiff_rate = report.whiff_rate
    if whiff_rate is not None and report.swings >= MIN_SAMPLE_FOR_A_CLAIM:
        if whiff_rate >= 30:
            out.append(
                Insight(
                    InsightKind.WORK_ON,
                    f"{report.whiffs} of your {report.swings} swings missed ({whiff_rate:.0f}%)",
                    "The quickest gain available is putting more of these swings "
                    "in play, not hitting the ones you already reach harder.",
                )
            )
        elif whiff_rate <= 15:
            out.append(
                Insight(
                    InsightKind.STRENGTH,
                    f"You made contact on {report.swings - report.whiffs} of "
                    f"{report.swings} swings",
                    f"A {whiff_rate:.0f}% miss rate means you are finding the ball consistently.",
                )
            )

    # -- what separates the pitch types -------------------------------------
    judged = [g for g in report.groups if g.has_enough_swings_to_judge]
    if len(judged) >= 2:
        judged.sort(key=lambda g: g.whiff_rate or 0)
        best_group, worst_group = judged[0], judged[-1]
        gap = (worst_group.whiff_rate or 0) - (best_group.whiff_rate or 0)
        if gap >= 15:
            out.append(
                Insight(
                    InsightKind.WORK_ON,
                    f"{worst_group.group.label.lower()} gave you more trouble",
                    f"You missed on {worst_group.whiff_rate:.0f}% of swings against "
                    f"them, against {best_group.whiff_rate:.0f}% on "
                    f"{best_group.group.label.lower()}.",
                )
            )

    # -- honesty about what this cannot tell you ----------------------------
    thin = [
        g
        for g in report.groups
        if g.group is not PitchGroup.UNCLASSIFIED
        and g.batted_balls > 0
        and not g.has_enough_contact_to_judge
    ]
    for group in thin:
        out.append(
            Insight(
                InsightKind.NOTE,
                f"Only {group.batted_balls} batted "
                f"{'ball' if group.batted_balls == 1 else 'balls'} against "
                f"{group.group.label.lower()}",
                "Too few to say anything about how you hit them. Worth watching "
                "as more sessions come in.",
            )
        )

    out.append(
        Insight(
            InsightKind.NOTE,
            "This is one session",
            "These numbers describe a single day. Patterns worth acting on need "
            "several sessions before they mean anything.",
        )
    )
    return out
