"""Facility-local time.

"What did Jake do today?" means today at the facility, not today in UTC. A
7pm session in New York is already tomorrow in UTC, so a UTC-based "today" shows
a coach an empty dashboard every evening -- exactly when they are most likely to
be looking at it.

Every calendar-date default in the application resolves through here, using the
organization's own timezone.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bsa.core.logging import get_logger

log = get_logger(__name__)


def resolve_zone(timezone_name: str | None) -> ZoneInfo | timezone:
    """Resolve an IANA timezone, falling back to UTC rather than failing.

    A misconfigured timezone should make dates slightly wrong, not take the
    dashboard down.
    """
    if not timezone_name:
        return UTC
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("clock.unknown_timezone", timezone=timezone_name)
        return UTC


def today_in(timezone_name: str | None) -> date:
    """The current calendar date at the facility."""
    return datetime.now(resolve_zone(timezone_name)).date()
