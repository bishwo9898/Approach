"""Synthetic TrackMan-shaped data generator.

Everything this produces is fictional. No real athlete data is used anywhere in
this repository, in seeds, or in tests.

The generator is seeded from a fixed RNG so a given (player, date) always yields
the same numbers. Deterministic fixtures make the ingestion and PR tests
meaningful -- a flaky "did a PR happen" assertion is worthless.
"""

from __future__ import annotations

import csv
import io
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from bsa.integrations.trackman.mapping import SYNTHETIC_V1


#: Fictional athletes. Any resemblance to real players is coincidental.
@dataclass(frozen=True, slots=True)
class SyntheticAthlete:
    external_id: str
    first_name: str
    last_name: str
    preferred_name: str | None
    position: str
    bats: str
    throws: str
    graduation_year: int
    #: Fastball velocity the athlete sits at on day one of the synthetic history.
    base_velocity: float = 0.0
    #: mph gained per month of training, before session-to-session noise.
    velocity_trend: float = 0.0
    base_exit_velocity: float = 0.0
    exit_velocity_trend: float = 0.0
    pitches: bool = True
    hits: bool = False


ATHLETES: list[SyntheticAthlete] = [
    SyntheticAthlete(
        "TM-100241",
        "Jake",
        "Williams",
        None,
        "RHP",
        "R",
        "R",
        2028,
        base_velocity=83.4,
        velocity_trend=0.85,
        pitches=True,
        hits=False,
    ),
    SyntheticAthlete(
        "TM-100377",
        "Ryan",
        "Jones",
        None,
        "RHP",
        "R",
        "R",
        2027,
        base_velocity=84.9,
        velocity_trend=0.70,
        pitches=True,
        hits=False,
    ),
    SyntheticAthlete(
        "TM-100482",
        "Marcus",
        "Cole",
        "Marc",
        "OF",
        "L",
        "L",
        2026,
        base_exit_velocity=88.2,
        exit_velocity_trend=1.10,
        pitches=False,
        hits=True,
    ),
    SyntheticAthlete(
        "TM-100515",
        "Alex",
        "Carter",
        None,
        "C",
        "R",
        "R",
        2027,
        base_exit_velocity=84.6,
        exit_velocity_trend=0.60,
        pitches=False,
        hits=True,
    ),
    SyntheticAthlete(
        "TM-100628",
        "Diego",
        "Herrera",
        None,
        "LHP",
        "L",
        "L",
        2029,
        base_velocity=78.1,
        velocity_trend=1.20,
        pitches=True,
        hits=False,
    ),
    SyntheticAthlete(
        "TM-100733",
        "Owen",
        "Mitchell",
        "Oz",
        "SS",
        "R",
        "R",
        2028,
        base_exit_velocity=81.9,
        exit_velocity_trend=0.95,
        pitches=False,
        hits=True,
    ),
]

DRILLS = ["Bullpen", "Flat Ground", "Command Ladder", "Velo Block"]
HITTING_DRILLS = ["Tee Work", "Front Toss", "Machine BP", "Live BP"]
INTENTS = ["Compete", "Submax", "Max Effort"]
GRIPS = ["Standard", "Offset", "Spike"]
BALL_TYPES = ["Baseball", "PlyoBall"]
TRAINING_BLOCKS = ["Offseason Block 1", "Offseason Block 2", "Preseason"]

_PITCH_MIX = [
    ("Fastball", 0.55),
    ("Slider", 0.18),
    ("Curveball", 0.14),
    ("ChangeUp", 0.13),
]

CSV_HEADERS = [
    "SessionUID",
    "SessionDate",
    "SessionType",
    "Venue",
    "SourceStatus",
    "PitchUID",
    "PitchNo",
    "UTCDateTime",
    "PitcherId",
    "PitcherName",
    "BatterId",
    "BatterName",
    "TaggedPitchType",
    "AutoPitchType",
    "PitchCall",
    "RelSpeed",
    "SpinRate",
    "SpinAxis",
    "HorzBreak",
    "InducedVertBreak",
    "RelHeight",
    "RelSide",
    "Extension",
    "PlateLocHeight",
    "PlateLocSide",
    "VertApprAngle",
    "HorzApprAngle",
    "ExitSpeed",
    "Angle",
    "Direction",
    "Distance",
    "HangTime",
    "HitSpinRate",
    "ContactPositionX",
    "ContactPositionY",
    "ContactPositionZ",
    "TaggedHitType",
    "Drill",
    "Grip",
    "Intent",
    "BallType",
    "BallWeightOz",
    "TrainingBlock",
    "Tags",
]


def _rng(athlete: SyntheticAthlete, session_date: date, salt: str = "") -> random.Random:
    """Deterministic per-athlete-per-day RNG.

    Seeded deliberately: identical inputs must always produce identical fixture
    data, or the ingestion and PR tests would be flaky. Not security-sensitive.
    """
    return random.Random(  # noqa: S311 -- fixture generation, never cryptographic
        f"{athlete.external_id}|{session_date.isoformat()}|{salt}"
    )


def _pick_pitch_type(rng: random.Random) -> str:
    roll = rng.random()
    cumulative = 0.0
    for label, weight in _PITCH_MIX:
        cumulative += weight
        if roll <= cumulative:
            return label
    return "Fastball"


def _months_between(start: date, end: date) -> float:
    return (end - start).days / 30.44


def generate_session_rows(
    athlete: SyntheticAthlete,
    session_date: date,
    *,
    history_start: date,
    session_uid: str,
    verified: bool = False,
    pitch_count: int | None = None,
    velocity_bonus: float = 0.0,
) -> list[dict[str, str]]:
    """One athlete's rows for one session.

    `velocity_bonus` lets a caller stage a deliberate breakout day, which is how
    the seed produces a realistic personal-record progression rather than noise.
    """
    rng = _rng(athlete, session_date)
    months = _months_between(history_start, session_date)
    start_at = datetime.combine(session_date, time(hour=16), tzinfo=UTC)
    rows: list[dict[str, str]] = []

    shared = {
        "SessionUID": session_uid,
        "SessionDate": session_date.isoformat(),
        "SessionType": "Bullpen" if athlete.pitches else "Cage",
        "Venue": "Main Facility",
        "SourceStatus": "Verified" if verified else "Preliminary",
        "TrainingBlock": TRAINING_BLOCKS[min(int(months // 2), len(TRAINING_BLOCKS) - 1)],
    }

    if athlete.pitches:
        count = pitch_count if pitch_count is not None else rng.randint(22, 34)
        # Session-level form: a pitcher's whole outing runs hot or cold together,
        # which is what makes session averages meaningful.
        session_form = rng.gauss(0, 0.55)
        drill = rng.choice(DRILLS)
        grip = rng.choice(GRIPS)
        intent = rng.choice(INTENTS)

        for index in range(count):
            pitch_type = _pick_pitch_type(rng)
            base = athlete.base_velocity + athlete.velocity_trend * months + session_form
            base += velocity_bonus
            if pitch_type == "Slider":
                base -= 8.5
            elif pitch_type == "Curveball":
                base -= 13.0
            elif pitch_type == "ChangeUp":
                base -= 9.5
            velocity = round(base + rng.gauss(0, 1.1), 1)

            strike_roll = rng.random()
            if strike_roll < 0.42:
                call = "StrikeCalled"
            elif strike_roll < 0.58:
                call = "StrikeSwinging"
            elif strike_roll < 0.68:
                call = "FoulBall"
            elif strike_roll < 0.93:
                call = "BallCalled"
            else:
                call = "InPlay"

            rows.append(
                {
                    **shared,
                    "PitchUID": f"{session_uid}-P{index + 1:03d}",
                    "PitchNo": str(index + 1),
                    "UTCDateTime": (start_at + timedelta(seconds=index * 45)).isoformat(),
                    "PitcherId": athlete.external_id,
                    "PitcherName": f"{athlete.last_name}, {athlete.first_name}",
                    "BatterId": "",
                    "BatterName": "",
                    "TaggedPitchType": pitch_type,
                    "AutoPitchType": pitch_type,
                    "PitchCall": call,
                    "RelSpeed": f"{velocity:.1f}",
                    "SpinRate": f"{rng.gauss(2180 if pitch_type == 'Fastball' else 2420, 95):.0f}",
                    "SpinAxis": f"{rng.uniform(180, 230):.1f}",
                    "HorzBreak": f"{rng.gauss(8.5, 3.0):.1f}",
                    "InducedVertBreak": f"{rng.gauss(14.0, 3.5):.1f}",
                    "RelHeight": f"{rng.gauss(5.9, 0.12):.2f}",
                    "RelSide": f"{rng.gauss(1.8 if athlete.throws == 'R' else -1.8, 0.15):.2f}",
                    "Extension": f"{rng.gauss(6.1, 0.2):.2f}",
                    "PlateLocHeight": f"{rng.gauss(2.4, 0.75):.2f}",
                    "PlateLocSide": f"{rng.gauss(0.0, 0.85):.2f}",
                    "VertApprAngle": f"{rng.gauss(-6.2, 0.9):.2f}",
                    "HorzApprAngle": f"{rng.gauss(0.4, 1.2):.2f}",
                    "ExitSpeed": "",
                    "Angle": "",
                    "Direction": "",
                    "Distance": "",
                    "HangTime": "",
                    "HitSpinRate": "",
                    "ContactPositionX": "",
                    "ContactPositionY": "",
                    "ContactPositionZ": "",
                    "TaggedHitType": "",
                    "Drill": drill,
                    "Grip": grip,
                    "Intent": intent,
                    "BallType": "Baseball",
                    "BallWeightOz": "5.125",
                    "Tags": "bullpen|tracked",
                }
            )

    if athlete.hits:
        count = pitch_count if pitch_count is not None else rng.randint(18, 30)
        session_form = rng.gauss(0, 1.2)
        drill = rng.choice(HITTING_DRILLS)

        for index in range(count):
            base = (
                athlete.base_exit_velocity
                + athlete.exit_velocity_trend * months
                + session_form
                + velocity_bonus
            )
            exit_velocity = round(base + rng.gauss(0, 3.4), 1)
            launch_angle = round(rng.gauss(14.0, 11.0), 1)
            # Crude but monotonic in the right variables: harder and better-angled
            # contact travels further. Synthetic data only -- not a physics model.
            distance = max(
                12.0,
                exit_velocity * 3.4 - abs(launch_angle - 27.0) * 5.2 + rng.gauss(0, 14),
            )
            if launch_angle < 10:
                hit_type = "GroundBall"
            elif launch_angle < 25:
                hit_type = "LineDrive"
            elif launch_angle < 50:
                hit_type = "FlyBall"
            else:
                hit_type = "PopUp"

            rows.append(
                {
                    **shared,
                    "PitchUID": f"{session_uid}-H{index + 1:03d}",
                    "PitchNo": str(index + 1),
                    "UTCDateTime": (start_at + timedelta(seconds=index * 40)).isoformat(),
                    # Machine-fed: deliberately no pitcher. A pitching machine
                    # is not an athlete and must never enter the player table.
                    "PitcherId": "",
                    "PitcherName": "",
                    "BatterId": athlete.external_id,
                    "BatterName": f"{athlete.last_name}, {athlete.first_name}",
                    "TaggedPitchType": "Fastball",
                    "AutoPitchType": "Fastball",
                    "PitchCall": "InPlay",
                    "RelSpeed": f"{rng.gauss(72.0, 1.0):.1f}",
                    "SpinRate": f"{rng.gauss(1850, 70):.0f}",
                    "SpinAxis": f"{rng.uniform(190, 215):.1f}",
                    "HorzBreak": f"{rng.gauss(4.0, 2.0):.1f}",
                    "InducedVertBreak": f"{rng.gauss(10.0, 2.5):.1f}",
                    "RelHeight": f"{rng.gauss(5.2, 0.1):.2f}",
                    "RelSide": f"{rng.gauss(0.0, 0.1):.2f}",
                    "Extension": f"{rng.gauss(5.0, 0.1):.2f}",
                    "PlateLocHeight": f"{rng.gauss(2.5, 0.35):.2f}",
                    "PlateLocSide": f"{rng.gauss(0.0, 0.35):.2f}",
                    "VertApprAngle": f"{rng.gauss(-5.5, 0.5):.2f}",
                    "HorzApprAngle": f"{rng.gauss(0.0, 0.6):.2f}",
                    "ExitSpeed": f"{exit_velocity:.1f}",
                    "Angle": f"{launch_angle:.1f}",
                    "Direction": f"{rng.gauss(0, 18):.1f}",
                    "Distance": f"{distance:.1f}",
                    "HangTime": f"{max(0.4, rng.gauss(3.6, 1.1)):.2f}",
                    "HitSpinRate": f"{rng.gauss(2600, 500):.0f}",
                    "ContactPositionX": f"{rng.gauss(0, 0.4):.2f}",
                    "ContactPositionY": f"{rng.gauss(2.2, 0.3):.2f}",
                    "ContactPositionZ": f"{rng.gauss(2.8, 0.3):.2f}",
                    "TaggedHitType": hit_type,
                    "Drill": drill,
                    "Grip": "Standard",
                    "Intent": rng.choice(INTENTS),
                    "BallType": "Baseball",
                    "BallWeightOz": "5.125",
                    "Tags": "cage|tracked",
                }
            )

    return rows


def rows_to_csv(rows: list[dict[str, str]]) -> bytes:
    """Render rows in the synthetic schema this repository documents."""
    buffer = io.StringIO()
    # LF, not csv's default CRLF: these files are committed, and a line-ending
    # difference would make every regeneration look like a change.
    writer = csv.DictWriter(
        buffer, fieldnames=CSV_HEADERS, extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def session_uid(session_date: date, label: str) -> str:
    return f"TM-SESSION-{session_date.strftime('%Y%m%d')}-{label}"


def build_day_csv(
    athletes: list[SyntheticAthlete],
    session_date: date,
    *,
    history_start: date,
    verified: bool = False,
    velocity_bonus: dict[str, float] | None = None,
) -> bytes:
    """A day's export: one session per athlete, as a facility would receive it."""
    bonus = velocity_bonus or {}
    rows: list[dict[str, str]] = []
    for athlete in athletes:
        rows.extend(
            generate_session_rows(
                athlete,
                session_date,
                history_start=history_start,
                session_uid=session_uid(session_date, athlete.external_id),
                verified=verified,
                velocity_bonus=bonus.get(athlete.external_id, 0.0),
            )
        )
    return rows_to_csv(rows)


#: Guards the generator against drifting away from the documented schema. A real
#: check rather than an assert, so it survives `python -O`.
if not set(CSV_HEADERS) >= SYNTHETIC_V1.required:  # pragma: no cover -- import-time guard
    raise RuntimeError(
        "synthetic CSV headers no longer satisfy the registered TrackMan schema: "
        f"missing {sorted(SYNTHETIC_V1.required - set(CSV_HEADERS))}"
    )
