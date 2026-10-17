"""Reading TrackMan's pitch table out of a screenshot.

Most of this runs against `tests/fixtures/trackman_pitch_table_ocr.json`, which
is the **real** output of Apple Vision over a real TrackMan screenshot -- 137
recognized lines, boxes and all, with the athlete's name replaced. Synthetic
cells prove the rules; the fixture proves they survive contact with what OCR
actually emits, which is where every bug in this module came from.

What that screenshot taught us, each now pinned below:

* the row marker is OCR'd as a character and merged into the pitch number
  (`*#54`, `X #42`, `8 #41`), which silently dropped four rows per screenshot;
* the inch mark in `5'2"` comes back as `'`, `i` or `%`;
* a dropped decimal point turns 11.5 into 115, which only a range check sees;
* a lone `-` is the one glyph OCR routinely misses entirely.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bsa.domain.screenshot_table import (
    Cell,
    Column,
    RowProblem,
    SourcedRead,
    TableRow,
    merge_reads,
    parse_clock,
    parse_feet,
    parse_number,
    read_table,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "trackman_pitch_table_ocr.json"


def real_cells() -> list[Cell]:
    lines = json.loads(FIXTURE.read_text())["image.png"]
    return [
        Cell(
            text=line["text"],
            center_x=line["x"] + line["width"] / 2,
            center_y=line["y"] + line["height"] / 2,
            height=line["height"],
        )
        for line in lines
    ]


def grid(rows: list[list[str]], *, header: bool = True) -> list[Cell]:
    """A synthetic table. Columns 180px apart, rows 40px apart."""
    headers = [
        "PITCH SPEED",
        "TOTAL SPIN",
        "TILT",
        "RELEASE HEIGHT",
        "I. VERT. MOV",
        "HORZ. MOV",
        "EXIT SPEED",
        "SPIN RATE",
        "LAUNCH ANGLE",
    ]
    cells: list[Cell] = []
    if header:
        for index, text in enumerate(headers):
            cells.append(Cell(text, center_x=200 + index * 180, center_y=50, height=20))
    for row_index, row in enumerate(rows):
        for index, text in enumerate(row):
            # Column 0 is the pitch number, left of the first value column.
            x = 60 if index == 0 else 200 + (index - 1) * 180
            cells.append(Cell(text, center_x=x, center_y=120 + row_index * 40, height=20))
    return cells


# -- against a real screenshot ----------------------------------------------


class TestRealScreenshot:
    @pytest.fixture
    def read(self):  # type: ignore[no-untyped-def]
        return read_table(real_cells())

    def test_every_column_is_found_by_name(self, read) -> None:  # type: ignore[no-untyped-def]
        assert len(read.columns) == 9
        assert set(read.columns) == set(Column)

    def test_every_row_is_read(self, read) -> None:  # type: ignore[no-untyped-def]
        """Fifteen pitches, #52 to #66, with no holes."""
        assert read.event_numbers == list(range(66, 51, -1))

    def test_nothing_blocks(self, read) -> None:  # type: ignore[no-untyped-def]
        assert read.ok, [p.message for p in read.blocking_problems]

    def test_the_marker_glyph_does_not_hide_a_pitch(self, read) -> None:  # type: ignore[no-untyped-def]
        """#54's crossed circle was recognized as `*`, merging into `*#54`."""
        assert 54 in read.event_numbers

    def test_values_land_in_the_right_columns(self, read) -> None:  # type: ignore[no-untyped-def]
        first = next(r for r in read.rows if r.event_number == 66)
        assert first.values["pitch_speed_mph"] == 78.0
        assert first.values["total_spin_rpm"] == 1599.0
        assert first.values["release_height_ft"] == 5.0
        assert first.values["exit_speed_mph"] == 68.5
        assert first.values["launch_angle_deg"] == 27.2
        # TrackMan showed a dash for these.
        assert first.values["tilt_clock"] is None
        assert first.values["hit_spin_rate_rpm"] is None

    def test_the_batter_is_read_from_the_table(self, read) -> None:  # type: ignore[no-untyped-def]
        assert read.batter_name == "Jordan Avery"

    def test_a_dropped_dash_is_a_notice_not_a_refusal(self, read) -> None:  # type: ignore[no-untyped-def]
        """It reads as "no measurement" either way, so it must not block."""
        assert read.notices
        assert all("no cell was recognized" in p.message for p in read.notices)


# -- the header is the contract ---------------------------------------------


class TestHeader:
    def test_a_screenshot_without_a_header_is_refused(self) -> None:
        """Columns are read by name. Without the header there is no name, and
        guessing by position is how an exit speed becomes a spin rate."""
        read = read_table(
            grid([["#1", "78.0", "1599", "-", "5'", "-", "-", "68.5", "-", "27.2"]], header=False)
        )

        assert not read.rows
        assert "no column header found" in read.problems[0].message

    def test_a_stray_label_is_not_mistaken_for_a_header(self) -> None:
        cells = [Cell("PITCH SPEED", center_x=200, center_y=50, height=20)]
        assert read_table(cells).columns == []


# -- what it refuses ---------------------------------------------------------


class TestRefusals:
    def test_an_unreadable_cell_is_reported_not_guessed(self) -> None:
        read = read_table(grid([["#1", "7X.0", "1599", "-", "5'", "-", "-", "-", "-", "-"]]))

        assert [p.column for p in read.problems if p.column] == ["pitch_speed_mph"]
        assert read.rows[0].values["pitch_speed_mph"] is None

    def test_an_unreadable_measurement_withholds_the_whole_pitch(self) -> None:
        """An absent exit speed understates a best and skews an average, so a
        pitch whose exit speed could not be read must not be used at all."""
        read = read_table(grid([["#1", "78.0", "1599", "-", "5'", "-", "-", "8X.1", "-", "-"]]))

        assert [p.column for p in read.blocking_problems] == ["exit_speed_mph"]
        assert 1 in read.blocked_events

    def test_an_unreadable_context_cell_only_empties_that_cell(self) -> None:
        """Release height is context. Nothing computes from it, so losing one
        changes no number on an athlete's page -- withholding 60 good pitches
        over it would."""
        read = read_table(
            grid([["#1", "78.0", "1599", "-", "5'%\"", "-", "-", "88.1", "-", "12.0"]])
        )

        assert read.blocking_problems == []
        assert read.rows[0].values["release_height_ft"] is None
        assert read.rows[0].values["exit_speed_mph"] == 88.1
        assert any(p.column == "release_height_ft" for p in read.notices)

    def test_a_value_outside_its_range_is_refused(self) -> None:
        """115.0 mph off the bat is not a reading, it is a misread."""
        row = ["#1", "78.0", "1599", "-", "5'", "-", "-", "155.0", "-", "12.0"]
        read = read_table(grid([row]))

        problem = next(p for p in read.problems if p.column == "exit_speed_mph")
        assert "outside the plausible range" in problem.message
        assert read.rows[0].values["exit_speed_mph"] is None

    def test_a_dropped_decimal_point_is_caught_by_the_column_format(self) -> None:
        """The failure a range check cannot see: "2.8" read as "28" lands
        comfortably inside the plausible range. TrackMan prints this column to
        one decimal every time -- 250 values in the reference export, not one
        without -- so a reading with no decimal point lost it."""
        row = ["#1", "78.0", "1599", "-", "5'", "28", "-", "-", "-", "-"]
        read = read_table(grid([row]))

        problem = next(p for p in read.problems if p.column == "induced_vertical_movement_in")
        assert "no decimal point" in problem.message
        assert "probably 2.8" in problem.message
        # Suggested, never applied.
        assert read.rows[0].values["induced_vertical_movement_in"] is None

    def test_a_dropped_decimal_in_a_measurement_withholds_the_pitch(self) -> None:
        row = ["#1", "78.0", "1599", "-", "5'", "-", "-", "881", "-", "12.0"]
        read = read_table(grid([row]))

        assert [p.column for p in read.blocking_problems] == ["exit_speed_mph"]
        assert "probably 88.1" in read.blocking_problems[0].message

    def test_an_integer_column_is_not_suspected_of_losing_a_point(self) -> None:
        """Spin is always printed whole; 1599 is a reading, not a misread."""
        row = ["#1", "78.0", "1599", "-", "5'", "-", "-", "-", "-", "-"]
        read = read_table(grid([row]))

        assert read.rows[0].values["total_spin_rpm"] == 1599.0
        assert read.problems == [] or all(not p.blocking for p in read.problems)

    def test_a_gap_in_the_pitch_numbers_is_reported(self) -> None:
        """The check that catches a row OCR dropped entirely, which no
        per-cell validation can see."""
        rows = [
            ["#3", "78.0", "-", "-", "5'", "-", "-", "-", "-", "-"],
            ["#1", "77.0", "-", "-", "5'", "-", "-", "-", "-", "-"],
        ]
        read = read_table(grid(rows))

        assert any("#2 is missing" in p.message for p in read.blocking_problems)

    def test_a_repeated_pitch_number_is_reported(self) -> None:
        rows = [
            ["#1", "78.0", "-", "-", "5'", "-", "-", "-", "-", "-"],
            ["#1", "77.0", "-", "-", "5'", "-", "-", "-", "-", "-"],
        ]
        read = read_table(grid(rows))

        assert any("more than once" in p.message for p in read.blocking_problems)

    def test_a_row_with_no_pitch_number_is_skipped_quietly(self) -> None:
        """Footers and section labels are not pitches and are not errors."""
        rows = [
            ["#1", "78.0", "-", "-", "5'", "-", "-", "-", "-", "-"],
            ["Not assigned", "", "", "", "", "", "", "", "", ""],
        ]
        read = read_table(grid(rows))

        assert read.event_numbers == [1]


# -- value shapes ------------------------------------------------------------


class TestValues:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [("5'2\"", 5.1667), ("5'2'", 5.1667), ("5'2", 5.1667), ("4'9i", 4.75), ("5'", 5.0)],
    )
    def test_every_way_ocr_renders_an_inch_mark(self, text: str, expected: float) -> None:
        assert parse_feet(text) == pytest.approx(expected, abs=0.001)

    def test_a_clock_face_stays_a_clock_face(self) -> None:
        """Tilt is an axis, not a quantity; 12:45 is not 12.75."""
        assert parse_clock("12:45") == "12:45"
        assert parse_clock("1:00") == "1:00"
        assert parse_clock("13:00") is None

    @pytest.mark.parametrize(
        ("text", "expected"),
        [("77.4", 77.4), ("-3.1", -3.1), ("27.2°", 27.2), ("1599", 1599.0)],
    )
    def test_numbers_and_their_decorations(self, text: str, expected: float) -> None:
        assert parse_number(text) == expected

    @pytest.mark.parametrize("text", ["-", "", "abc", "5'2\""])
    def test_anything_else_is_not_a_number(self, text: str) -> None:
        assert parse_number(text) is None


# -- combining screenshots ---------------------------------------------------


class TestMerging:
    def row(self, event: int, speed: float) -> TableRow:
        return TableRow(event_number=event, values={"pitch_speed_mph": speed})

    def test_overlapping_screenshots_are_deduplicated(self) -> None:
        """A screen holds about fifteen pitches, so a session takes several and
        they overlap. The overlap is a second reading, not a duplicate pitch."""
        from bsa.domain.screenshot_table import TableRead

        first = TableRead(rows=[self.row(2, 78.0), self.row(1, 77.0)], columns=list(Column))
        second = TableRead(rows=[self.row(3, 79.0), self.row(2, 78.0)], columns=list(Column))
        merged = merge_reads([SourcedRead("a.png", first), SourcedRead("b.png", second)])

        assert [r.event_number for r in merged.rows] == [1, 2, 3]
        assert merged.ok

    def test_two_screenshots_disagreeing_withhold_the_pitch(self) -> None:
        """One of them is wrong and there is no basis for choosing."""
        from bsa.domain.screenshot_table import TableRead

        first = TableRead(rows=[self.row(1, 78.0)], columns=list(Column))
        second = TableRead(rows=[self.row(1, 88.0)], columns=list(Column))
        merged = merge_reads([SourcedRead("a.png", first), SourcedRead("b.png", second)])

        assert merged.rows == []
        assert any("but" in p.message and "same pitch" in p.message for p in merged.problems)

    def test_a_problem_names_the_screenshot_it_came_from(self) -> None:
        from bsa.domain.screenshot_table import TableRead

        read = TableRead(problems=[RowProblem(1, "pitch_speed_mph", "unreadable")])
        merged = merge_reads([SourcedRead("second-half.png", read)])

        assert merged.problems[0].message.startswith("second-half.png: ")
