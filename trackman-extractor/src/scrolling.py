"""Mouse movement, scrolling and failsafe-aware waiting.

PyAutoGUI's failsafe is on: moving the mouse into any screen corner raises
pyautogui.FailSafeException, which stops the run. Our waits check for it
every 0.1 s, so the corner works even while the program is sleeping.
"""

from __future__ import annotations

import time

import pyautogui
import Quartz

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

# Pixel scrolls are sent as several small events, like a trackpad does,
# rather than one huge jump that an app might clamp or accelerate.
PIXEL_CHUNK = 40

DOWN = 1
UP = -1


def wait(seconds: float) -> None:
    end = time.monotonic() + seconds
    while True:
        pyautogui.failSafeCheck()
        remaining = end - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.1, remaining))


def move_to(point: tuple[int, int]) -> None:
    pyautogui.moveTo(*point)


def scroll(point: tuple[int, int], amount: float, unit: str, direction: int, invert: bool = False) -> None:
    """Scroll the view under `point` by `amount` pixels (points) or lines."""
    move_to(point)  # scroll events go to whatever is under the mouse
    sign = -direction  # macOS: negative scroll deltas move the content up (scroll down)
    if invert:
        sign = -sign

    if unit == "line":
        pyautogui.scroll(sign * int(amount))
        return

    remaining = int(round(amount))
    while remaining > 0:
        pyautogui.failSafeCheck()
        step = min(PIXEL_CHUNK, remaining)
        event = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitPixel, 1, sign * step)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        remaining -= step
        time.sleep(0.01)
