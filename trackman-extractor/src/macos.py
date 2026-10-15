"""Small wrappers around macOS: permissions, the TrackMan window, focus, sleep.

Reading window positions through Quartz needs no permission at all. Only
posting mouse events (Accessibility) and capturing another app's pixels
(Screen Recording) do.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

import AppKit
import Quartz

# Windows owned by these apps can cover the table even though they are not
# normal (layer 0) app windows.
OVERLAY_OWNERS = {"Notification Center", "NotificationCenter"}


@dataclass(frozen=True)
class Rect:
    """A rectangle in screen points, origin at the top-left of the main display."""

    x: float
    y: float
    width: float
    height: float

    @property
    def center(self) -> tuple[int, int]:
        return round(self.x + self.width / 2), round(self.y + self.height / 2)

    def intersects(self, other: Rect) -> bool:
        return (
            self.x < other.x + other.width
            and other.x < self.x + self.width
            and self.y < other.y + other.height
            and other.y < self.y + self.height
        )

    def as_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


def find_app_pid(bundle_id: str) -> int | None:
    apps = AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id)
    return int(apps[0].processIdentifier()) if apps else None


def activate_app(bundle_id: str) -> None:
    """Bring the app to the front. `open -b` needs no Automation permission."""
    subprocess.run(["open", "-b", bundle_id], check=True, capture_output=True, timeout=15)


def _on_screen_windows() -> list:
    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    return Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []


def _bounds(window) -> Rect:
    b = window["kCGWindowBounds"]
    return Rect(float(b["X"]), float(b["Y"]), float(b["Width"]), float(b["Height"]))


def main_window_bounds(pid: int) -> Rect | None:
    """The app's largest normal on-screen window, or None if minimised/closed."""
    windows = [
        _bounds(w)
        for w in _on_screen_windows()
        if w["kCGWindowOwnerPID"] == pid and w["kCGWindowLayer"] == 0
    ]
    return max(windows, key=lambda r: r.width * r.height, default=None)


def obstructing_app(pid: int, rect: Rect) -> str | None:
    """Name of an app whose window sits on top of `rect`, or None if it is clear.

    The window list is ordered front to back, so we only need to look at the
    windows listed before TrackMan's own.
    """
    for w in _on_screen_windows():
        layer = w["kCGWindowLayer"]
        if w["kCGWindowOwnerPID"] == pid and layer == 0:
            return None
        owner = w.get("kCGWindowOwnerName", "")
        is_cover = layer == 0 or owner in OVERLAY_OWNERS
        if is_cover and w.get("kCGWindowAlpha", 1) > 0 and _bounds(w).intersects(rect):
            return owner or "another window"
    return None


def missing_permissions() -> list[str]:
    missing = []
    if not Quartz.CGPreflightPostEventAccess():
        missing.append("Accessibility")
    if not Quartz.CGPreflightScreenCaptureAccess():
        missing.append("Screen Recording")
    return missing


def request_permissions(missing: list[str]) -> None:
    """Ask macOS to show its permission prompts (and list this terminal app)."""
    if "Accessibility" in missing:
        Quartz.CGRequestPostEventAccess()
    if "Screen Recording" in missing:
        Quartz.CGRequestScreenCaptureAccess()


def keep_awake() -> None:
    """Stop the display sleeping mid-capture. caffeinate exits when we do."""
    subprocess.Popen(
        ["caffeinate", "-d", "-i", "-w", str(os.getpid())],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
