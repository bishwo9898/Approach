"""Small helpers: folder names, logging."""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date
from pathlib import Path

log = logging.getLogger("trackman")


def slugify(name: str) -> str:
    """'Jordan Avery' -> 'jordan_avery'. Accents are dropped: 'José' -> 'jose'."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_name.lower()).strip("_")
    return slug or "player"


def new_player_folder(captures_dir: Path, day: date, player: str) -> Path:
    """captures/YYYY-MM-DD/<player>/, or <player>_2, _3... if that already exists.

    Existing captures are never overwritten.
    """
    day_dir = captures_dir / day.isoformat()
    base = slugify(player)
    folder, n = day_dir / base, 2
    while folder.exists():
        folder, n = day_dir / f"{base}_{n}", n + 1
    folder.mkdir(parents=True)
    return folder


def setup_logging(logs_dir: Path) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"capture_{date.today().isoformat()}.log"

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    to_file = logging.FileHandler(log_file, encoding="utf-8")
    to_file.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))

    log.setLevel(logging.INFO)
    log.handlers = [console, to_file]
    log.propagate = False
    return log_file
