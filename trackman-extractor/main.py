"""TrackMan Baseball Pro table capture (Phase 1: screenshots only).

One athlete, already open in TrackMan:

    python main.py --capture-current-player "Jordan Avery"

A whole roster, for a date range:

    python main.py --list-sessions  --from 2026-10-01 --to 2026-10-15   # read only
    python main.py --capture-range  --from 2026-10-01 --to 2026-10-15
    python main.py --capture-range  --from 2026-10-01 --to 2026-10-15 --resume

Setup, in order:

    python main.py --dry-run           check permissions and the window
    python main.py --pick-region       mark the table area
    python main.py --test-region       one test screenshot
    python main.py --calibrate-scroll  measure one scroll step
    python main.py --pick-ui           mark the controls used to switch athlete
    python main.py --verify-ui         move the pointer over each one, clicking nothing

Emergency stop: move the mouse into any screen corner, or press Ctrl+C.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from src.config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from src.utils import log, setup_logging


def a_date(text: str) -> date:
    """--from/--to accept 2026-10-15, or 'today' / 'yesterday'."""
    value = text.strip().lower()
    if value == "today":
        return date.today()
    if value == "yesterday":
        return date.today() - timedelta(days=1)
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{text!r} is not a date. Use YYYY-MM-DD, 'today' or 'yesterday'."
        ) from None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture TrackMan Baseball Pro tables as screenshots.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Dates: --from/--to take YYYY-MM-DD, 'today' or 'yesterday'. "
               "--on DAY is shorthand for --from DAY --to DAY.",
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--capture-current-player", metavar="NAME",
                        help="capture the table that is open in TrackMan right now")
    action.add_argument("--list-sessions", action="store_true",
                        help="read the History list for a date range and save the athletes found "
                             "(clicks nothing)")
    action.add_argument("--capture-range", action="store_true",
                        help="capture every athlete who hit in a date range")
    action.add_argument("--dry-run", action="store_true",
                        help="check permissions, window and config without moving the mouse")
    action.add_argument("--pick-region", action="store_true",
                        help="mark the table corners with the mouse and save them to config.yaml")
    action.add_argument("--test-region", action="store_true",
                        help="take one screenshot of the configured area and open it")
    action.add_argument("--calibrate-scroll", action="store_true",
                        help="scroll once and report how far the table moved")
    action.add_argument("--pick-ui", action="store_true",
                        help="mark the controls used to switch athlete")
    action.add_argument("--verify-ui", action="store_true",
                        help="move the pointer over each marked control, clicking nothing")

    dates = parser.add_argument_group("date range")
    dates.add_argument("--from", dest="start", type=a_date, metavar="DAY",
                       help="first day to include")
    dates.add_argument("--to", dest="end", type=a_date, metavar="DAY",
                       help="last day to include")
    dates.add_argument("--on", type=a_date, metavar="DAY",
                       help="a single day (same as --from DAY --to DAY)")

    parser.add_argument("--roster", type=Path, metavar="FILE",
                        help="athlete list to capture (default: the one --list-sessions wrote)")
    parser.add_argument("--resume", action="store_true",
                        help="with --capture-range, skip athletes already captured for that day")
    parser.add_argument("--view", help="table name recorded in metadata (default: capture.view)")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="path to config.yaml")
    return parser.parse_args()


def resolve_range(args: argparse.Namespace) -> tuple[date | None, date | None]:
    if args.on:
        if args.start or args.end:
            raise ConfigError("Use --on by itself, or --from/--to; not both.")
        return args.on, args.on
    if args.start and args.end and args.start > args.end:
        raise ConfigError(f"--from {args.start} is after --to {args.end}.")
    return args.start, args.end


def main() -> int:
    args = parse_args()
    try:
        cfg = load_config(args.config)
        start, end = resolve_range(args)
    except ConfigError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    setup_logging(cfg.logs_path)

    # Imported here so --help and config errors work even before the
    # macOS libraries are installed.
    from src import calibrate, run, table_capture

    view = args.view or cfg.capture.view
    try:
        if args.capture_current_player:
            player = args.capture_current_player.strip()
            if not player:
                log.error("Player name cannot be empty")
                return 2
            return table_capture.capture_current_player(cfg, player, view)

        if args.list_sessions:
            if start is None and end is None:
                log.error("--list-sessions needs a date range: --on DAY, or --from DAY --to DAY")
                return 2
            out = args.roster or run.roster_file(cfg, start, end)
            return run.list_sessions(cfg, start, end, out)

        if args.capture_range:
            if start is None and end is None and args.roster is None:
                log.error("--capture-range needs --on/--from/--to, or a --roster file")
                return 2
            return _capture_range(cfg, run, args, start, end, view)

        if args.dry_run:
            return calibrate.check_setup(cfg)
        if args.pick_region:
            return calibrate.pick_region(cfg)
        if args.test_region:
            return calibrate.test_region(cfg)
        if args.pick_ui:
            return calibrate.pick_ui(cfg)
        if args.verify_ui:
            return calibrate.verify_ui(cfg)
        return calibrate.calibrate_scroll(cfg)
    except ConfigError as exc:
        log.error(str(exc))
        return 2
    except KeyboardInterrupt:
        log.warning("Stopped with Ctrl+C")
        return 130


def _capture_range(cfg, run, args, start, end, view: str) -> int:
    from src import roster as roster_module

    path = args.roster or run.roster_file(cfg, start, end)
    if not path.exists():
        log.error(
            f"No athlete list at {path}. Run this first:\n"
            f"    python main.py --list-sessions --from {start or 'DAY'} --to {end or 'DAY'}"
        )
        return 2
    names = roster_module.read_roster(path)
    if not names:
        log.error(f"{path} has no athletes in it.")
        return 2
    log.info(f"Roster: {len(names)} athlete(s) from {path.name}")

    # Captures are filed under the day they belong to, not the day the
    # computer happens to be running, so an overnight run lands correctly.
    day = end or start or date.today()
    return run.capture_roster(cfg, names, view, day, start, end, args.resume)


if __name__ == "__main__":
    sys.exit(main())
