"""Milestone 1: capture every page of the table currently open in TrackMan.

The loop is event driven and spends almost all its time sleeping:

    screenshot -> compare with previous page -> scroll -> wait -> screenshot ...

It stops when the table no longer moves (bottom reached), when it hits
max_pages_per_player, or when you stop it. Pages already saved always stay
on disk, and metadata.json is updated after every page.

Player navigation (next milestone) will call capture_pages() after opening
each player's table.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pyautogui

from src import capture, compare, macos, metadata, scrolling
from src.capture import CaptureError
from src.config import Config
from src.macos import Rect
from src.utils import log, new_player_folder

TOP_SEARCH_LIMIT = 60  # scroll-up attempts before giving up on finding the top


class StopCapture(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


def preflight(cfg: Config, need_region: bool = True) -> tuple[int | None, list[str], list[str]]:
    """Check everything needed before touching the mouse.

    Returns (TrackMan pid, problems to show the user, missing permissions).
    """
    problems = []
    pid = macos.find_app_pid(cfg.app.bundle_id)
    if pid is None:
        problems.append(f"{cfg.app.name} is not running. Open it, log in, and open a player's table.")
    elif macos.main_window_bounds(pid) is None:
        problems.append(f"{cfg.app.name} has no visible window (minimised, or on another desktop Space?).")
    missing = macos.missing_permissions()
    if missing:
        problems.append(
            f"Missing macOS permission(s): {', '.join(missing)}. Grant them to the app you run "
            "this from (Terminal, iTerm, VS Code) in System Settings > Privacy & Security, "
            "then quit and reopen that app. See README.md."
        )
    if need_region and not cfg.region.is_set:
        problems.append("No capture region yet. Run:  python main.py --pick-region")
    return pid, problems, missing


def screen_region(cfg: Config, pid: int) -> tuple[Rect, Rect]:
    """(capture rectangle on screen, TrackMan window), following the window if it moved."""
    window = macos.main_window_bounds(pid)
    if window is None:
        raise StopCapture("window_missing", f"{cfg.app.name} window disappeared (closed or minimised?).")
    r = cfg.region
    if abs(window.width - r.window_width) > 2 or abs(window.height - r.window_height) > 2:
        raise StopCapture(
            "window_resized",
            f"{cfg.app.name} window is {window.width:g}x{window.height:g} points but was "
            f"{r.window_width:g}x{r.window_height:g} when the region was picked. "
            "Resize it back, or re-run --pick-region.",
        )
    return Rect(window.x + r.x, window.y + r.y, r.width, r.height), window


def ensure_clear(cfg: Config, pid: int, rect: Rect) -> None:
    """Make sure nothing is covering the table before a screenshot or scroll."""
    for attempt in range(5):
        blocker = macos.obstructing_app(pid, rect)
        if blocker is None:
            return
        if attempt == 0:
            log.warning(f"{blocker} is covering the table; bringing {cfg.app.name} back to the front")
        macos.activate_app(cfg.app.bundle_id)
        scrolling.wait(cfg.timing.wait_after_activate + 1)
    raise StopCapture("obstructed", f"{blocker} keeps covering the table. Close it and try again.")


def grab(cfg: Config, pid: int, path: Path):
    """Screenshot the table to `path`. Returns (fingerprint, rect used)."""
    rect, _ = screen_region(cfg, pid)
    ensure_clear(cfg, pid, rect)
    capture.capture_region(rect, path, cfg.output.image_format)
    return compare.fingerprint(path), rect


def scroll_to_top(cfg: Config, pid: int, folder: Path) -> None:
    log.info("Scrolling to the top of the table")
    det = cfg.detection
    probe = folder / f"_probe.{cfg.output.image_format}"
    try:
        before, rect = grab(cfg, pid, probe)
        unchanged = 0
        for _ in range(TOP_SEARCH_LIMIT):
            scrolling.scroll(rect.center, cfg.scroll_amount * 3, cfg.scroll.unit, scrolling.UP, cfg.scroll.invert)
            scrolling.wait(cfg.timing.wait_after_scroll)
            after, rect = grab(cfg, pid, probe)
            if compare.changed_fraction(before, after, det.pixel_tolerance) <= det.unchanged_threshold:
                unchanged += 1
                if unchanged >= det.unchanged_frames_required:
                    return
            else:
                unchanged = 0
            before = after
        raise StopCapture("top_not_reached", f"Table still moving after {TOP_SEARCH_LIMIT} scrolls up.")
    finally:
        probe.unlink(missing_ok=True)


def capture_pages(cfg: Config, pid: int, folder: Path, meta: dict) -> str:
    """Screenshot, scroll, repeat. Returns why it stopped: 'bottom_reached' or 'max_pages'."""
    det = cfg.detection
    fmt = cfg.output.image_format
    pending = folder / f"_pending.{fmt}"

    rect, window = screen_region(cfg, pid)
    metadata.set_region(meta, rect, window)
    if cfg.capture.start_from_top:
        scroll_to_top(cfg, pid, folder)

    previous = None
    unchanged = 0
    while True:
        current, rect = grab(cfg, pid, pending)

        if previous is not None and (
            compare.changed_fraction(previous, current, det.pixel_tolerance) <= det.unchanged_threshold
        ):
            pending.unlink()  # identical to the page already saved
            unchanged += 1
            log.info(f"No movement detected ({unchanged}/{det.unchanged_frames_required})")
            if unchanged >= det.unchanged_frames_required:
                log.info("Bottom reached")
                return "bottom_reached"
        else:
            unchanged = 0
            overlap = None
            if previous is not None:
                overlap = compare.find_overlap(
                    previous, current, det.pixel_tolerance, det.overlap_mismatch_threshold
                )
            page = meta["pages"] + 1
            name = f"page_{page:03d}.{fmt}"
            pending.replace(folder / name)
            size = capture.image_size(folder / name)
            if meta["pixel_scale"] is None:
                meta["pixel_scale"] = round(size[0] / rect.width, 3)
            metadata.add_page(meta, name, size, overlap)
            if overlap is not None and overlap.status == "no_overlap":
                _warn(
                    meta,
                    f"Page {page} does not overlap page {page - 1}; rows may have been skipped. "
                    "Lower scroll.target_fraction or raise timing.wait_after_scroll.",
                )
            metadata.write_metadata(meta, folder)
            log.info(f"Captured page {page}")
            previous = current

            if page >= cfg.capture.max_pages_per_player:
                _warn(meta, f"Stopped at max_pages_per_player ({page}) before reaching the bottom.")
                return "max_pages"

        scrolling.scroll(rect.center, cfg.scroll_amount, cfg.scroll.unit, scrolling.DOWN, cfg.scroll.invert)
        scrolling.wait(cfg.timing.wait_after_scroll)


def capture_current_player(cfg: Config, player: str, view: str) -> int:
    """Capture the table that is open right now. Returns a process exit code."""
    pid, problems, _ = preflight(cfg)
    if problems:
        for problem in problems:
            log.error(problem)
        return 1

    started = datetime.now()
    folder = new_player_folder(cfg.captures_path, started.date(), player)
    meta = metadata.new_metadata(cfg, player, view, folder, started)
    metadata.write_metadata(meta, folder)
    log.info(f"Starting capture for {player} ({view} table)")
    log.info(f"Saving to {folder}")

    status = "failed"
    try:
        macos.keep_awake()
        log.info(f"Starting in {cfg.timing.start_delay:g}s. Hands off the mouse; move it to any screen corner to stop.")
        scrolling.wait(cfg.timing.start_delay)
        macos.activate_app(cfg.app.bundle_id)
        scrolling.wait(cfg.timing.wait_after_activate)
        reason = capture_pages(cfg, pid, folder, meta)
        status = "complete" if reason == "bottom_reached" else "incomplete"
    except pyautogui.FailSafeException:
        status, reason = "interrupted", "failsafe_corner"
        log.warning("Stopped: mouse moved to a screen corner")
    except KeyboardInterrupt:
        status, reason = "interrupted", "keyboard_interrupt"
        log.warning("Stopped with Ctrl+C")
    except StopCapture as stop:
        reason = stop.reason
        log.error(stop.message)
    except CaptureError as exc:
        reason = "screencapture_failed"
        log.error(str(exc))
    except Exception:
        reason = "unexpected_error"
        log.exception("Unexpected error")
    finally:
        (folder / f"_pending.{cfg.output.image_format}").unlink(missing_ok=True)

    meta["status"] = status
    meta["stop_reason"] = reason
    meta["finished_at"] = datetime.now().isoformat(timespec="seconds")
    metadata.write_metadata(meta, folder)

    pages = meta["pages"]
    if status == "complete":
        log.info(f"Completed {player} - {pages} page{'s' if pages != 1 else ''}")
    else:
        log.warning(f"{player}: {status} ({reason}) - {pages} page(s) kept in {folder}")
    gaps = sum(1 for f in meta["files"] if f["overlap_with_previous"] == "no_overlap")
    if gaps:
        log.warning(f"{gaps} page(s) may have gaps before them; see 'warnings' in metadata.json")

    if status == "complete":
        return 0
    return 130 if status == "interrupted" else 1


def _warn(meta: dict, message: str) -> None:
    log.warning(message)
    meta["warnings"].append(message)
