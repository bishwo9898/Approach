"""Our normalized baseball vocabulary.

Vendor labels vary ("Fastball", "FourSeamFastBall", "FF"). The adapter maps
whatever arrives onto these values, so metric filters and coach-facing labels
are written once against names we control.

An unrecognized label is preserved verbatim rather than dropped or forced into
the nearest bucket -- silently reclassifying a pitch corrupts the metric that
filters on it.
"""

from __future__ import annotations

from enum import StrEnum


class PitchType(StrEnum):
    FASTBALL = "FASTBALL"
    SINKER = "SINKER"
    CUTTER = "CUTTER"
    SLIDER = "SLIDER"
    CURVEBALL = "CURVEBALL"
    CHANGEUP = "CHANGEUP"
    SPLITTER = "SPLITTER"
    KNUCKLEBALL = "KNUCKLEBALL"
    OTHER = "OTHER"


class PitchCall(StrEnum):
    STRIKE_CALLED = "STRIKE_CALLED"
    STRIKE_SWINGING = "STRIKE_SWINGING"
    BALL = "BALL"
    FOUL = "FOUL"
    IN_PLAY = "IN_PLAY"
    HIT_BY_PITCH = "HIT_BY_PITCH"
    UNDEFINED = "UNDEFINED"


class BattedBallType(StrEnum):
    GROUND_BALL = "GROUND_BALL"
    LINE_DRIVE = "LINE_DRIVE"
    FLY_BALL = "FLY_BALL"
    POPUP = "POPUP"
    OTHER = "OTHER"


#: Calls that count as a strike for strike-percentage style metrics. A foul ball
#: is a strike for this purpose; a ball in play is not counted either way.
STRIKE_CALLS: frozenset[PitchCall] = frozenset(
    {PitchCall.STRIKE_CALLED, PitchCall.STRIKE_SWINGING, PitchCall.FOUL}
)
