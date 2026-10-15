"""The flow engine, driven by a recording stand-in.

Walking a roster is the part that touches TrackMan's UI, which is exactly the
part no test can exercise for real. So the engine is separated from the machine
behind the `Driver` interface, and these tests drive it with a fake: no app, no
display, no permissions, and every branch reachable -- including the ones that
only happen when a screen never loads.
"""

from __future__ import annotations

import re

import pytest

from src.macos import Rect
from src.ocr import TextLine
from src.steps import FlowRunner, FlowTimeout, StepError, parse_flow
from src.ui import Area, Point, TargetError

WINDOW = Rect(100, 50, 1200, 900)


class FakeDriver:
    """Records what a flow did, and returns whatever text the test wants."""

    def __init__(self, screens: list[list[str]] | None = None):
        self.actions: list[tuple] = []
        # Each read returns the next screen; the last repeats forever.
        self.screens = screens or [[]]
        self.reads = 0
        self.slept = 0.0

    def click(self, point):
        self.actions.append(("click", point))

    def type_text(self, text):
        self.actions.append(("type", text))

    def press(self, key):
        self.actions.append(("press", key))

    def wait(self, seconds):
        self.slept += seconds
        self.actions.append(("wait", seconds))

    def scroll(self, point, amount, direction):
        self.actions.append(("scroll", point, amount, direction))

    def window(self):
        return WINDOW

    def read(self, rect):
        screen = self.screens[min(self.reads, len(self.screens) - 1)]
        self.reads += 1
        return [TextLine(text, 1.0, 0, index * 20, 100, 18) for index, text in enumerate(screen)]


def runner(driver, **kwargs):
    return FlowRunner(
        driver=driver,
        targets={"ok": Point(40, 60), "uncalibrated": Point(0, 0)},
        areas={"list": Area(10, 20, 400, 500), "empty": Area()},
        poll_interval=0.0,
        **kwargs,
    )


def test_a_click_lands_relative_to_the_window() -> None:
    """Targets are stored window-relative so moving the window stays correct."""
    driver = FakeDriver()
    runner(driver).run(parse_flow("f", [{"click": "ok"}]))

    assert driver.actions == [("click", (140, 110))]


def test_the_athlete_name_is_substituted_when_typing() -> None:
    driver = FakeDriver()
    runner(driver).run(parse_flow("f", [{"type": "{player}"}]), {"player": "Jordan Avery"})

    assert driver.actions == [("type", "Jordan Avery")]


def test_an_unknown_placeholder_is_left_alone() -> None:
    """A typo in a flow must not silently type an empty string."""
    driver = FakeDriver()
    runner(driver).run(parse_flow("f", [{"type": "{nope}"}]), {"player": "X"})

    assert driver.actions == [("type", "{nope}")]


def test_wait_for_text_returns_as_soon_as_the_screen_arrives() -> None:
    """The point of waiting on text rather than sleeping: it stops early."""
    driver = FakeDriver([[], [], ["EXIT SPEED", "mph"]])
    runner(driver).run(parse_flow("f", [{"wait_for_text": "EXIT SPEED"}]))

    assert driver.reads == 3


def test_wait_for_text_gives_up_with_an_actionable_message() -> None:
    driver = FakeDriver([["something else"]])

    with pytest.raises(FlowTimeout) as caught:
        runner(driver, text_timeout=0.01).run(parse_flow("f", [{"wait_for_text": "EXIT SPEED"}]))

    message = str(caught.value)
    assert "EXIT SPEED" in message
    assert "--verify-ui" in message  # tells the operator what to do about it


def test_wait_for_text_matches_case_insensitively() -> None:
    driver = FakeDriver([["exit speed"]])
    runner(driver).run(parse_flow("f", [{"wait_for_text": "EXIT SPEED"}]))


def test_an_uncalibrated_target_is_refused_rather_than_clicked() -> None:
    """0,0 is the window corner. Clicking it would do something unpredictable."""
    driver = FakeDriver()

    with pytest.raises(TargetError, match="--pick-ui"):
        runner(driver).run(parse_flow("f", [{"click": "uncalibrated"}]))

    assert driver.actions == []


def test_an_unknown_target_names_what_is_available() -> None:
    driver = FakeDriver()

    with pytest.raises(TargetError, match="ok, uncalibrated"):
        runner(driver).run(parse_flow("f", [{"click": "nope"}]))


def test_scrolling_an_area_uses_its_centre_on_screen() -> None:
    driver = FakeDriver()
    runner(driver).run(parse_flow("f", [{"scroll": {"area": "list", "amount": 300}}]))

    # area (10,20) 400x500 inside window at (100,50) -> centre (310, 320)
    assert driver.actions == [("scroll", (310, 320), 300.0, 1)]


def test_scroll_direction_up_is_negative() -> None:
    driver = FakeDriver()
    runner(driver).run(
        parse_flow("f", [{"scroll": {"area": "list", "amount": 10, "direction": "up"}}])
    )

    assert driver.actions[0][3] == -1


def test_a_whole_flow_runs_in_order() -> None:
    driver = FakeDriver([["Jordan Avery"]])
    steps = parse_flow("select_player", [
        {"click": "ok"},
        {"type": "{player}"},
        {"press": "enter"},
        {"wait_for_text": "{player_regex}"},
    ])

    name = "Jordan Avery"
    runner(driver).run(steps, {"player": name, "player_regex": re.escape(name)})

    assert [a[0] for a in driver.actions] == ["click", "type", "press"]


def test_a_regex_special_character_in_a_name_is_handled() -> None:
    """An athlete called "O'Brien (Jr.)" must not break the wait."""
    name = "O'Brien (Jr.)"
    driver = FakeDriver([[name]])
    runner(driver).run(
        parse_flow("f", [{"wait_for_text": "{player_regex}"}]),
        {"player": name, "player_regex": re.escape(name)},
    )


def test_flow_parsing_rejects_mistakes_before_anything_moves() -> None:
    for bad in (
        [{"klick": "ok"}],
        [{"press": "f13"}],
        [{"wait": -1}],
        [{"click": ""}],
        [{"click": "a", "type": "b"}],
        [{"scroll": {"amount": 10}}],
        [{"scroll": {"area": "l", "amount": 0}}],
        [{"scroll": {"area": "l", "amount": 10, "direction": "sideways"}}],
        "not a list",
    ):
        with pytest.raises(StepError):
            parse_flow("f", bad)


def test_an_empty_flow_is_allowed() -> None:
    """`reset: []` is a legitimate 'nothing needed here'."""
    assert parse_flow("reset", None) == []
    assert parse_flow("reset", []) == []
