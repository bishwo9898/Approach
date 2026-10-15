"""Capturing a whole roster: discover who hit, then capture each one.

Two commands live here.

`--list-sessions` reads TrackMan's History list and writes the athletes it
found to a text file. It clicks nothing. Run it first, read the file, fix any
name OCR got wrong.

`--capture-range` walks that list. Each athlete is independent: a flow that
times out on one is recorded and the run moves to the next, because a roster of
forty should not be lost to one slow screen. Stopping deliberately -- the
failsafe corner or Ctrl+C -- stops everything.

Every run writes a manifest beside the captures saying what happened to each
athlete, which is what `--resume` reads to skip the ones already done.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pyautogui

from src import macos, metadata, roster, scrolling, table_capture
from src.capture import CaptureError
from src.config import Config
from src.live import LiveDriver
from src.ocr import OcrError
from src.steps import FlowRunner, FlowTimeout, StepError
from src.table_capture import StopCapture, preflight
from src.ui import TargetError, require_area
from src.utils import log, new_player_folder, slugify

MANIFEST_VERSION = 1


class RunStopped(Exception):
    """The operator stopped the whole run."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


@dataclass
class PlayerOutcome:
    player: str
    status: str
    reason: str
    pages: int = 0
    folder: str | None = None
    message: str | None = None

    def as_dict(self) -> dict:
        out = {"player": self.player, "status": self.status, "reason": self.reason,
               "pages": self.pages, "folder": self.folder}
        if self.message:
            out["message"] = self.message
        return out


# -- discovery ---------------------------------------------------------------


def discover_sessions(cfg: Config, driver: LiveDriver, runner: FlowRunner,
                      start: date | None, end: date | None) -> list[roster.Session]:
    """Scroll the History list, reading every row. Clicks nothing."""
    area = require_area(cfg.ui.areas, "session_list")
    if cfg.flows.open_history:
        log.info("Opening History")
        runner.run(cfg.flows.open_history)

    anchor = start or end or date.today()
    found: list[roster.Session] = []
    unchanged = 0
    unreadable = 0

    for page in range(1, cfg.history.max_list_pages + 1):
        rect = area.on_screen(driver.window())
        lines = driver.read_accurately(rect)
        rows = roster.sessions_in_rows(lines, around=anchor, name_pattern=cfg.history.name_pattern)
        found, added = roster.merge(found, rows)
        missed = roster.unreadable_rows(
            lines, name_pattern=cfg.history.name_pattern, id_pattern=cfg.history.id_pattern
        )
        unreadable += missed
        log.info(f"History page {page}: {len(rows)} row(s) read, {added} new")
        if missed:
            log.warning(
                f"    {missed} row(s) on this page had an athlete id but no readable name."
            )

        if added == 0:
            unchanged += 1
            if unchanged >= cfg.history.unchanged_pages_required:
                log.info("Reached the end of the History list")
                break
        else:
            unchanged = 0

        driver.scroll(rect.center, cfg.history.scroll_amount, 1)
        scrolling.wait(cfg.timing.wait_after_scroll)
    else:
        log.warning(
            f"Stopped after {cfg.history.max_list_pages} History pages. "
            "Raise history.max_list_pages if the list is longer than that."
        )
    if unreadable:
        log.warning(
            f"{unreadable} row(s) were not read. Compare the list below against TrackMan "
            "and add anyone missing to the roster file by hand."
        )
    return found


def list_sessions(cfg: Config, start: date | None, end: date | None, out_path: Path) -> int:
    """--list-sessions: read the History list and save the roster. Read-only."""
    pid, problems, _ = preflight(cfg, need_region=False)
    problems.extend(_ui_problems(cfg, need_flows=("open_history",)))
    if problems:
        for problem in problems:
            log.error(problem)
        return 1

    driver = LiveDriver(cfg, pid)
    runner = _runner(cfg, driver)
    try:
        macos.keep_awake()
        macos.activate_app(cfg.app.bundle_id)
        scrolling.wait(cfg.timing.wait_after_activate)
        sessions = discover_sessions(cfg, driver, runner, start, end)
    except pyautogui.FailSafeException:
        log.warning("Stopped: mouse moved to a screen corner")
        return 130
    except KeyboardInterrupt:
        log.warning("Stopped with Ctrl+C")
        return 130
    except (FlowTimeout, TargetError, StepError, OcrError, CaptureError) as exc:
        log.error(str(exc))
        return 1

    kept = roster.in_range(sessions, start, end)
    names = roster.players(kept)
    if not names:
        log.error(
            "No athletes were read from the History list. Check --verify-ui, and that the "
            "list is showing sessions for this range."
        )
        return 1

    undated = sum(1 for s in kept if s.day is None)
    log.info(f"Found {len(kept)} session(s) for {len(names)} athlete(s):")
    for session in sorted(kept, key=lambda s: (s.day or date.min, s.player)):
        log.info(f"    {session}")
    if undated:
        log.warning(f"{undated} row(s) had no readable date and were kept. Check them above.")
    dropped = len(sessions) - len(kept)
    if dropped:
        log.info(f"{dropped} session(s) outside {start or 'any'}..{end or 'any'} were ignored.")

    roster.write_roster(out_path, kept, start, end)
    log.info(f"Wrote {len(names)} athlete(s) to {out_path}")
    log.info("Read it, fix any misspelled name, then run --capture-range.")
    return 0


# -- capture -----------------------------------------------------------------


def capture_one(cfg: Config, pid: int, driver: LiveDriver, runner: FlowRunner,
                player: str, view: str, day: date) -> PlayerOutcome:
    """Navigate to one athlete's table and capture it.

    Flow failures are returned, not raised: the roster continues. Only a
    deliberate stop propagates.
    """
    import re as _re

    context = {"player": player, "player_regex": _re.escape(player)}
    folder = None
    try:
        if cfg.flows.reset:
            runner.run(cfg.flows.reset, context)
        runner.run(cfg.flows.select_player, context)
        runner.run(cfg.flows.open_hit_table, context)
    except FlowTimeout as exc:
        return PlayerOutcome(player, "failed", "flow_timeout", message=str(exc))
    except (TargetError, StepError) as exc:
        return PlayerOutcome(player, "failed", "flow_error", message=str(exc))

    started = datetime.now()
    folder = new_player_folder(cfg.captures_path, day, player)
    meta = metadata.new_metadata(cfg, player, view, folder, started)
    metadata.write_metadata(meta, folder)

    status, reason = "failed", "unexpected_error"
    try:
        reason = table_capture.capture_pages(cfg, pid, folder, meta)
        status = "complete" if reason == "bottom_reached" else "incomplete"
    except StopCapture as stop:
        reason = stop.reason
        log.error(stop.message)
        if stop.reason in ("window_resized", "window_missing", "obstructed"):
            # Not this athlete's problem; every athlete after would fail too.
            _finalise(meta, folder, status, reason, started)
            raise RunStopped(stop.reason, stop.message) from stop
    except CaptureError as exc:
        reason = "screencapture_failed"
        log.error(str(exc))
    except Exception:
        reason = "unexpected_error"
        log.exception(f"Unexpected error capturing {player}")
    finally:
        (folder / f"_pending.{cfg.output.image_format}").unlink(missing_ok=True)

    _finalise(meta, folder, status, reason, started)
    return PlayerOutcome(player, status, reason, meta["pages"], folder.name)


def _finalise(meta: dict, folder: Path, status: str, reason: str, started: datetime) -> None:
    meta["status"] = status
    meta["stop_reason"] = reason
    meta["finished_at"] = datetime.now().isoformat(timespec="seconds")
    metadata.write_metadata(meta, folder)


def capture_roster(cfg: Config, players: list[str], view: str, day: date,
                   start: date | None, end: date | None, resume: bool) -> int:
    """--capture-range: walk the roster, capturing each athlete's table."""
    pid, problems, _ = preflight(cfg)
    problems.extend(_ui_problems(cfg, need_flows=("select_player", "open_hit_table")))
    if problems:
        for problem in problems:
            log.error(problem)
        return 1

    day_dir = cfg.captures_path / day.isoformat()
    done = _already_done(day_dir) if resume else set()
    todo = [p for p in players if p not in done]
    if resume and done:
        log.info(f"Resuming: {len(done)} athlete(s) already complete, {len(todo)} to go")
    if not todo:
        log.info("Nothing to do: every athlete on the roster is already captured.")
        return 0

    driver = LiveDriver(cfg, pid)
    runner = _runner(cfg, driver)
    outcomes: list[PlayerOutcome] = []
    started = datetime.now()
    manifest_path = day_dir / f"_run_{started:%Y%m%d_%H%M%S}.json"
    stop_reason = "finished"

    log.info(f"Capturing {len(todo)} athlete(s) into {day_dir}")
    log.info(f"Starting in {cfg.timing.start_delay:g}s. Hands off the mouse; "
             "move it to any screen corner to stop.")
    try:
        macos.keep_awake()
        scrolling.wait(cfg.timing.start_delay)
        macos.activate_app(cfg.app.bundle_id)
        scrolling.wait(cfg.timing.wait_after_activate)

        for index, player in enumerate(todo, start=1):
            log.info(f"[{index}/{len(todo)}] {player}")
            outcome = capture_one(cfg, pid, driver, runner, player, view, day)
            outcomes.append(outcome)
            if outcome.status == "complete":
                log.info(f"    {outcome.pages} page(s) -> {outcome.folder}")
            else:
                log.warning(f"    {outcome.status} ({outcome.reason})")
                if outcome.message:
                    log.warning(f"    {outcome.message}")
            _write_manifest(manifest_path, started, view, start, end, outcomes, "running")
    except pyautogui.FailSafeException:
        stop_reason = "failsafe_corner"
        log.warning("Stopped: mouse moved to a screen corner")
    except KeyboardInterrupt:
        stop_reason = "keyboard_interrupt"
        log.warning("Stopped with Ctrl+C")
    except RunStopped as stop:
        stop_reason = stop.reason
        log.error(f"Run stopped: {stop}")

    _write_manifest(manifest_path, started, view, start, end, outcomes, stop_reason)
    return _report(outcomes, todo, manifest_path, stop_reason)


def _report(outcomes: list[PlayerOutcome], todo: list[str], manifest: Path, stop_reason: str) -> int:
    complete = [o for o in outcomes if o.status == "complete"]
    failed = [o for o in outcomes if o.status != "complete"]
    pages = sum(o.pages for o in outcomes)
    log.info(f"Done: {len(complete)}/{len(todo)} athlete(s) complete, {pages} page(s) total")
    if failed:
        log.warning(f"{len(failed)} athlete(s) did not complete:")
        for outcome in failed:
            log.warning(f"    {outcome.player}: {outcome.reason}")
        log.warning("Fix the cause, then re-run with --resume to do only these.")
    log.info(f"Manifest: {manifest}")

    if stop_reason in ("failsafe_corner", "keyboard_interrupt"):
        return 130
    return 0 if not failed and stop_reason == "finished" else 1


def _write_manifest(path: Path, started: datetime, view: str, start: date | None,
                    end: date | None, outcomes: list[PlayerOutcome], status: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": MANIFEST_VERSION,
        "status": status,
        "view": view,
        "range": {"from": start.isoformat() if start else None,
                  "to": end.isoformat() if end else None},
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "players": [o.as_dict() for o in outcomes],
    }, indent=2) + "\n")


def _already_done(day_dir: Path) -> set[str]:
    """Athletes marked complete in any manifest for this day."""
    done: set[str] = set()
    for manifest in sorted(day_dir.glob("_run_*.json")):
        try:
            data = json.loads(manifest.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for entry in data.get("players", []):
            if entry.get("status") == "complete":
                done.add(entry.get("player", ""))
    return done - {""}


def _runner(cfg: Config, driver: LiveDriver) -> FlowRunner:
    return FlowRunner(
        driver=driver,
        targets=cfg.ui.targets,
        areas=cfg.ui.areas,
        poll_interval=cfg.timing.ocr_poll_interval,
        text_timeout=cfg.timing.wait_for_text_timeout,
    )


def _ui_problems(cfg: Config, need_flows: tuple[str, ...]) -> list[str]:
    problems = []
    for name in need_flows:
        if not getattr(cfg.flows, name):
            problems.append(
                f"flows.{name} is empty in config.yaml. See the flows section and README."
            )
    return problems


def roster_file(cfg: Config, start: date | None, end: date | None) -> Path:
    """Where --list-sessions writes and --capture-range reads by default."""
    span = f"{start or 'any'}_{end or 'any'}"
    return cfg.rosters_path / f"roster_{span}.txt"


def slug(name: str) -> str:  # re-exported for the CLI's messages
    return slugify(name)
