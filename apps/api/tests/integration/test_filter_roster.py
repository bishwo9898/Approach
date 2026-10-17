"""Safely reducing the active roster without deleting athlete history."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from bsa.db.models import Organization, UserSession
from bsa.domain.enums import Role
from bsa.scripts.filter_roster import (
    RosterEntry,
    RosterResolutionError,
    apply_plan,
    build_plan,
    resolve_entries,
)
from tests.conftest import make_player, make_user


def test_filter_deactivates_non_roster_players_accounts_and_sessions(
    db: Session, organization: Organization
) -> None:
    kept = make_player(db, organization, first_name="Kept", last_name="Athlete")
    removed = make_player(db, organization, first_name="Former", last_name="Athlete")
    kept_user = make_user(db, organization, subject="kept", role=Role.PLAYER, player=kept)
    removed_user = make_user(db, organization, subject="removed", role=Role.PLAYER, player=removed)
    coach = make_user(db, organization, subject="coach", role=Role.COACH)
    session = UserSession(
        user_id=removed_user.id,
        token_hash="a" * 64,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add(session)
    db.flush()

    selected = resolve_entries(db, organization, [RosterEntry("Kept", "Athlete")])
    plan = build_plan(db, organization, selected)
    apply_plan(db, organization, plan)
    db.flush()

    assert plan.deactivate_players == 1
    assert plan.deactivate_accounts == 1
    assert plan.revoke_sessions == 1
    assert kept.active is True
    assert removed.active is False
    assert kept_user.active is True
    assert removed_user.active is False
    assert coach.active is True
    assert session.revoked_at is not None


def test_shared_name_requires_a_disambiguator(db: Session, organization: Organization) -> None:
    older = make_player(db, organization, first_name="Shared", last_name="Name")
    younger = make_player(db, organization, first_name="Shared", last_name="Name")
    older.date_of_birth = date(2008, 1, 1)
    younger.date_of_birth = date(2012, 1, 1)
    db.flush()

    with pytest.raises(RosterResolutionError, match="matched 2 athletes"):
        resolve_entries(db, organization, [RosterEntry("Shared", "Name")])

    selected = resolve_entries(
        db,
        organization,
        [RosterEntry("Shared", "Name", date_of_birth=date(2012, 1, 1))],
    )
    assert selected == frozenset({younger.id})
