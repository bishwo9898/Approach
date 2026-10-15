"""The roster run: what happens when one athlete goes wrong.

Forty athletes is roughly an hour of unattended clicking, so the behaviour that
matters most is what the run does when something fails partway through. One
screen that never loads must not cost the other thirty-nine.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from src.run import PlayerOutcome, _already_done, _report, _write_manifest

DAY = date(2026, 10, 9)


def manifest(path: Path, entries: list[dict], status: str = "finished") -> None:
    path.write_text(json.dumps({
        "schema_version": 1, "status": status, "view": "Hit",
        "range": {"from": "2026-10-09", "to": "2026-10-09"},
        "started_at": "2026-10-09T10:00:00", "finished_at": "2026-10-09T10:30:00",
        "players": entries,
    }))


def test_resume_skips_only_the_athletes_that_finished(tmp_path: Path) -> None:
    manifest(tmp_path / "_run_20261009_100000.json", [
        {"player": "Jordan Avery", "status": "complete", "pages": 3},
        {"player": "Riley Chen", "status": "failed", "reason": "flow_timeout", "pages": 0},
        {"player": "Devin Ruiz", "status": "incomplete", "reason": "max_pages", "pages": 100},
    ])

    assert _already_done(tmp_path) == {"Jordan Avery"}


def test_resume_reads_every_manifest_for_the_day(tmp_path: Path) -> None:
    """A second attempt adds to the first rather than replacing it."""
    manifest(tmp_path / "_run_20261009_100000.json",
             [{"player": "Jordan Avery", "status": "complete", "pages": 3}])
    manifest(tmp_path / "_run_20261009_120000.json",
             [{"player": "Riley Chen", "status": "complete", "pages": 2}])

    assert _already_done(tmp_path) == {"Jordan Avery", "Riley Chen"}


def test_a_corrupt_manifest_does_not_stop_a_resume(tmp_path: Path) -> None:
    """A run killed mid-write must not make --resume unusable."""
    (tmp_path / "_run_20261009_100000.json").write_text("{ truncated")
    manifest(tmp_path / "_run_20261009_120000.json",
             [{"player": "Riley Chen", "status": "complete", "pages": 2}])

    assert _already_done(tmp_path) == {"Riley Chen"}


def test_nothing_done_yet_is_an_empty_set(tmp_path: Path) -> None:
    assert _already_done(tmp_path) == set()


def test_the_manifest_records_each_athletes_outcome(tmp_path: Path) -> None:
    path = tmp_path / "_run.json"
    outcomes = [
        PlayerOutcome("Jordan Avery", "complete", "bottom_reached", 3, "jordan_avery"),
        PlayerOutcome("Riley Chen", "failed", "flow_timeout", 0, None,
                      "Waited 15s for 'EXIT SPEED'"),
    ]

    _write_manifest(path, datetime(2026, 10, 9, 10), "Hit",
                    date(2026, 10, 1), date(2026, 10, 15), outcomes, "finished")

    data = json.loads(path.read_text())
    assert data["range"] == {"from": "2026-10-01", "to": "2026-10-15"}
    assert data["players"][0]["pages"] == 3
    # The failure keeps its explanation, so a later --resume is informed.
    assert "EXIT SPEED" in data["players"][1]["message"]


def test_the_manifest_is_written_as_the_run_goes(tmp_path: Path) -> None:
    """Written after every athlete, so a crash still leaves a usable record."""
    path = tmp_path / "_run.json"
    _write_manifest(path, datetime(2026, 10, 9, 10), "Hit", None, None,
                    [PlayerOutcome("A", "complete", "bottom_reached", 1, "a")], "running")

    assert json.loads(path.read_text())["status"] == "running"


def test_a_clean_run_exits_zero() -> None:
    outcomes = [PlayerOutcome("A", "complete", "bottom_reached", 2, "a")]

    assert _report(outcomes, ["A"], Path("m.json"), "finished") == 0


def test_a_run_with_a_failed_athlete_exits_nonzero() -> None:
    outcomes = [
        PlayerOutcome("A", "complete", "bottom_reached", 2, "a"),
        PlayerOutcome("B", "failed", "flow_timeout"),
    ]

    assert _report(outcomes, ["A", "B"], Path("m.json"), "finished") == 1


def test_stopping_deliberately_reports_as_interrupted() -> None:
    """Walking away is not a failure, and should not read like one."""
    outcomes = [PlayerOutcome("A", "complete", "bottom_reached", 2, "a")]

    assert _report(outcomes, ["A", "B"], Path("m.json"), "failsafe_corner") == 130
    assert _report(outcomes, ["A", "B"], Path("m.json"), "keyboard_interrupt") == 130


# -- discovery loop ----------------------------------------------------------


class FakeListDriver:
    """A History list that scrolls, with overlapping reads like the real one."""

    def __init__(self, pages: list[list[str]]):
        self.pages = pages
        self.reads = 0
        self.scrolls = 0

    def window(self):
        from src.macos import Rect

        return Rect(0, 0, 1200, 900)

    def scroll(self, point, amount, direction):
        self.scrolls += 1

    def read_accurately(self, rect):
        from src.ocr import TextLine

        page = self.pages[min(self.reads, len(self.pages) - 1)]
        self.reads += 1
        return [TextLine(text, 1.0, 0, index * 30, 200, 20) for index, text in enumerate(page)]


def discover(pages, cfg_overrides=None):
    from src.config import load_config
    from src.run import discover_sessions
    from src.steps import FlowRunner
    from src.ui import Area

    cfg = load_config()
    cfg.ui.areas["session_list"] = Area(0, 0, 800, 600)
    cfg.flows.open_history = []  # already open
    for key, value in (cfg_overrides or {}).items():
        setattr(cfg.history, key, value)

    driver = FakeListDriver(pages)
    runner = FlowRunner(driver=driver, targets=cfg.ui.targets, areas=cfg.ui.areas)
    found = discover_sessions(cfg, driver, runner, DAY, DAY)
    return found, driver


def test_discovery_scrolls_until_the_list_stops_producing_new_rows() -> None:
    from src.roster import players

    found, driver = discover([
        ["9 Oct 2026", "Jordan Avery", "Riley Chen"],
        ["Riley Chen", "Devin Ruiz"],       # overlaps on purpose
        ["Devin Ruiz"],                        # nothing new
        ["Devin Ruiz"],                        # nothing new again -> stop
    ])

    assert players(found) == ["Jordan Avery", "Riley Chen", "Devin Ruiz"]
    assert driver.reads == 4


def test_discovery_respects_the_page_limit() -> None:
    """A list that never repeats must not scroll forever."""
    words = ["Alpha", "Bravo", "Charlie", "Delta", "Echo",
             "Foxtrot", "Golf", "Hotel", "India", "Juliet"]
    # Names only: a digit anywhere stops it being read as a name at all, which
    # would end the loop early for the wrong reason.
    pages = [[f"{first} {second}"] for first in words for second in words]

    _, driver = discover(pages, {"max_list_pages": 5})

    assert driver.reads == 5


def test_discovery_carries_the_date_heading_across_pages() -> None:
    found, _ = discover([
        ["9 Oct 2026", "Jordan Avery"],
        ["Riley Chen"],   # no date on this page: inherits nothing, stays None
        ["Riley Chen"],
        ["Riley Chen"],
    ])

    by_name = {session.player: session.day for session in found}
    assert by_name["Jordan Avery"] == date(2026, 10, 9)
