"""metadata.json for one player's capture folder.

The file is rewritten after every page, so a run that is interrupted still
leaves an accurate record of what was captured. Phase 2 (table extraction)
reads this file, so fields are only ever added, never renamed. Bump
SCHEMA_VERSION if a field's meaning changes.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from src.config import Config
from src.macos import Rect

SCHEMA_VERSION = 1
FILENAME = "metadata.json"


def new_metadata(cfg: Config, player: str, view: str, folder: Path, started: datetime) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "player": player,
        "player_folder": folder.name,
        "source": cfg.app.name,
        "app_bundle_id": cfg.app.bundle_id,
        "view": view,
        "capture_date": started.date().isoformat(),
        "capture_time": started.strftime("%H:%M:%S"),
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": None,
        "status": "in_progress",  # in_progress | complete | incomplete | interrupted | failed
        "stop_reason": None,
        "pages": 0,
        # Pages run top to bottom; consecutive pages overlap by design.
        # Phase 2 can drop the repeated rows using scroll_shift_px.
        "page_order": "top_to_bottom",
        "screenshot_region": None,
        "pixel_scale": None,  # image pixels per screen point (2.0 on Retina)
        "image_format": cfg.output.image_format,
        "scroll": {
            "unit": cfg.scroll.unit,
            "amount": cfg.scroll_amount,
            "target_fraction": cfg.scroll.target_fraction,
        },
        "settings": {
            "timing": asdict(cfg.timing),
            "detection": asdict(cfg.detection),
            "max_pages_per_player": cfg.capture.max_pages_per_player,
        },
        "warnings": [],
        "files": [],
    }


def set_region(meta: dict, region: Rect, window: Rect) -> None:
    meta["screenshot_region"] = {
        "units": "points",
        "screen": region.as_dict(),
        "relative_to_window": {
            "x": region.x - window.x,
            "y": region.y - window.y,
            "width": region.width,
            "height": region.height,
        },
        "window": window.as_dict(),
    }


def add_page(meta: dict, file_name: str, size: tuple[int, int], overlap) -> None:
    """Record a saved page. `overlap` is the compare.Overlap against the previous page (None for page 1)."""
    meta["files"].append(
        {
            "page": len(meta["files"]) + 1,
            "file": file_name,
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "width_px": size[0],
            "height_px": size[1],
            # How far rows moved up since the previous page, in image pixels.
            "scroll_shift_px": overlap.shift_px if overlap else None,
            # overlap | no_overlap | unverifiable | null (first page)
            "overlap_with_previous": overlap.status if overlap else None,
            # Image rows between these two scroll; rows outside them are sticky
            # header/footer. Measured in reduced fingerprint rows = image pixels.
            "body_top_px": overlap.body_top_px if overlap else None,
            "body_bottom_px": overlap.body_bottom_px if overlap else None,
        }
    )
    meta["pages"] = len(meta["files"])


def write_metadata(meta: dict, folder: Path) -> None:
    """Write atomically, so a crash never leaves a half-written file."""
    tmp = folder / (FILENAME + ".tmp")
    tmp.write_text(json.dumps(meta, indent=2) + "\n")
    os.replace(tmp, folder / FILENAME)
