"""The real machine behind a flow: mouse, keyboard, screen.

Kept behind the narrow `Driver` interface in steps.py so the flow engine can be
tested without an app, a display, or any macOS permission.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pyautogui

from src import capture, macos, ocr, scrolling
from src.config import Config
from src.macos import Rect
from src.ocr import TextLine


class LiveDriver:
    def __init__(self, cfg: Config, pid: int):
        self.cfg = cfg
        self.pid = pid
        self._scratch = Path(tempfile.mkdtemp(prefix="trackman-ocr-"))
        self._shot = self._scratch / "screen.png"

    # -- state ---------------------------------------------------------------

    def window(self) -> Rect:
        window = macos.main_window_bounds(self.pid)
        if window is None:
            raise RuntimeError(f"{self.cfg.app.name} window disappeared.")
        return window

    # -- input ---------------------------------------------------------------

    def click(self, point: tuple[int, int]) -> None:
        pyautogui.failSafeCheck()
        scrolling.move_to(point)
        scrolling.wait(0.05)  # let any hover state settle before the press
        pyautogui.click()
        scrolling.wait(self.cfg.timing.wait_after_click)

    def type_text(self, text: str) -> None:
        pyautogui.failSafeCheck()
        # A per-character interval: TrackMan's search filters as you type, and
        # a burst of keystrokes can outrun it and leave the field truncated.
        pyautogui.write(text, interval=self.cfg.timing.type_interval)

    def press(self, key: str) -> None:
        pyautogui.failSafeCheck()
        pyautogui.press({"esc": "escape", "return": "enter"}.get(key, key))

    def wait(self, seconds: float) -> None:
        scrolling.wait(seconds)

    def scroll(self, point: tuple[int, int], amount: float, direction: int) -> None:
        scrolling.scroll(point, amount, self.cfg.scroll.unit, direction, self.cfg.scroll.invert)

    # -- reading -------------------------------------------------------------

    def read(self, rect: Rect | None) -> list[TextLine]:
        """OCR an area of the screen, or the whole TrackMan window."""
        area = rect if rect is not None else self.window()
        capture.capture_region(area, self._shot, "png")
        # Fast mode: these reads answer "has this screen arrived", and the
        # accurate model is several times slower for no gain on that question.
        return ocr.recognize(self._shot, fast=True)

    def read_accurately(self, rect: Rect) -> list[TextLine]:
        """OCR an area with the accurate model, for text we are going to keep."""
        capture.capture_region(rect, self._shot, "png")
        return ocr.recognize(self._shot, fast=False)
