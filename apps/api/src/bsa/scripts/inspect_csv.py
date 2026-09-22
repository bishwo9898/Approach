"""Inspect a TrackMan export and report what we can and cannot read.

    python -m bsa.scripts.inspect_csv path/to/export.csv

Run this first on a real export. It never writes to the database and never
guesses a mapping -- it tells you which columns are present, whether a known
schema matches, and prints a starter `ColumnMap` to paste into
`bsa/integrations/trackman/mapping.py`.

The point is to turn "the import failed, call a developer" into "here is
exactly what the file contains", which is most of the work of adding support
for a real schema.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

from bsa.integrations.trackman.mapping import COLUMN_MAPS, ColumnMap

#: Column names we would expect to find, by the domain field they would feed.
#: Used only to suggest a starting point for a human to check -- never applied.
_HINTS: dict[str, tuple[str, ...]] = {
    "session id": ("sessionuid", "sessionid", "gameuid", "gameid"),
    "session date": ("sessiondate", "date", "utcdate", "localdate"),
    "event id": ("pitchuid", "pitchid", "playid", "eventid"),
    "pitcher id": ("pitcherid", "pitcher", "pitcherguid"),
    "batter id": ("batterid", "batter", "batterguid"),
    "pitch velocity": ("relspeed", "releasespeed", "pitchspeed", "velocity"),
    "spin rate": ("spinrate", "releasespinrate"),
    "exit velocity": ("exitspeed", "exitvelocity", "launchspeed"),
    "launch angle": ("angle", "launchangle"),
    "distance": ("distance", "hitdistance", "carry"),
    "pitch type": ("taggedpitchtype", "autopitchtype", "pitchtype"),
    "pitch call": ("pitchcall", "call", "result"),
}


def _key(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _match_known_schema(headers: list[str]) -> ColumnMap | None:
    present = {h.strip() for h in headers}
    for column_map in COLUMN_MAPS.values():
        if column_map.required <= present:
            return column_map
    return None


def _suggest(headers: list[str]) -> list[tuple[str, str]]:
    """Columns that *look* like ones we need. Suggestions only."""
    by_key = {_key(h): h for h in headers}
    found: list[tuple[str, str]] = []
    for label, candidates in _HINTS.items():
        for candidate in candidates:
            if candidate in by_key:
                found.append((label, by_key[candidate]))
                break
    return found


def inspect(path: Path, *, show_sample: bool = True) -> int:
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        print(f"This file is not valid UTF-8 text: {exc}", file=sys.stderr)
        return 1

    reader = csv.DictReader(io.StringIO(text))
    headers = list(reader.fieldnames or [])
    if not headers:
        print("This file has no header row, so nothing can be read from it.")
        return 1

    rows = list(reader)

    print(f"\nFile:    {path.name}")
    print(f"Rows:    {len(rows)}")
    print(f"Columns: {len(headers)}\n")

    known = _match_known_schema(headers)
    if known is not None:
        print(f"  This matches the registered schema '{known.version}'.")
        print("  It can be imported as-is.\n")
        return 0

    print("  No registered schema matches this file, so it cannot be imported yet.")
    print("  Nothing was guessed -- a misread column produces numbers that look fine.\n")

    print("Columns found:")
    for header in headers:
        filled = sum(1 for row in rows if (row.get(header) or "").strip())
        note = "" if filled else "   (always empty)"
        print(f"  - {header}{note}")

    suggestions = _suggest(headers)
    if suggestions:
        print("\nColumns that look like ones we need (verify each -- these are guesses):")
        width = max(len(label) for label, _ in suggestions)
        for label, header in suggestions:
            print(f"  {label:<{width}}  ->  {header}")

    missing = [label for label in _HINTS if label not in {s[0] for s in suggestions}]
    if missing:
        print("\nNo obvious candidate for:")
        for label in missing:
            print(f"  - {label}")

    if show_sample and rows:
        print("\nFirst row:")
        for header in headers:
            value = (rows[0].get(header) or "").strip()
            print(f"  {header} = {value!r}")

    print("\n" + "-" * 70)
    print("Next step: add a ColumnMap to")
    print("  apps/api/src/bsa/integrations/trackman/mapping.py")
    print("using the real column names above, then register it in COLUMN_MAPS.")
    print("Nothing outside that file needs to change.")
    print("-" * 70 + "\n")
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report what a TrackMan export contains. Reads only; writes nothing."
    )
    parser.add_argument("path", type=Path, help="CSV file to inspect")
    parser.add_argument(
        "--no-sample", action="store_true", help="do not print the first row's values"
    )
    args = parser.parse_args()

    if not args.path.exists():
        print(f"error: {args.path} does not exist", file=sys.stderr)
        return 1
    return inspect(args.path, show_sample=not args.no_sample)


if __name__ == "__main__":
    raise SystemExit(main())
