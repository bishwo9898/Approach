"""Unit conversion."""

from __future__ import annotations

from datetime import UTC

import pytest

from bsa.core.units import Unit, UnitConversionError, convert, format_value, supports


def test_identity_conversions_are_explicit() -> None:
    """Even a no-op conversion must be declared, so the path is always exercised."""
    assert convert(88.4, "mph", Unit.MPH) == 88.4


def test_metric_velocity_converts_to_mph() -> None:
    assert convert(40.0, "m/s", Unit.MPH) == pytest.approx(89.477, abs=0.01)
    assert convert(144.0, "km/h", Unit.MPH) == pytest.approx(89.477, abs=0.01)


def test_feet_convert_to_inches() -> None:
    assert convert(1.5, "ft", Unit.INCHES) == 18.0


def test_unsupported_conversion_raises_rather_than_guessing() -> None:
    """Guessing a factor produces plausible numbers nobody catches."""
    with pytest.raises(UnitConversionError, match="no supported conversion"):
        convert(10.0, "furlongs", Unit.MPH)

    assert not supports("furlongs", Unit.MPH)


def test_unit_names_are_case_and_space_insensitive() -> None:
    assert convert(10.0, " MPH ", Unit.MPH) == 10.0


def test_formatting_always_carries_the_unit() -> None:
    assert format_value(87.34, Unit.MPH) == "87.3 mph"
    assert format_value(2184.6, Unit.RPM) == "2185 rpm"
    assert format_value(64.2, Unit.PERCENT) == "64.2%"


def test_facility_timezone_drives_today_not_utc() -> None:
    """A 7pm New York session must not land on tomorrow's dashboard.

    UTC has already rolled over by then, so a UTC-based "today" would show the
    coach an empty page at exactly the moment they are looking at it.
    """
    from datetime import datetime
    from unittest.mock import patch
    from zoneinfo import ZoneInfo

    from bsa.core.clock import resolve_zone, today_in

    # 2026-09-13 02:45 UTC == 2026-09-12 22:45 in New York.
    instant = datetime(2026, 9, 13, 2, 45, tzinfo=UTC)

    with patch("bsa.core.clock.datetime") as clock:
        clock.now.side_effect = lambda tz: instant.astimezone(tz)
        assert today_in("America/New_York").isoformat() == "2026-09-12"
        assert today_in("UTC").isoformat() == "2026-09-13"

    assert resolve_zone("America/New_York") == ZoneInfo("America/New_York")
    # A misconfigured timezone degrades to UTC rather than taking the API down.
    assert resolve_zone("Not/AZone") is UTC
    assert resolve_zone(None) is UTC


def test_repo_root_is_found_by_marker_not_by_counting() -> None:
    """Guards a bug that has already shipped twice.

    Counting `.parents[n]` by hand wrote generated files into a plausible but
    wrong directory, silently, in two separate scripts. This asserts the root is
    located by a marker file instead.
    """
    from bsa.scripts.paths import repo_root, samples_dir, shared_dir

    root = repo_root()
    assert (root / "pnpm-workspace.yaml").exists()
    assert (root / "apps" / "api" / "pyproject.toml").exists()
    assert samples_dir() == root / "samples" / "trackman"
    assert shared_dir() == root / "packages" / "shared"
