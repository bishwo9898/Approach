"""Writes the synthetic sample exports committed under `samples/trackman/`.

Regenerate with:  python -m bsa.scripts.make_samples

Every file is fictional. These exist so a new developer can run a real import
without TrackMan credentials, and so the documented schema always has a
concrete example next to it.
"""

from __future__ import annotations

import csv
import io
import sys
from datetime import date
from pathlib import Path

from bsa.scripts.paths import repo_root, samples_dir
from bsa.scripts.synthetic import ATHLETES, build_day_csv, rows_to_csv

SAMPLE_DATE = date(2026, 9, 12)
HISTORY_START = date(2026, 6, 1)


def write_samples(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def emit(name: str, data: bytes) -> None:
        path = out_dir / name
        path.write_bytes(data)
        written.append(path)

    # A normal day's export across the whole roster.
    emit(
        "session_2026-09-12_preliminary.csv",
        build_day_csv(ATHLETES, SAMPLE_DATE, history_start=HISTORY_START),
    )

    # The same sessions, republished as verified with corrected values. Used to
    # demonstrate reconciliation: same session ids, no duplicate rows.
    emit(
        "session_2026-09-12_verified.csv",
        build_day_csv(
            ATHLETES,
            SAMPLE_DATE,
            history_start=HISTORY_START,
            verified=True,
            velocity_bonus={a.external_id: -0.8 for a in ATHLETES},
        ),
    )

    # A file containing an athlete we have no mapping for, to exercise the
    # identity-resolution queue.
    unknown = build_day_csv(ATHLETES[:1], SAMPLE_DATE, history_start=HISTORY_START)
    emit(
        "session_2026-09-12_unknown_player.csv",
        unknown.replace(b"TM-100241", b"TM-999999"),
    )

    # A deliberately malformed file: a missing session id, an unparseable date
    # and an impossible velocity, alongside rows that must still be accepted.
    # Built through the csv module -- these rows contain quoted commas.
    source = build_day_csv([ATHLETES[0]], SAMPLE_DATE, history_start=HISTORY_START)
    reader = csv.DictReader(io.StringIO(source.decode()))
    fieldnames = list(reader.fieldnames or [])
    good_rows = [dict(r) for r in reader][:5]

    bad_session = {**good_rows[0], "SessionUID": "", "PitchUID": "BAD-1"}
    bad_date = {**good_rows[1], "SessionDate": "not-a-date", "PitchUID": "BAD-2"}
    bad_velocity = {**good_rows[2], "RelSpeed": "268.0", "PitchUID": "BAD-3"}

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows([*good_rows, bad_session, bad_date, bad_velocity])
    emit("session_2026-09-12_malformed.csv", buffer.getvalue().encode())

    # A header we do not recognize at all.
    emit(
        "unknown_schema.csv",
        b"Alpha,Beta,Gamma\n1,2,3\n",
    )

    # Empty roster day: a valid header with no rows.
    emit("empty_session.csv", rows_to_csv([]))

    return written


def main() -> int:
    root = samples_dir()
    for path in write_samples(root):
        print(f"wrote {path.relative_to(repo_root())} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
