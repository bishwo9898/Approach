"""Offline tests: a fake TrackMan table stands in for the real app.

The fake draws a tall table with a sticky column header and a sticky legend,
mostly '-' cells (like real hitting data), and scrolls it by exactly the
requested amount on a 2x "Retina" scale. No permissions or app needed.

    .venv/bin/python -m pytest -q
"""

from __future__ import annotations

import json
import random

import pyautogui
import pytest
from PIL import Image, ImageDraw, ImageFont

from src import calibrate, capture, compare, macos, scrolling, table_capture
from src.config import DEFAULT_CONFIG_PATH, Config, ConfigError, RegionConfig, load_config
from src.macos import Rect
from src.utils import new_player_folder, slugify

SCALE = 2
WINDOW = Rect(100, 50, 1000, 800)
REGION = RegionConfig(x=20, y=40, width=600, height=400, window_width=1000, window_height=800)
WIDTH, HEIGHT = 1200, 800  # region in image pixels
HEADER, FOOTER, ROW = 80, 40, 60
BODY = HEIGHT - HEADER - FOOTER
FONT = ImageFont.load_default(size=26)


class FakeTrackMan:
    def __init__(self, rows: int, start_offset: int = 0):
        rng = random.Random(rows)
        self.table = Image.new("L", (WIDTH, rows * ROW), 255)
        draw = ImageDraw.Draw(self.table)
        for i in range(rows):
            y = i * ROW
            cells = [f"#{rows - i}"] + [
                f"{rng.uniform(40, 110):.1f}" if rng.random() < 0.3 else "-" for _ in range(8)
            ]
            for col, text in enumerate(cells):
                draw.text((30 + col * 135, y + 16), text, fill=0, font=FONT)
            draw.line((0, y + ROW - 1, WIDTH, y + ROW - 1), fill=220)
        self.max_offset = max(0, rows * ROW - BODY)
        self.offset = min(start_offset, self.max_offset)
        self.saved_offsets = []

    def render(self, rect, path, image_format="png"):
        assert (rect.x, rect.y) == (WINDOW.x + REGION.x, WINDOW.y + REGION.y)
        assert not path.name.startswith("."), "real screencapture refuses hidden filenames"
        frame = Image.new("L", (WIDTH, HEIGHT), 255)
        draw = ImageDraw.Draw(frame)
        draw.text((30, 25), "PITCH SPEED   EXIT SPEED   LAUNCH ANGLE", fill=0, font=FONT)
        frame.paste(self.table.crop((0, self.offset, WIDTH, self.offset + BODY)), (0, HEADER))
        draw.text((10, HEIGHT - 32), "Not assigned", fill=0, font=FONT)
        frame.save(path)
        self.last_offset = self.offset

    def scroll(self, point, amount, unit, direction, invert=False):
        self.offset = min(self.max_offset, max(0, self.offset + direction * round(amount * SCALE)))


@pytest.fixture
def run(tmp_path, monkeypatch):
    """Returns a function that runs a full capture against a fake table."""

    def _run(rows, start_offset=0, scroll_amount="auto", max_pages=100, scroll_hook=None):
        fake = FakeTrackMan(rows, start_offset)
        monkeypatch.setattr(macos, "find_app_pid", lambda bundle_id: 4242)
        monkeypatch.setattr(macos, "main_window_bounds", lambda pid: WINDOW)
        monkeypatch.setattr(macos, "obstructing_app", lambda pid, rect: None)
        monkeypatch.setattr(macos, "missing_permissions", lambda: [])
        monkeypatch.setattr(macos, "activate_app", lambda bundle_id: None)
        monkeypatch.setattr(macos, "keep_awake", lambda: None)
        monkeypatch.setattr(scrolling, "wait", lambda seconds: None)
        monkeypatch.setattr(capture, "capture_region", fake.render)

        def scroll(*args, **kwargs):
            if scroll_hook:
                scroll_hook()
            fake.scroll(*args, **kwargs)

        monkeypatch.setattr(scrolling, "scroll", scroll)

        # Record the table offset of every page that is actually kept.
        real_add_page = table_capture.metadata.add_page

        def add_page(meta, *args):
            fake.saved_offsets.append(fake.last_offset)
            real_add_page(meta, *args)

        monkeypatch.setattr(table_capture.metadata, "add_page", add_page)

        cfg = Config(region=REGION)
        cfg.output.captures_dir = str(tmp_path / "captures")
        cfg.scroll.amount = scroll_amount
        cfg.capture.max_pages_per_player = max_pages
        code = table_capture.capture_current_player(cfg, "Jordan Avery", "Hit")
        folder = next((tmp_path / "captures").glob("*/jordan_avery"))
        meta = json.loads((folder / "metadata.json").read_text())
        return code, meta, folder, fake

    return _run


def assert_no_gaps(fake):
    offsets = fake.saved_offsets
    assert offsets[0] == 0, "first page must be the top of the table"
    assert offsets[-1] == fake.max_offset, "last page must be the bottom of the table"
    for a, b in zip(offsets, offsets[1:]):
        assert 0 < b - a < BODY, f"gap between offsets {a} and {b}"


def test_captures_whole_table_with_overlap(run):
    code, meta, folder, fake = run(rows=60)
    assert code == 0
    assert meta["status"] == "complete" and meta["stop_reason"] == "bottom_reached"
    assert_no_gaps(fake)
    assert meta["pages"] == len(fake.saved_offsets)
    assert sorted(p.name for p in folder.glob("page_*.png")) == [f["file"] for f in meta["files"]]
    assert not list(folder.glob("_*.png")), "temporary files must be cleaned up"
    assert meta["pixel_scale"] == SCALE
    for prev, page in zip(fake.saved_offsets, meta["files"][1:]):
        assert page["overlap_with_previous"] == "overlap"
        assert HEADER <= page["body_top_px"] < HEADER + ROW
        assert page["body_bottom_px"] <= HEIGHT - FOOTER
    shifts = [page["scroll_shift_px"] for page in meta["files"][1:]]
    expected = [b - a for a, b in zip(fake.saved_offsets, fake.saved_offsets[1:])]
    assert shifts == expected


def test_starts_from_top_when_left_scrolled_down(run):
    code, meta, _, fake = run(rows=60, start_offset=1500)
    assert code == 0
    assert_no_gaps(fake)


def test_table_that_fits_on_one_page(run):
    code, meta, _, fake = run(rows=8)
    assert code == 0
    assert meta["pages"] == 1 and fake.saved_offsets == [0]


def test_too_large_scroll_is_flagged(run):
    code, meta, _, _ = run(rows=60, scroll_amount=380.0)  # 760 px > 680 px scrolling area
    statuses = {page["overlap_with_previous"] for page in meta["files"][1:]}
    assert "no_overlap" in statuses
    assert any("rows may have been skipped" in w for w in meta["warnings"])


def test_max_pages_failsafe(run):
    code, meta, folder, _ = run(rows=60, max_pages=2)
    assert code == 1
    assert meta["status"] == "incomplete" and meta["stop_reason"] == "max_pages"
    assert len(list(folder.glob("page_*.png"))) == 2


def test_corner_failsafe_keeps_partial_capture(run):
    calls = {"n": 0}

    def hook():
        calls["n"] += 1
        if calls["n"] == 5:  # a few scrolls in (after scroll-to-top)
            raise pyautogui.FailSafeException("corner")

    code, meta, folder, _ = run(rows=60, scroll_hook=hook)
    assert code == 130
    assert meta["status"] == "interrupted" and meta["stop_reason"] == "failsafe_corner"
    assert meta["pages"] >= 1
    assert len(list(folder.glob("page_*.png"))) == meta["pages"]


def test_hover_shading_is_not_movement(tmp_path):
    base = Image.new("L", (400, 300), 255)
    ImageDraw.Draw(base).text((10, 10), "#12   78.0   1599", fill=0, font=FONT)
    hovered = base.copy()
    ImageDraw.Draw(hovered).rectangle((0, 100, 400, 160), fill=245)  # light row highlight
    base.save(tmp_path / "a.png")
    hovered.save(tmp_path / "b.png")
    a, b = compare.fingerprint(tmp_path / "a.png"), compare.fingerprint(tmp_path / "b.png")
    assert compare.changed_fraction(a, b, 24) == 0


def test_shipped_config_loads_and_region_markers_exist():
    cfg = load_config(DEFAULT_CONFIG_PATH)
    assert cfg.scroll.amount == "auto"
    assert calibrate.REGION_BLOCK.search(DEFAULT_CONFIG_PATH.read_text())


def test_config_rejects_typos(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("scroll:\n  ammount: 5\n")
    with pytest.raises(ConfigError, match="ammount"):
        load_config(path)
    path.write_text("scroll:\n  unit: line\n")
    with pytest.raises(ConfigError, match="auto only works"):
        load_config(path)


def test_player_folders_never_overwrite(tmp_path):
    from datetime import date

    assert slugify("José O'Neil Jr.") == "jose_o_neil_jr"
    first = new_player_folder(tmp_path, date(2026, 10, 4), "Jordan Avery")
    second = new_player_folder(tmp_path, date(2026, 10, 4), "Jordan Avery")
    assert first.name == "jordan_avery" and second.name == "jordan_avery_2"
