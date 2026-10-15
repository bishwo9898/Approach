"""A tiny action language for driving TrackMan's UI.

The capture loop never needed this: it scrolls one table. Walking a roster does
-- open History, filter, pick a player, open Hit, open Table -- and that
sequence belongs to the *app*, not to this program. TrackMan will rearrange its
UI eventually, and when it does the fix should be a few lines of YAML rather
than a patch to Python. The project already holds that line for every other
setting; flows are the same rule applied to clicks.

Six actions, which is enough:

    - click: history_button          # a calibrated ui target
    - type: "{player}"               # {player} is filled in per athlete
    - press: enter                   # enter, escape, tab, down, up
    - wait: 0.4                      # seconds
    - wait_for_text: "EXIT SPEED"    # poll with OCR until it appears
    - scroll: {area: session_list, amount: 300, direction: down}

`wait_for_text` is the one that matters. Fixed sleeps are how UI automation
becomes flaky: too short and it clicks a screen that has not loaded, too long
and a hundred athletes take an hour. Waiting for the text that proves the
screen arrived is both faster and more reliable.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Protocol

from src.macos import Rect
from src.ocr import TextLine
from src.ui import Area, Point

KEYS = {"enter", "return", "escape", "esc", "tab", "down", "up", "left", "right"}
ACTIONS = {"click", "type", "press", "wait", "wait_for_text", "scroll"}


class StepError(Exception):
    pass


class FlowTimeout(StepError):
    """A wait_for_text never saw its text. Almost always a wrong target or a slow load."""


class Driver(Protocol):
    """Everything a flow can do to the machine.

    Narrow on purpose: tests drive flows through a recording stand-in, so the
    step engine is covered without a running app or any permissions.
    """

    def click(self, point: tuple[int, int]) -> None: ...
    def type_text(self, text: str) -> None: ...
    def press(self, key: str) -> None: ...
    def wait(self, seconds: float) -> None: ...
    def read(self, rect: Rect | None) -> list[TextLine]: ...
    def scroll(self, point: tuple[int, int], amount: float, direction: int) -> None: ...
    def window(self) -> Rect: ...


@dataclass(frozen=True, slots=True)
class Step:
    action: str
    value: object

    def describe(self) -> str:
        return f"{self.action}: {self.value}"


def parse_flow(name: str, raw: object) -> list[Step]:
    """Turn the YAML for one flow into steps, rejecting typos up front."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise StepError(f"flows.{name} must be a list of steps")

    steps: list[Step] = []
    for index, item in enumerate(raw, start=1):
        where = f"flows.{name}[{index}]"
        if not isinstance(item, dict) or len(item) != 1:
            raise StepError(f"{where} must be a single 'action: value' pair, got {item!r}")
        action, value = next(iter(item.items()))
        if action not in ACTIONS:
            raise StepError(
                f"{where}: unknown action {action!r}. Use one of: {', '.join(sorted(ACTIONS))}"
            )
        steps.append(Step(action, _check(action, value, where)))
    return steps


def _check(action: str, value: object, where: str) -> object:
    if action in ("click", "type", "wait_for_text"):
        if not isinstance(value, str) or not value.strip():
            raise StepError(f"{where}: {action} needs a non-empty value")
        return value.strip() if action == "click" else value
    if action == "press":
        key = str(value).strip().lower()
        if key not in KEYS:
            raise StepError(f"{where}: press must be one of {', '.join(sorted(KEYS))}, got {value!r}")
        return key
    if action == "wait":
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise StepError(f"{where}: wait needs a number of seconds, got {value!r}")
        return float(value)
    if action == "scroll":
        if not isinstance(value, dict):
            raise StepError(f"{where}: scroll needs area/amount/direction")
        unknown = set(value) - {"area", "amount", "direction"}
        if unknown:
            raise StepError(f"{where}: unknown scroll key(s) {', '.join(sorted(unknown))}")
        if "area" not in value:
            raise StepError(f"{where}: scroll needs an 'area'")
        direction = str(value.get("direction", "down")).lower()
        if direction not in ("down", "up"):
            raise StepError(f"{where}: scroll direction must be down or up")
        amount = value.get("amount", 0)
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount <= 0:
            raise StepError(f"{where}: scroll amount must be a positive number")
        return {"area": str(value["area"]), "amount": float(amount), "direction": direction}
    raise StepError(f"{where}: unhandled action {action!r}")  # pragma: no cover


@dataclass
class FlowRunner:
    driver: Driver
    targets: dict[str, Point]
    areas: dict[str, Area]
    poll_interval: float = 0.4
    text_timeout: float = 15.0

    def run(self, steps: list[Step], context: dict[str, str] | None = None) -> None:
        for step in steps:
            self.run_step(step, context or {})

    def run_step(self, step: Step, context: dict[str, str]) -> None:
        from src.ui import require_area, require_point

        if step.action == "click":
            point = require_point(self.targets, str(step.value))
            self.driver.click(point.on_screen(self.driver.window()))
        elif step.action == "type":
            self.driver.type_text(_fill(str(step.value), context))
        elif step.action == "press":
            self.driver.press(str(step.value))
        elif step.action == "wait":
            self.driver.wait(float(step.value))  # type: ignore[arg-type]
        elif step.action == "wait_for_text":
            self._wait_for_text(_fill(str(step.value), context))
        elif step.action == "scroll":
            spec = step.value
            assert isinstance(spec, dict)
            area = require_area(self.areas, str(spec["area"]))
            rect = area.on_screen(self.driver.window())
            self.driver.scroll(
                rect.center, float(spec["amount"]), 1 if spec["direction"] == "down" else -1
            )

    def _wait_for_text(self, pattern: str) -> None:
        """Poll until `pattern` appears anywhere on screen, or give up.

        Matching is a regular expression so a flow can wait on something loose
        like `Hit|Table`, and the athlete's own name is escaped by the caller
        when it is substituted.
        """
        regex = re.compile(pattern, re.I)
        deadline = time.monotonic() + self.text_timeout
        attempts = 0
        while True:
            attempts += 1
            if any(regex.search(line.text) for line in self.driver.read(None)):
                return
            if time.monotonic() >= deadline:
                raise FlowTimeout(
                    f"Waited {self.text_timeout:g}s for {pattern!r} to appear on screen "
                    f"({attempts} checks) and it never did. The previous click probably "
                    "went somewhere unexpected -- re-run --verify-ui."
                )
            self.driver.wait(self.poll_interval)


def _fill(template: str, context: dict[str, str]) -> str:
    """Substitute {player} and friends, leaving unknown braces alone."""
    out = template
    for key, value in context.items():
        out = out.replace("{" + key + "}", value)
    return out
