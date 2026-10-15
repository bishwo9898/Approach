"""Setup helpers: --dry-run, --pick-region, --test-region, --calibrate-scroll."""

from __future__ import annotations

import re
import subprocess
from datetime import datetime

import pyautogui

from src import capture, compare, macos, scrolling
from src.config import Config, ConfigError
from src.table_capture import StopCapture, grab, preflight, screen_region
from src.ui import Area, Point
from src.utils import log

REGION_BLOCK = re.compile(r"(# --- region \(written by --pick-region\) ---\n).*?(# --- end region ---)", re.S)


def check_setup(cfg: Config) -> int:
    """--dry-run: report what a capture would do. Moves nothing, captures nothing."""
    pid, problems, missing = preflight(cfg)
    log.info(f"Config: {cfg.path}")
    log.info(f"{cfg.app.name}: {'running (pid %d)' % pid if pid else 'NOT running'}")
    if pid and cfg.region.is_set:
        try:
            rect, window = screen_region(cfg, pid)
            log.info(f"Window: {window.width:g}x{window.height:g} at ({window.x:g}, {window.y:g})")
            log.info(f"Capture area on screen: {rect.width:g}x{rect.height:g} at ({rect.x:g}, {rect.y:g})")
            blocker = macos.obstructing_app(pid, rect)
            if blocker:
                log.info(f"Note: {blocker} currently covers the table (fine; the capture brings TrackMan forward)")
        except StopCapture as stop:
            problems.append(stop.message)
    unit = "points" if cfg.scroll.unit == "pixel" else "lines"
    log.info(f"Scroll per page: {cfg.scroll_amount:g} {unit}; max {cfg.capture.max_pages_per_player} pages")
    log.info(f"Captures go to: {cfg.captures_path}/YYYY-MM-DD/<player_name>/")

    # Roster capture needs more than the table region, so say where that stands
    # too -- without turning a missing calibration into an error for someone
    # who only ever captures the open table.
    calibrated = sorted(n for n, point in cfg.ui.targets.items() if point.is_set)
    pending = sorted(n for n, point in cfg.ui.targets.items() if not point.is_set)
    areas = sorted(n for n, area in cfg.ui.areas.items() if area.is_set)
    if calibrated or areas:
        log.info(f"Roster controls calibrated: {', '.join(calibrated + areas)}")
    if pending or not areas:
        missing_areas = sorted(n for n, a in cfg.ui.areas.items() if not a.is_set)
        log.info(
            f"Not calibrated yet: {', '.join(pending + missing_areas)} "
            "(only needed for --list-sessions / --capture-range; run --pick-ui)"
        )

    if missing:
        macos.request_permissions(missing)
        log.info("Asked macOS to show permission prompts; your terminal app should now be listed in Settings.")
    if problems:
        for problem in problems:
            log.error(problem)
        return 1
    log.info("Ready. (Dry run: no mouse movement, no screenshots.)")
    return 0


def pick_region(cfg: Config) -> int:
    """Record the table corners with the mouse and save them to config.yaml. Needs no permissions."""
    pid = macos.find_app_pid(cfg.app.bundle_id)
    window = macos.main_window_bounds(pid) if pid else None
    if window is None:
        log.error(f"{cfg.app.name} is not running or its window is hidden. Open a player's table first.")
        return 1

    print(
        "\nPut this terminal beside TrackMan so both are visible. Size the TrackMan window\n"
        "the way you will use it for every capture (bigger shows more rows per page).\n"
        "Keep this terminal focused; just hover the mouse over TrackMan and press Enter here.\n"
    )
    input("1) Hover over the TOP-LEFT corner of the table, including the column-name row. Press Enter. ")
    x1, y1 = pyautogui.position()
    input("2) Hover over the BOTTOM-RIGHT corner of the last fully visible row "
          "(leave out the 'Not assigned' legend). Press Enter. ")
    x2, y2 = pyautogui.position()

    window = macos.main_window_bounds(pid) or window  # re-read in case it moved
    left, top = min(x1, x2), min(y1, y2)
    width, height = abs(x2 - x1), abs(y2 - y1)
    if width < 100 or height < 100:
        log.error(f"That area is only {width}x{height} points. Run --pick-region again.")
        return 1
    inside = (
        window.x <= left and window.y <= top
        and left + width <= window.x + window.width and top + height <= window.y + window.height
    )
    if not inside:
        log.error("Both corners must be inside the TrackMan window. Run --pick-region again.")
        return 1

    values = {
        "x": left - window.x,
        "y": top - window.y,
        "width": width,
        "height": height,
        "window_width": window.width,
        "window_height": window.height,
    }
    block = "region:\n" + "".join(f"  {key}: {value:g}\n" for key, value in values.items())
    text = cfg.path.read_text()
    new_text, count = REGION_BLOCK.subn(lambda m: m.group(1) + block + m.group(2), text)
    if count != 1:
        raise ConfigError(f"Region markers missing from {cfg.path}. Paste this in by hand:\n{block}")
    cfg.path.write_text(new_text)
    log.info(f"Saved region {width}x{height} points to {cfg.path.name}. Next: python main.py --test-region")
    return 0


def test_region(cfg: Config) -> int:
    """Take one screenshot of the configured area and open it in Preview."""
    pid, problems, _ = preflight(cfg)
    if problems:
        for problem in problems:
            log.error(problem)
        return 1
    folder = cfg.captures_path / "_calibration"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"region_test_{datetime.now():%Y%m%d_%H%M%S}.{cfg.output.image_format}"
    try:
        macos.activate_app(cfg.app.bundle_id)
        scrolling.wait(cfg.timing.wait_after_activate)
        grab(cfg, pid, path)
    except StopCapture as stop:
        log.error(stop.message)
        return 1
    width, height = capture.image_size(path)
    log.info(f"Saved {path} ({width}x{height} px). Opening it: check the whole table width is inside.")
    subprocess.run(["open", str(path)], check=False)
    return 0


def calibrate_scroll(cfg: Config) -> int:
    """Scroll once, measure how far the table really moved, and suggest settings."""
    pid, problems, _ = preflight(cfg)
    if problems:
        for problem in problems:
            log.error(problem)
        return 1
    det = cfg.detection
    folder = cfg.captures_path / "_calibration"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    before_path = folder / f"scroll_before_{stamp}.{cfg.output.image_format}"
    after_path = folder / f"scroll_after_{stamp}.{cfg.output.image_format}"
    amount, unit = cfg.scroll_amount, cfg.scroll.unit

    try:
        macos.activate_app(cfg.app.bundle_id)
        scrolling.wait(cfg.timing.wait_after_activate)
        before, rect = grab(cfg, pid, before_path)
        scrolling.scroll(rect.center, amount, unit, scrolling.DOWN, cfg.scroll.invert)
        scrolling.wait(cfg.timing.wait_after_scroll)
        after, rect = grab(cfg, pid, after_path)
        scrolling.scroll(rect.center, amount, unit, scrolling.UP, cfg.scroll.invert)  # put it back
    except pyautogui.FailSafeException:
        log.warning("Stopped: mouse moved to a screen corner")
        return 130
    except StopCapture as stop:
        log.error(stop.message)
        return 1

    log.info(f"Saved {before_path.name} and {after_path.name} in {folder}")
    result = compare.find_overlap(before, after, det.pixel_tolerance, det.overlap_mismatch_threshold)
    unit_name = "points" if unit == "pixel" else "lines"

    if result.status == "unchanged":
        log.error(
            "The table did not move. Make sure it has more rows than fit on screen and is not "
            "already at the bottom, then retry. If it still does not move, set scroll.unit: line "
            "and scroll.amount: 5 in config.yaml."
        )
        return 1
    if result.status == "unverifiable":
        log.error("Could not measure the scroll: the captured area has no rows to compare. Check --test-region.")
        return 1
    if result.status == "no_overlap":
        reverse = compare.find_overlap(after, before, det.pixel_tolerance, det.overlap_mismatch_threshold)
        if reverse.status == "overlap":
            log.error("TrackMan scrolled the wrong way. Set scroll.invert: true in config.yaml and retry.")
        else:
            log.error(
                f"Scrolling {amount:g} {unit_name} moved more than a whole page, so rows would be "
                f"skipped. Set scroll.amount to about {max(1, round(amount / 2))} and retry."
            )
        return 1

    scale = capture.image_size(before_path)[0] / rect.width
    body_points = (result.body_bottom_px - result.body_top_px) / scale
    moved_points = result.shift_px / scale
    moved_share = moved_points / body_points
    log.info(
        f"Scrolling {amount:g} {unit_name} moved the table {moved_points:.0f} points: "
        f"{moved_share:.0%} of the {body_points:.0f}-point scrolling area, "
        f"so consecutive pages overlap by {1 - moved_share:.0%}."
    )

    per_unit = moved_points / amount
    suggested = round(cfg.scroll.target_fraction * body_points / per_unit)
    if unit == "pixel" and abs(per_unit - 1) > 0.1:
        log.info(f"TrackMan scrolls {per_unit:.2f} points per scroll point, so 'auto' is off.")
    if moved_share > 0.9:
        log.warning(f"Too little overlap. Set scroll.amount: {suggested} in config.yaml.")
    elif abs(suggested - amount) > max(2, 0.1 * amount):
        log.info(f"For {cfg.scroll.target_fraction:.0%} per page set scroll.amount: {suggested} in config.yaml.")
    else:
        log.info("Scroll settings look good. Next: python main.py --capture-current-player \"<name>\"")
    return 0


UI_BLOCK = re.compile(r"(# --- ui \(written by --pick-ui\) ---\n).*?(# --- end ui ---)", re.S)

#: What each target is, in the order --pick-ui asks for them.
TARGET_PROMPTS = {
    "history_button": "the HISTORY button (what opens the list of sessions)",
    "player_filter": 'the "All players" dropdown in the History filters',
    "player_search": "the search field inside that dropdown",
    "player_first_result": "the FIRST name in the list under the search field",
    "hit_tab": "the Hit view (the hitting data for the selected athlete)",
    "table_tab": "the Table view inside Hit",
}
AREA_PROMPTS = {
    "session_list": (
        "the History rows: top-left of the first row, then bottom-right of the last "
        "visible row. Include the athlete names and the dates; leave out the filter bar"
    ),
}


def pick_ui(cfg: Config) -> int:
    """Record each control's position by hovering over it. Needs no permissions."""
    pid = macos.find_app_pid(cfg.app.bundle_id)
    window = macos.main_window_bounds(pid) if pid else None
    if window is None:
        log.error(f"{cfg.app.name} is not running or its window is hidden.")
        return 1

    print(
        "\nCalibrating the controls used to walk a roster.\n"
        "Put this terminal beside TrackMan. Keep the terminal focused and just hover\n"
        "the mouse over TrackMan, then press Enter here. Press 's' then Enter to skip\n"
        "one and keep whatever is already saved.\n"
    )
    targets = dict(cfg.ui.targets)
    areas = dict(cfg.ui.areas)

    for name, description in TARGET_PROMPTS.items():
        current = targets.get(name)
        state = f"currently {current.x:g},{current.y:g}" if current and current.is_set else "not set"
        answer = input(f"  {name} - hover over {description} [{state}]. Enter / s: ").strip().lower()
        if answer == "s":
            continue
        x, y = pyautogui.position()
        window = macos.main_window_bounds(pid) or window
        if not _inside(window, x, y):
            log.error(f"  That point is outside the {cfg.app.name} window; keeping the old value.")
            continue
        targets[name] = Point(x - window.x, y - window.y)
        print(f"      saved at {targets[name].x:g},{targets[name].y:g}")

    for name, description in AREA_PROMPTS.items():
        current = areas.get(name)
        state = f"currently {current.width:g}x{current.height:g}" if current and current.is_set else "not set"
        answer = input(f"\n  {name} - {description} [{state}]. Enter to set, s to skip: ").strip().lower()
        if answer == "s":
            continue
        input("      hover over the TOP-LEFT of that area and press Enter. ")
        x1, y1 = pyautogui.position()
        input("      hover over the BOTTOM-RIGHT and press Enter. ")
        x2, y2 = pyautogui.position()
        window = macos.main_window_bounds(pid) or window
        left, top = min(x1, x2), min(y1, y2)
        width, height = abs(x2 - x1), abs(y2 - y1)
        if width < 80 or height < 60:
            log.error(f"      That area is only {width}x{height} points; keeping the old value.")
            continue
        if not (_inside(window, left, top) and _inside(window, left + width, top + height)):
            log.error("      Both corners must be inside the TrackMan window; keeping the old value.")
            continue
        areas[name] = Area(left - window.x, top - window.y, width, height)
        print(f"      saved {width}x{height} points")

    _write_ui(cfg, targets, areas)
    missing = [n for n, p in targets.items() if not p.is_set]
    if missing:
        log.warning(f"Still not calibrated: {', '.join(missing)}. Re-run --pick-ui for those.")
    log.info(f"Saved to {cfg.path.name}. Next: python main.py --verify-ui")
    return 0


def verify_ui(cfg: Config) -> int:
    """Move the mouse to each calibrated control in turn. Clicks nothing."""
    pid = macos.find_app_pid(cfg.app.bundle_id)
    window = macos.main_window_bounds(pid) if pid else None
    if window is None:
        log.error(f"{cfg.app.name} is not running or its window is hidden.")
        return 1
    if macos.missing_permissions():
        log.error(
            "Moving the mouse needs the Accessibility permission. See --dry-run."
        )
        return 1

    calibrated = [(name, point) for name, point in cfg.ui.targets.items() if point.is_set]
    if not calibrated:
        log.error("Nothing is calibrated yet. Run:  python main.py --pick-ui")
        return 1

    macos.activate_app(cfg.app.bundle_id)
    scrolling.wait(cfg.timing.wait_after_activate)
    print("\nWatch the pointer. It only moves -- nothing is clicked.\n")
    try:
        for name, point in calibrated:
            window = macos.main_window_bounds(pid) or window
            scrolling.move_to(point.on_screen(window))
            print(f"  {name}")
            scrolling.wait(1.2)
        for name, area in cfg.ui.areas.items():
            if not area.is_set:
                continue
            rect = area.on_screen(window)
            print(f"  {name} (tracing the area)")
            for corner in ((rect.x, rect.y), (rect.x + rect.width, rect.y),
                           (rect.x + rect.width, rect.y + rect.height), (rect.x, rect.y + rect.height),
                           (rect.x, rect.y)):
                scrolling.move_to((round(corner[0]), round(corner[1])))
                scrolling.wait(0.35)
    except pyautogui.FailSafeException:
        log.warning("Stopped: mouse moved to a screen corner")
        return 130

    uncalibrated = [n for n, p in cfg.ui.targets.items() if not p.is_set]
    if uncalibrated:
        log.warning(f"Not calibrated: {', '.join(uncalibrated)}")
    log.info("If the pointer landed on the wrong control, re-run --pick-ui.")
    return 0


def _inside(window, x: float, y: float) -> bool:
    return (window.x <= x <= window.x + window.width
            and window.y <= y <= window.y + window.height)


def _write_ui(cfg: Config, targets: dict, areas: dict) -> None:
    lines = ["ui:", "  targets:"]
    for name in TARGET_PROMPTS:
        point = targets.get(name, Point(0, 0))
        comment = TARGET_PROMPTS[name]
        lines.append(f"    {name}: {{x: {point.x:g}, y: {point.y:g}}}   # {comment}")
    lines.append("  areas:")
    for name in AREA_PROMPTS:
        area = areas.get(name, Area())
        lines.append(
            f"    {name}: {{x: {area.x:g}, y: {area.y:g}, "
            f"width: {area.width:g}, height: {area.height:g}}}"
        )
    block = "\n".join(lines) + "\n"
    text = cfg.path.read_text()
    new_text, count = UI_BLOCK.subn(lambda m: m.group(1) + block + m.group(2), text)
    if count != 1:
        raise ConfigError(f"UI markers missing from {cfg.path}. Paste this in by hand:\n{block}")
    cfg.path.write_text(new_text)
