"""Cheap comparisons between consecutive screenshots. No OCR, no ML.

Each screenshot is reduced to a small grayscale "fingerprint": columns are
averaged in groups of 8, rows are kept at full resolution. Keeping every row
lets us measure exactly how many pixels the table scrolled. A fingerprint of a
Retina table screenshot is about 0.6 MB and is the only thing kept in memory
between pages.

Two questions are answered:

* changed_fraction: did the table move at all? (bottom detection)
* find_overlap: does the bottom of the previous page reappear in this one?
  If it does, no rows can have been skipped, and the match tells us the
  scroll distance in pixels.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

COLUMN_GROUP = 8
# iOS draws a fading scroll indicator at the right edge of a scroll view.
# Ignoring the rightmost 2% keeps it from looking like a real change.
RIGHT_EDGE_IGNORE = 0.02


def fingerprint(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        gray = image.convert("L")
    reduced = np.asarray(gray.reduce((COLUMN_GROUP, 1)), dtype=np.int16)
    keep = reduced.shape[1] - int(reduced.shape[1] * RIGHT_EDGE_IGNORE)
    return reduced[:, :keep]


def changed_fraction(a: np.ndarray, b: np.ndarray, pixel_tolerance: int) -> float:
    """Share of fingerprint cells that differ by more than the tolerance (0..1)."""
    if a.shape != b.shape:
        return 1.0
    return np.count_nonzero(np.abs(a - b) > pixel_tolerance) / a.size


@dataclass
class Overlap:
    # "overlap"      bottom of the previous page found again: no gap
    # "no_overlap"   not found: rows may have been skipped
    # "unverifiable" nothing distinctive to match (e.g. empty space)
    # "unchanged"    the frames are identical
    status: str
    shift_px: int | None = None  # how far the content moved up, in image pixels
    body_top_px: int | None = None  # rows above this did not move (sticky header)
    body_bottom_px: int | None = None  # rows from here down did not move (sticky footer)


def find_overlap(
    prev: np.ndarray, curr: np.ndarray, pixel_tolerance: int, mismatch_threshold: float
) -> Overlap:
    if prev.shape != curr.shape:
        return Overlap("unverifiable")

    # Rows that are identical in both frames at the top and bottom are sticky
    # (column headers, legends). Only the rows between them scroll.
    moved = np.flatnonzero((np.abs(prev - curr) > pixel_tolerance).any(axis=1))
    if moved.size == 0:
        return Overlap("unchanged")
    top, bottom = int(moved[0]), int(moved[-1]) + 1

    # The last tenth of the previous page's scrolling area...
    band_height = max(8, (bottom - top) // 10)
    band_start = bottom - band_height
    band = prev[band_start:bottom]
    if band_start - top < 1 or band.max() - band.min() <= pixel_tolerance:
        return Overlap("unverifiable", None, top, bottom)

    # ...should appear higher up in the new page, moved up by the scroll distance.
    best_shift, best_score = None, 1.0
    for shift in range(1, band_start - top + 1):
        window = curr[band_start - shift : bottom - shift]
        score = np.count_nonzero(np.abs(window - band) > pixel_tolerance) / band.size
        if score < best_score:
            best_shift, best_score = shift, score

    if best_score <= mismatch_threshold:
        return Overlap("overlap", best_shift, top, bottom)
    return Overlap("no_overlap", None, top, bottom)
