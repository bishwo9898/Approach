"""Column mapping: vendor spelling -> our domain.

=============================================================================
IMPORTANT -- READ BEFORE TRUSTING THIS FILE
=============================================================================
The column names below are a SYNTHETIC schema we defined ourselves. They are
modelled on the *shape* we expect from a TrackMan event export (one row per
tracked pitch, batted-ball columns populated when the ball was put in play), but
they are NOT the real TrackMan column names, and no attempt has been made to
guess them.

When an authorized real TrackMan export is available:
  1. Add a new `ColumnMap` below with the real names and units.
  2. Register it in `COLUMN_MAPS` under a new schema version.
  3. Extend `detect_schema` to recognize it.
Nothing outside this file should need to change -- that separation is the entire
reason this file exists.

Units are declared per column and every value is routed through
`bsa.core.units.convert`, including the identity conversions. If a real export
turns out to report metres per second, one entry changes here and nothing else.
=============================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bsa.core.units import Unit
from bsa.domain.vocabulary import BattedBallType, PitchCall, PitchType


@dataclass(frozen=True, slots=True)
class NumericColumn:
    """A measured column and the unit the vendor reports it in."""

    source: str
    unit: Unit
    #: Readings outside this range are rejected as tracking artifacts rather
    #: than stored. Bounds are generous: the intent is to exclude impossible
    #: values, not to second-guess an athlete.
    min_value: float | None = None
    max_value: float | None = None


@dataclass(frozen=True, slots=True)
class ColumnMap:
    """One vendor export schema."""

    version: str
    session_id: str
    session_date: str
    pitch_id: str
    pitcher_id: str

    #: Present in every file of this schema. Used to tell schemas apart.
    required: frozenset[str]

    session_type: str | None = None
    venue: str | None = None
    source_status: str | None = None
    pitch_number: str | None = None
    event_timestamp: str | None = None
    pitcher_name: str | None = None
    batter_id: str | None = None
    batter_name: str | None = None
    tagged_pitch_type: str | None = None
    auto_pitch_type: str | None = None
    pitch_call: str | None = None
    batted_ball_type: str | None = None

    pitch_numeric: dict[str, NumericColumn] = field(default_factory=dict)
    hit_numeric: dict[str, NumericColumn] = field(default_factory=dict)
    #: Source column -> training_context key.
    training_context: dict[str, str] = field(default_factory=dict)


SYNTHETIC_V1 = ColumnMap(
    version="synthetic.v1",
    session_id="SessionUID",
    session_date="SessionDate",
    session_type="SessionType",
    venue="Venue",
    source_status="SourceStatus",
    pitch_id="PitchUID",
    pitch_number="PitchNo",
    event_timestamp="UTCDateTime",
    pitcher_id="PitcherId",
    pitcher_name="PitcherName",
    batter_id="BatterId",
    batter_name="BatterName",
    tagged_pitch_type="TaggedPitchType",
    auto_pitch_type="AutoPitchType",
    pitch_call="PitchCall",
    batted_ball_type="TaggedHitType",
    required=frozenset({"SessionUID", "SessionDate", "PitchUID", "PitcherId"}),
    pitch_numeric={
        "velocity_mph": NumericColumn("RelSpeed", Unit.MPH, 20.0, 110.0),
        "spin_rate_rpm": NumericColumn("SpinRate", Unit.RPM, 0.0, 4000.0),
        "spin_axis_deg": NumericColumn("SpinAxis", Unit.DEGREES, 0.0, 360.0),
        "horizontal_break_in": NumericColumn("HorzBreak", Unit.INCHES, -40.0, 40.0),
        "vertical_break_in": NumericColumn("InducedVertBreak", Unit.INCHES, -40.0, 40.0),
        "release_height_ft": NumericColumn("RelHeight", Unit.FEET, 0.0, 9.0),
        "release_side_ft": NumericColumn("RelSide", Unit.FEET, -6.0, 6.0),
        "extension_ft": NumericColumn("Extension", Unit.FEET, 0.0, 10.0),
        "plate_location_height_ft": NumericColumn("PlateLocHeight", Unit.FEET, -3.0, 8.0),
        "plate_location_side_ft": NumericColumn("PlateLocSide", Unit.FEET, -6.0, 6.0),
        "vertical_approach_angle_deg": NumericColumn("VertApprAngle", Unit.DEGREES, -20.0, 10.0),
        "horizontal_approach_angle_deg": NumericColumn("HorzApprAngle", Unit.DEGREES, -20.0, 20.0),
    },
    hit_numeric={
        "exit_velocity_mph": NumericColumn("ExitSpeed", Unit.MPH, 10.0, 130.0),
        "launch_angle_deg": NumericColumn("Angle", Unit.DEGREES, -90.0, 90.0),
        "launch_direction_deg": NumericColumn("Direction", Unit.DEGREES, -90.0, 90.0),
        "distance_ft": NumericColumn("Distance", Unit.FEET, 0.0, 600.0),
        "hang_time_s": NumericColumn("HangTime", Unit.SECONDS, 0.0, 15.0),
        "hit_spin_rate_rpm": NumericColumn("HitSpinRate", Unit.RPM, 0.0, 10000.0),
        "contact_position_x_ft": NumericColumn("ContactPositionX", Unit.FEET, -10.0, 10.0),
        "contact_position_y_ft": NumericColumn("ContactPositionY", Unit.FEET, -10.0, 10.0),
        "contact_position_z_ft": NumericColumn("ContactPositionZ", Unit.FEET, -10.0, 10.0),
    },
    training_context={
        "Drill": "drill",
        "Grip": "grip",
        "Intent": "intent",
        "BallType": "ball_type",
        "BallWeightOz": "ball_weight_oz",
        "TrainingBlock": "training_block",
        "Tags": "tags",
    },
)

COLUMN_MAPS: dict[str, ColumnMap] = {SYNTHETIC_V1.version: SYNTHETIC_V1}


class UnknownSchemaError(ValueError):
    """The header does not match any schema we know how to read.

    Fails the import rather than best-guessing a mapping. A misread column is
    worse than a rejected file: it produces numbers that look fine.
    """


def detect_schema(headers: list[str]) -> ColumnMap:
    present = {h.strip() for h in headers}
    for column_map in COLUMN_MAPS.values():
        if column_map.required <= present:
            return column_map
    # Every column is listed, not a truncated sample: this message is what an
    # operator forwards when an import fails, and a clipped list means another
    # round trip before anyone can act on it.
    raise UnknownSchemaError(
        "No registered TrackMan schema matches this file, so nothing was imported. "
        f"Known schemas: {sorted(COLUMN_MAPS)}. "
        f"Columns in this file ({len(present)}): {', '.join(sorted(present))}. "
        "Run `python -m bsa.scripts.inspect_csv <file>` for a full report."
    )


#: Vendor pitch labels -> our vocabulary. Lowercased, non-alphanumerics stripped
#: before lookup, so "Four-Seam", "FourSeam" and "four seam" all land together.
PITCH_TYPE_ALIASES: dict[str, PitchType] = {
    "fastball": PitchType.FASTBALL,
    "fourseamfastball": PitchType.FASTBALL,
    "fourseam": PitchType.FASTBALL,
    "ff": PitchType.FASTBALL,
    "fb": PitchType.FASTBALL,
    "twoseamfastball": PitchType.SINKER,
    "twoseam": PitchType.SINKER,
    "sinker": PitchType.SINKER,
    "si": PitchType.SINKER,
    "cutter": PitchType.CUTTER,
    "fc": PitchType.CUTTER,
    "slider": PitchType.SLIDER,
    "sl": PitchType.SLIDER,
    "sweeper": PitchType.SLIDER,
    "curveball": PitchType.CURVEBALL,
    "curve": PitchType.CURVEBALL,
    "cb": PitchType.CURVEBALL,
    "cu": PitchType.CURVEBALL,
    "knucklecurve": PitchType.CURVEBALL,
    "changeup": PitchType.CHANGEUP,
    "ch": PitchType.CHANGEUP,
    "splitter": PitchType.SPLITTER,
    "fs": PitchType.SPLITTER,
    "knuckleball": PitchType.KNUCKLEBALL,
    "kn": PitchType.KNUCKLEBALL,
}

PITCH_CALL_ALIASES: dict[str, PitchCall] = {
    "strikecalled": PitchCall.STRIKE_CALLED,
    "calledstrike": PitchCall.STRIKE_CALLED,
    "strikeswinging": PitchCall.STRIKE_SWINGING,
    "swingingstrike": PitchCall.STRIKE_SWINGING,
    "ballcalled": PitchCall.BALL,
    "ball": PitchCall.BALL,
    "ballinplay": PitchCall.IN_PLAY,
    "inplay": PitchCall.IN_PLAY,
    "foulball": PitchCall.FOUL,
    "foul": PitchCall.FOUL,
    "hitbypitch": PitchCall.HIT_BY_PITCH,
    "undefined": PitchCall.UNDEFINED,
}

BATTED_BALL_ALIASES: dict[str, BattedBallType] = {
    "groundball": BattedBallType.GROUND_BALL,
    "gb": BattedBallType.GROUND_BALL,
    "linedrive": BattedBallType.LINE_DRIVE,
    "ld": BattedBallType.LINE_DRIVE,
    "flyball": BattedBallType.FLY_BALL,
    "fb": BattedBallType.FLY_BALL,
    "popup": BattedBallType.POPUP,
    "pu": BattedBallType.POPUP,
}


def _normalize_key(raw: str) -> str:
    return "".join(ch for ch in raw.lower() if ch.isalnum())


def normalize_pitch_type(raw: str | None) -> str | None:
    """Map a vendor pitch label onto our vocabulary.

    An unrecognized label is returned upper-cased rather than bucketed into
    OTHER: preserving it keeps the data honest and makes the gap visible, where
    forcing it into OTHER would hide a mapping we still owe.
    """
    if not raw or not raw.strip():
        return None
    known = PITCH_TYPE_ALIASES.get(_normalize_key(raw))
    return known.value if known else raw.strip().upper()


def normalize_pitch_call(raw: str | None) -> str | None:
    if not raw or not raw.strip():
        return None
    known = PITCH_CALL_ALIASES.get(_normalize_key(raw))
    return known.value if known else raw.strip().upper()


def normalize_batted_ball_type(raw: str | None) -> str | None:
    if not raw or not raw.strip():
        return None
    known = BATTED_BALL_ALIASES.get(_normalize_key(raw))
    return known.value if known else raw.strip().upper()
