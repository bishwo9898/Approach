"""Screenshot one screen region straight to disk with macOS `screencapture`.

The image never passes through Python memory here: screencapture writes the
file itself, so nothing is held between pages.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image

from src.macos import Rect


class CaptureError(Exception):
    pass


def capture_region(rect: Rect, path: Path, image_format: str = "png") -> None:
    region = f"{round(rect.x)},{round(rect.y)},{round(rect.width)},{round(rect.height)}"
    # -x: no shutter sound. The mouse cursor is never included by default.
    cmd = ["screencapture", "-x", "-t", image_format, "-R", region, str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    # screencapture can print an error yet still exit 0, so any stderr is a failure.
    # (It refuses hidden filenames such as ".page.png", for example.)
    if result.returncode != 0 or result.stderr.strip() or not path.exists() or path.stat().st_size == 0:
        detail = result.stderr.strip() or f"exit code {result.returncode}"
        raise CaptureError(f"screencapture failed for region {region}: {detail}")


def image_size(path: Path) -> tuple[int, int]:
    """(width, height) in pixels. Reads only the file header."""
    with Image.open(path) as image:
        return image.size
