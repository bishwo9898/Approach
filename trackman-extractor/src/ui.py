"""Points and areas of the TrackMan window, calibrated once with --pick-ui.

Everything is stored relative to the window's top-left corner, exactly like the
capture `region:`, so moving the window does not invalidate a calibration. A
*resized* window does, which is why resolving a target re-reads the window and
refuses to guess.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.macos import Rect


class TargetError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Point:
    """A click position, in points relative to the window's top-left corner."""

    x: float
    y: float

    @property
    def is_set(self) -> bool:
        # (0, 0) is the window's own corner -- never a real control, and what an
        # uncalibrated target looks like.
        return not (self.x == 0 and self.y == 0)

    def on_screen(self, window: Rect) -> tuple[int, int]:
        return round(window.x + self.x), round(window.y + self.y)


@dataclass(frozen=True, slots=True)
class Area:
    """A rectangle to screenshot and read, relative to the window."""

    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0

    @property
    def is_set(self) -> bool:
        return self.width > 0 and self.height > 0

    def on_screen(self, window: Rect) -> Rect:
        return Rect(window.x + self.x, window.y + self.y, self.width, self.height)


def require_point(targets: dict[str, Point], name: str) -> Point:
    point = targets.get(name)
    if point is None:
        raise TargetError(
            f"'{name}' is not a known ui target. Known: {', '.join(sorted(targets)) or 'none'}"
        )
    if not point.is_set:
        raise TargetError(
            f"ui target '{name}' has not been calibrated yet. Run:  python main.py --pick-ui"
        )
    return point


def require_area(areas: dict[str, Area], name: str) -> Area:
    area = areas.get(name)
    if area is None:
        raise TargetError(
            f"'{name}' is not a known ui area. Known: {', '.join(sorted(areas)) or 'none'}"
        )
    if not area.is_set:
        raise TargetError(
            f"ui area '{name}' has not been calibrated yet. Run:  python main.py --pick-ui"
        )
    return area
