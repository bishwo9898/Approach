"""Provisioning a roster export into athletes and accounts.

The unit tests in `test_roster_plan.py` decide *what* should happen. These
check what actually lands in the database, and in particular the one operation
here that can destroy data: folding two athlete records into one when a later
run decides they were always the same person.

Every athlete is invented. The real export is gitignored.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from bsa.core.password import hash_password
from bsa.db.models import (
    ExternalPlayerIdentity,
    HitEvent,
    Organization,
    Player,
    TrainingSession,
    User,
    UserCredential,
)
from bsa.domain.enums import Role, SourceStatus
from bsa.domain.roster import EmailPolicy, plan_export
from bsa.scripts.provision_roster import apply_plan

pytestmark = pytest.mark.integration

DOMAIN = "approach.com"


def record(name: str, dob: str, player_id: str) -> dict[str, str]:
    return {
        "name": name,
        "dateOfBirth": dob,
        "number": "-",
        "team": "-",
        "playerId": f"{player_id} TrackMan",
    }


def provision(
    db: Session,
    organization: Organization,
    records: list[dict[str, str]],
    *,
    merge_duplicates: bool = True,
    policy: EmailPolicy = EmailPolicy.BIRTH_YEAR,
):  # type: ignore[no-untyped-def]
    plan, skipped = plan_export(
        records, domain=DOMAIN, policy=policy, merge_duplicates=merge_duplicates
    )
    outcome = apply_plan(
        db, organization, plan, link_existing=False, issue_codes=False, skipped=skipped
    )
    db.flush()
    return outcome


def players(db: Session, organization: Organization) -> list[Player]:
    return list(
        db.scalars(
            select(Player)
            .where(Player.organization_id == organization.id, Player.active.is_(True))
            .order_by(Player.last_name, Player.first_name)
        )
    )


def identities_of(db: Session, player: Player) -> set[str]:
    return {
        i.external_id
        for i in db.scalars(
            select(ExternalPlayerIdentity).where(ExternalPlayerIdentity.player_id == player.id)
        )
    }


def give_data_to(db: Session, organization: Organization, player: Player) -> None:
    """One imported batted ball, so `_carries_data` has something to find."""
    session = TrainingSession(
        organization_id=organization.id,
        provider="trackman",
        external_session_id=f"session-{uuid.uuid4().hex[:8]}",
        session_date=date(2026, 9, 22),
        imported_at=datetime.now(UTC),
        source_status=SourceStatus.VERIFIED,
    )
    db.add(session)
    db.flush()
    db.add(
        HitEvent(
            organization_id=organization.id,
            session_id=session.id,
            player_id=player.id,
            external_event_id=f"hit-{uuid.uuid4().hex[:8]}",
            exit_velocity_mph=92.0,
            source_status=SourceStatus.VERIFIED,
        )
    )
    db.flush()


def give_account_to(db: Session, organization: Organization, player: Player) -> User:
    """An account for an athlete the planner refused to issue one to.

    Needed because the duplicate pairs are exactly the rows whose name collided,
    so provisioning deliberately left them without an address.
    """
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        organization_id=organization.id,
        auth_provider="local",
        auth_subject=str(user_id),
        email=f"{user_id.hex[:8]}@approach.com",
        display_name=player.display_name,
        role=Role.PLAYER,
        player_id=player.id,
    )
    db.add(user)
    db.add(UserCredential(user_id=user_id))
    db.flush()
    return user


def account_for(db: Session, player: Player) -> User | None:
    return db.scalars(
        select(User).where(User.player_id == player.id, User.active.is_(True))
    ).first()


TWO_ROWS_ONE_PERSON = [
    record("Riley Chen", "Feb. 24  2015", "11"),
    record("Riley Chen", "Feb. 24  2015", "22"),
]


class TestProvisioning:
    def test_creates_an_athlete_an_identity_and_an_account(
        self, db: Session, organization: Organization
    ) -> None:
        outcome = provision(db, organization, [record("Jordan Avery", "Jan. 1  2010", "11")])

        assert outcome.players_created == 1
        assert outcome.accounts_created == 1
        found = players(db, organization)
        assert len(found) == 1
        assert identities_of(db, found[0]) == {"11"}

        user = account_for(db, found[0])
        assert user is not None
        assert user.email == "jordan.avery@approach.com"
        # Provisioned, never claimed: that is the normal starting state.
        credential = db.get(UserCredential, user.id)
        assert credential is not None and not credential.has_password

    def test_re_running_changes_nothing(self, db: Session, organization: Organization) -> None:
        records = [
            record("Jordan Avery", "Jan. 1  2010", "11"),
            record("Sam Okafor", "Feb. 2  2011", "22"),
        ]
        provision(db, organization, records)
        again = provision(db, organization, records)

        assert again.players_created == 0
        assert again.identities_created == 0
        assert again.accounts_created == 0
        assert again.accounts_existing == 2
        assert len(players(db, organization)) == 2

    def test_two_rows_for_one_person_become_one_athlete(
        self, db: Session, organization: Organization
    ) -> None:
        """Both TrackMan ids land on the same athlete, which is the point:
        data filed under either one reaches the same person."""
        outcome = provision(db, organization, TWO_ROWS_ONE_PERSON)

        assert outcome.players_created == 1
        assert outcome.identities_created == 2
        found = players(db, organization)
        assert len(found) == 1
        assert identities_of(db, found[0]) == {"11", "22"}

    def test_an_athlete_with_no_address_still_exists(
        self, db: Session, organization: Organization
    ) -> None:
        """Their sessions must still import; only the login is withheld."""
        outcome = provision(
            db,
            organization,
            [
                record("Devin Ruiz", "May. 24  2009", "11"),
                record("Devin Ruiz", "Jul. 24  2009", "22"),
            ],
        )
        assert outcome.players_created == 2
        assert len(outcome.blocked) == 2
        assert all(account_for(db, p) is None for p in players(db, organization))


class TestFoldingDuplicateRecords:
    """When an earlier run split one person across two athlete records.

    That is exactly what happened here: the roster was provisioned before the
    facility confirmed that an identical name and birth date means TrackMan
    entered the same athlete twice.
    """

    @pytest.fixture
    def already_split(self, db: Session, organization: Organization) -> list[Player]:
        provision(db, organization, TWO_ROWS_ONE_PERSON, merge_duplicates=False)
        found = players(db, organization)
        assert len(found) == 2, "fixture must start from two separate records"
        return found

    def test_the_records_are_folded_into_one(
        self, db: Session, organization: Organization, already_split: list[Player]
    ) -> None:
        outcome = provision(db, organization, TWO_ROWS_ONE_PERSON)

        assert outcome.players_folded == 1
        assert not outcome.merge_blocked
        remaining = players(db, organization)
        assert len(remaining) == 1
        assert identities_of(db, remaining[0]) == {"11", "22"}

    def test_the_retired_record_is_deactivated_not_deleted(
        self, db: Session, organization: Organization, already_split: list[Player]
    ) -> None:
        provision(db, organization, TWO_ROWS_ONE_PERSON)
        retired = [
            p
            for p in db.scalars(select(Player).where(Player.organization_id == organization.id))
            if not p.active
        ]
        assert len(retired) == 1

    def test_the_retired_account_is_deactivated_and_unlinked(
        self, db: Session, organization: Organization, already_split: list[Player]
    ) -> None:
        """Deactivated rather than deleted, so the address stays taken and
        cannot be re-issued to somebody else."""
        give_account_to(db, organization, already_split[0])
        give_account_to(db, organization, already_split[1])

        provision(db, organization, TWO_ROWS_ONE_PERSON)

        dormant = db.scalars(select(User).where(User.active.is_(False))).all()
        assert len(dormant) == 1
        assert dormant[0].player_id is None
        assert account_for(db, players(db, organization)[0]) is not None

    def test_the_record_carrying_data_is_the_one_that_survives(
        self, db: Session, organization: Organization, already_split: list[Player]
    ) -> None:
        keeper = already_split[1]
        give_data_to(db, organization, keeper)

        provision(db, organization, TWO_ROWS_ONE_PERSON)

        remaining = players(db, organization)
        assert len(remaining) == 1
        assert remaining[0].id == keeper.id
        assert identities_of(db, remaining[0]) == {"11", "22"}

    def test_it_refuses_when_both_records_carry_data(
        self, db: Session, organization: Organization, already_split: list[Player]
    ) -> None:
        """Moving sessions from one athlete to another is not this script's
        call. It says so and leaves both alone."""
        for player in already_split:
            give_data_to(db, organization, player)

        outcome = provision(db, organization, TWO_ROWS_ONE_PERSON)

        assert outcome.players_folded == 0
        assert len(outcome.merge_blocked) == 1
        assert outcome.merge_blocked[0][1] == "carries imported data"
        assert len(players(db, organization)) == 2

    def test_it_refuses_to_retire_an_account_somebody_is_using(
        self, db: Session, organization: Organization, already_split: list[Player]
    ) -> None:
        """Taking away a login in use is not a side effect of re-running a
        provisioning script."""
        # The first record is the survivor (both are empty, so the oldest wins),
        # so claiming the second is claiming the one that would be retired.
        claimed = give_account_to(db, organization, already_split[1])
        credential = db.get(UserCredential, claimed.id)
        assert credential is not None
        credential.password_hash = hash_password("RisingFastball26")
        credential.password_set_at = datetime.now(UTC)
        db.flush()

        outcome = provision(db, organization, TWO_ROWS_ONE_PERSON)

        assert outcome.players_folded == 0
        assert [reason for _, reason in outcome.merge_blocked] == ["has a claimed account"]
        assert len(players(db, organization)) == 2
        assert account_for(db, already_split[1]) is not None
