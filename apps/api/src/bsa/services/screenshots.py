"""Turning TrackMan screenshots into a CSV the ingestion pipeline can read.

The pipeline, end to end:

    images -> OCR -> table per image -> merged by pitch number -> CSV -> stored

Everything that decides anything lives in `bsa.domain.screenshot_table`, which
is pure and tested against real screenshots. This module does the parts that
touch the world: running an OCR engine over files, writing the CSV, and keeping
both the screenshots and the CSV in the object store.

Why both are kept: the CSV is what the rest of the system reads, and the
screenshots are the only evidence of what it was derived from. If a number is
ever disputed, the image it came from has to still exist.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from bsa.core.logging import get_logger
from bsa.domain.screenshot_table import (
    Cell,
    MergedTable,
    RowProblem,
    SourcedRead,
    merge_reads,
    read_table,
)
from bsa.integrations.ocr import OcrEngine
from bsa.integrations.ocr.base import OcrUnavailableError
from bsa.integrations.storage import ObjectStore

log = get_logger(__name__)

#: The live at-bat schema, in the order the CSV writes it. Matches what
#: `bsa.integrations.trackman.live_atbat` expects, so a converted screenshot
#: enters the system through exactly the same path as a vendor-supplied file.
CSV_COLUMNS = [
    "player_name",
    "opponent_name",
    "session_date_display",
    "session_time_display",
    "competition",
    "pitch_set",
    "event_number",
    "pitch_speed_mph",
    "total_spin_rpm",
    "tilt_clock",
    "release_height_ft",
    "induced_vertical_movement_in",
    "horizontal_movement_in",
    "exit_speed_mph",
    "hit_spin_rate_rpm",
    "launch_angle_deg",
    "pitch_type",
    "hit_type",
    "source_image",
]


@dataclass(frozen=True, slots=True)
class UploadedImage:
    filename: str
    data: bytes


@dataclass(slots=True)
class ConversionResult:
    """What came out, and everything that was not believed on the way."""

    csv_text: str
    pitches: int
    batted_balls: int
    #: Where the CSV was archived, for re-reading or re-ingesting later.
    csv_key: str | None = None
    image_keys: list[str] = field(default_factory=list)
    problems: list[RowProblem] = field(default_factory=list)
    batter_name: str | None = None
    first_pitch: int | None = None
    last_pitch: int | None = None

    @property
    def blocking_problems(self) -> list[RowProblem]:
        return [p for p in self.problems if p.blocking]

    @property
    def notices(self) -> list[RowProblem]:
        return [p for p in self.problems if not p.blocking]

    @property
    def ok(self) -> bool:
        return self.pitches > 0 and not self.blocking_problems


def _cells(engine: OcrEngine, path: Path) -> list[Cell]:
    return [
        Cell(
            text=line.text,
            center_x=line.center_x,
            center_y=line.center_y,
            height=line.height,
        )
        for line in engine.read(path)
    ]


def read_images(engine: OcrEngine, images: list[UploadedImage]) -> MergedTable:
    """Recognize every screenshot and reconcile them into one table."""
    reads: list[SourcedRead] = []
    with TemporaryDirectory() as workspace:
        for image in images:
            # Written to disk because OCR engines take a path: Vision needs a
            # CGImageSource and Tesseract shells out.
            path = Path(workspace) / Path(image.filename).name
            path.write_bytes(image.data)
            try:
                reads.append(SourcedRead(image.filename, read_table(_cells(engine, path))))
            except OcrUnavailableError:
                # The engine itself cannot run. That is not a bad screenshot
                # and must not be reported as one.
                raise
            except Exception as exc:  # pragma: no cover -- engine-specific failure
                log.warning("screenshot.unreadable", filename=image.filename, error=str(exc))
                reads.append(SourcedRead(image.filename, read_table([])))
    return merge_reads(reads)


def to_csv(
    table: MergedTable,
    *,
    player_name: str,
    session_date: date,
    opponent_name: str = "",
    session_time: str = "",
    competition: str = "",
) -> str:
    """Write the merged table in the live at-bat CSV shape.

    Only pitches that survived validation are written. A pitch that could not
    be read is absent from the file and present in the problem list, which is
    the only honest pair of places for it to be.

    There is no `marker_shape` column. The shape is not a measurement, and the
    one time this project derived numbers from it, it told an athlete how many
    swings they had missed from data that does not record swings.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()

    for row in sorted(table.rows, key=lambda r: r.event_number):
        record = dict.fromkeys(CSV_COLUMNS, "")
        record["player_name"] = player_name
        record["opponent_name"] = opponent_name
        record["session_date_display"] = session_date.strftime("%b %-d")
        record["session_time_display"] = session_time
        record["competition"] = competition
        record["event_number"] = str(row.event_number)
        record["source_image"] = table.source_of.get(row.event_number, "")
        for column, value in row.values.items():
            # TrackMan's own "absent" marker, so the file reads the way a
            # vendor-supplied one does.
            record[column] = "-" if value is None else _format(column, value)
        writer.writerow(record)

    return buffer.getvalue()


#: Decimal places per column, matching how TrackMan prints each one. Writing
#: "79" where the vendor writes "79.0" parses to the same number, but a file
#: that is textually identical to a vendor export is one fewer thing to wonder
#: about when the two are compared.
_PLACES = {
    "pitch_speed_mph": 1,
    "total_spin_rpm": 0,
    "release_height_ft": 4,
    "induced_vertical_movement_in": 1,
    "horizontal_movement_in": 1,
    "exit_speed_mph": 1,
    "hit_spin_rate_rpm": 0,
    "launch_angle_deg": 1,
}


def _format(column: str, value: float | str) -> str:
    if isinstance(value, str):
        return value  # a clock face
    return f"{value:.{_PLACES.get(column, 1)}f}"


def convert(
    engine: OcrEngine,
    store: ObjectStore,
    images: list[UploadedImage],
    *,
    player_name: str,
    session_date: date,
    opponent_name: str = "",
    session_time: str = "",
    competition: str = "",
    archive_prefix: str = "screenshots",
) -> ConversionResult:
    """Convert a set of screenshots and archive everything involved."""
    table = read_images(engine, images)
    csv_text = to_csv(
        table,
        player_name=player_name,
        session_date=session_date,
        opponent_name=opponent_name,
        session_time=session_time,
        competition=competition,
    )

    stamp = session_date.isoformat()
    folder = f"{archive_prefix}/{stamp}"
    image_keys = [
        store.put(f"{folder}/{Path(image.filename).name}", image.data) for image in images
    ]
    csv_key = store.put(f"{folder}/pitches.csv", csv_text.encode("utf-8"))

    events = [row.event_number for row in table.rows]
    batted = sum(1 for row in table.rows if row.values.get("exit_speed_mph") is not None)

    log.info(
        "screenshot.converted",
        images=len(images),
        pitches=len(table.rows),
        batted_balls=batted,
        blocking=len(table.blocking_problems),
    )
    return ConversionResult(
        csv_text=csv_text,
        pitches=len(table.rows),
        batted_balls=batted,
        csv_key=csv_key,
        image_keys=image_keys,
        problems=table.problems,
        batter_name=table.batter_name,
        first_pitch=min(events) if events else None,
        last_pitch=max(events) if events else None,
    )
