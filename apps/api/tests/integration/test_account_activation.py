"""Claiming a provisioned account, then signing in with it.

The flow under test, end to end through the real API:

    provisioned (no password) -> lookup email -> set password -> sign in

Two properties matter more than the happy path and are tested hardest:

* setting a password does not trust that the lookup succeeded, and
* a session token is a credential -- it expires, it can be revoked, and holding
  one still does not let its owner read another athlete's data.

Every athlete here is invented. Real names live in a gitignored export.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from bsa.api.app import create_app
from bsa.api.v1 import auth as auth_routes
from bsa.core.config import Settings, SignupGate, get_settings
from bsa.core.password import hash_password
from bsa.core.tokens import hash_session_token
from bsa.db.models import Organization, Player, User, UserCredential, UserSession
from bsa.db.session import get_db
from bsa.domain.enums import Role
from bsa.services import accounts
from tests.conftest import make_player

pytestmark = pytest.mark.integration

PASSWORD = "RisingFastball26"
OTHER_PASSWORD = "SecondBaseman42"


@pytest.fixture(autouse=True)
def clear_rate_limits() -> None:
    """The limiters are process-wide, so one test must not exhaust another's."""
    auth_routes._LOOKUP_LIMIT.reset()
    auth_routes._LOGIN_LIMIT.reset()


def settings_for(gate: SignupGate = SignupGate.OPEN) -> Settings:
    return Settings(
        env="development",
        auth_provider="local",
        signup_gate=gate,
        account_email_domain="approach.com",
        login_max_attempts=3,
        login_lockout_minutes=15,
    )


@pytest.fixture
def gate() -> SignupGate:
    """Overridden by the activation-code tests via indirect parametrization."""
    return SignupGate.OPEN


@pytest.fixture
def client(db: Session, gate: SignupGate):  # type: ignore[no-untyped-def]
    """The real app, with only the database swapped for the test transaction.

    `get_principal` and the auth provider are deliberately not stubbed: they are
    the things under test.
    """
    settings = settings_for(gate)
    app = create_app(settings)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def provision(
    db: Session,
    organization: Organization,
    *,
    email: str,
    display_name: str = "Jordan Avery",
    role: Role = Role.PLAYER,
    player: Player | None = None,
    password: str | None = None,
    active: bool = True,
) -> User:
    """An account exactly as the roster provisioner would create it."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        organization_id=organization.id,
        auth_provider="local",
        auth_subject=str(user_id),
        email=accounts.normalize_email(email),
        display_name=display_name,
        role=role,
        player_id=player.id if player else None,
        active=active,
    )
    db.add(user)
    db.flush()
    credential = UserCredential(user_id=user.id)
    if password is not None:
        credential.password_hash = hash_password(password)
        credential.password_set_at = datetime.now(UTC)
    db.add(credential)
    db.flush()
    return user


@pytest.fixture
def athlete(db: Session, organization: Organization) -> Player:
    return make_player(
        db, organization, first_name="Jordan", last_name="Avery", external_id="TM-ROSTER-1"
    )


@pytest.fixture
def unclaimed(db: Session, organization: Organization, athlete: Player) -> User:
    return provision(db, organization, email="jordan.avery@approach.com", player=athlete)


# -- step one: does this address exist? --------------------------------------


class TestEmailLookup:
    def test_a_roster_address_is_recognized(self, client: TestClient, unclaimed: User) -> None:
        response = client.post(
            "/api/v1/auth/activation/lookup", json={"email": "jordan.avery@approach.com"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == "jordan.avery@approach.com"
        assert body["first_name"] == "Jordan"
        assert body["requires_code"] is False
        assert body["password_rules"], "the form must show the rules the server enforces"

    def test_an_unknown_address_is_told_so(self, client: TestClient, unclaimed: User) -> None:
        """The one deliberate disclosure: a person given their address verbally
        cannot fix a typo if the only feedback is "something was wrong"."""
        response = client.post(
            "/api/v1/auth/activation/lookup", json={"email": "nobody@approach.com"}
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "email_not_recognized"
        assert response.json()["error"]["message"] == "Email does not match."

    def test_capitalization_and_spacing_do_not_matter(
        self, client: TestClient, unclaimed: User
    ) -> None:
        response = client.post(
            "/api/v1/auth/activation/lookup", json={"email": "  Jordan.Avery@Approach.com "}
        )
        assert response.status_code == 200

    def test_a_deactivated_account_cannot_be_claimed(
        self, client: TestClient, db: Session, organization: Organization
    ) -> None:
        provision(db, organization, email="gone@approach.com", active=False)
        response = client.post(
            "/api/v1/auth/activation/lookup", json={"email": "gone@approach.com"}
        )
        assert response.status_code == 404

    def test_an_already_claimed_account_is_sent_to_sign_in(
        self, client: TestClient, db: Session, organization: Organization
    ) -> None:
        provision(db, organization, email="taken@approach.com", password=PASSWORD)
        response = client.post(
            "/api/v1/auth/activation/lookup", json={"email": "taken@approach.com"}
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "already_activated"

    def test_a_malformed_address_is_rejected_before_any_lookup(self, client: TestClient) -> None:
        assert (
            client.post("/api/v1/auth/activation/lookup", json={"email": "not-an-email"})
        ).status_code == 422


# -- step two: choose a password ---------------------------------------------


class TestSettingAPassword:
    def test_a_password_can_be_set_and_then_used(
        self, client: TestClient, db: Session, unclaimed: User
    ) -> None:
        setup = client.post(
            "/api/v1/auth/activation/complete",
            json={
                "email": "jordan.avery@approach.com",
                "password": PASSWORD,
                "password_confirmation": PASSWORD,
            },
        )
        assert setup.status_code == 204

        credential = db.get(UserCredential, unclaimed.id)
        assert credential is not None
        assert credential.has_password
        assert PASSWORD not in (credential.password_hash or "")

        signin = client.post(
            "/api/v1/auth/login",
            json={"email": "jordan.avery@approach.com", "password": PASSWORD},
        )
        assert signin.status_code == 200
        assert signin.json()["role"] == "PLAYER"

    def test_setting_a_password_does_not_sign_you_in(
        self, client: TestClient, unclaimed: User
    ) -> None:
        """Asked for deliberately: using the password immediately is how someone
        finds out straight away that they can reproduce it."""
        response = client.post(
            "/api/v1/auth/activation/complete",
            json={
                "email": "jordan.avery@approach.com",
                "password": PASSWORD,
                "password_confirmation": PASSWORD,
            },
        )
        assert response.status_code == 204
        assert not response.content

    def test_mismatched_confirmation_is_rejected(self, client: TestClient, unclaimed: User) -> None:
        response = client.post(
            "/api/v1/auth/activation/complete",
            json={
                "email": "jordan.avery@approach.com",
                "password": PASSWORD,
                "password_confirmation": PASSWORD + "x",
            },
        )
        assert response.status_code == 422
        assert "do not match" in response.json()["error"]["message"]

    def test_a_weak_password_is_refused_with_every_reason(
        self, client: TestClient, unclaimed: User
    ) -> None:
        response = client.post(
            "/api/v1/auth/activation/complete",
            json={
                "email": "jordan.avery@approach.com",
                "password": "abc",
                "password_confirmation": "abc",
            },
        )
        assert response.status_code == 422
        assert len(response.json()["error"]["problems"]) >= 2

    def test_the_athletes_own_name_is_refused(self, client: TestClient, unclaimed: User) -> None:
        response = client.post(
            "/api/v1/auth/activation/complete",
            json={
                "email": "jordan.avery@approach.com",
                "password": "JordanAvery2026",
                "password_confirmation": "JordanAvery2026",
            },
        )
        assert response.status_code == 422

    def test_an_unknown_address_cannot_set_a_password(self, client: TestClient) -> None:
        """Step two re-proves step one. It trusts nothing from the lookup,
        because the lookup hands back nothing that could serve as proof."""
        response = client.post(
            "/api/v1/auth/activation/complete",
            json={
                "email": "nobody@approach.com",
                "password": PASSWORD,
                "password_confirmation": PASSWORD,
            },
        )
        assert response.status_code == 404

    def test_a_password_cannot_be_set_twice(self, client: TestClient, unclaimed: User) -> None:
        """The second caller must not silently overwrite the first one's choice."""
        payload = {
            "email": "jordan.avery@approach.com",
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
        }
        assert client.post("/api/v1/auth/activation/complete", json=payload).status_code == 204

        again = client.post(
            "/api/v1/auth/activation/complete",
            json={
                "email": "jordan.avery@approach.com",
                "password": OTHER_PASSWORD,
                "password_confirmation": OTHER_PASSWORD,
            },
        )
        assert again.status_code == 409
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"email": "jordan.avery@approach.com", "password": PASSWORD},
            ).status_code
            == 200
        )


# -- the activation code gate ------------------------------------------------


class TestActivationCodeGate:
    """What stops a guessable address from being a way in.

    Addresses are `first.last@domain`, so anyone with a team sheet can guess
    one. With the gate on, guessing is not enough.
    """

    @pytest.fixture
    def gate(self) -> SignupGate:
        return SignupGate.CODE

    @pytest.fixture
    def coded(self, db: Session, unclaimed: User) -> str:
        credential = db.get(UserCredential, unclaimed.id)
        assert credential is not None
        code = accounts.issue_activation_code(db, credential)
        db.flush()
        return code

    def test_a_correct_code_is_accepted(self, client: TestClient, coded: str) -> None:
        response = client.post(
            "/api/v1/auth/activation/lookup",
            json={"email": "jordan.avery@approach.com", "code": coded},
        )
        assert response.status_code == 200
        assert response.json()["requires_code"] is True

    def test_the_code_is_stored_hashed_not_readably(
        self, client: TestClient, db: Session, unclaimed: User, coded: str
    ) -> None:
        credential = db.get(UserCredential, unclaimed.id)
        assert credential is not None
        assert credential.activation_code_hash is not None
        assert coded not in credential.activation_code_hash

    def test_formatting_of_a_typed_code_is_forgiven(self, client: TestClient, coded: str) -> None:
        typed = coded.replace("-", " ").lower()
        response = client.post(
            "/api/v1/auth/activation/lookup",
            json={"email": "jordan.avery@approach.com", "code": typed},
        )
        assert response.status_code == 200

    def test_a_missing_code_is_refused_and_says_one_is_needed(
        self, client: TestClient, coded: str
    ) -> None:
        response = client.post(
            "/api/v1/auth/activation/lookup", json={"email": "jordan.avery@approach.com"}
        )
        assert response.status_code == 403
        body = response.json()["error"]
        assert body["code"] == "activation_code_invalid"
        # The setup screen reveals its code field on this flag.
        assert body["code_required"] is True

    def test_a_missing_code_costs_no_attempt(
        self, client: TestClient, db: Session, unclaimed: User, coded: str
    ) -> None:
        """The form asks for an email first and only learns from the reply that
        a code is needed. Charging for that would lock people out for following
        the form as designed."""
        for _ in range(5):
            client.post(
                "/api/v1/auth/activation/lookup", json={"email": "jordan.avery@approach.com"}
            )
        db.expire_all()
        credential = db.get(UserCredential, unclaimed.id)
        assert credential is not None
        assert credential.failed_attempts == 0
        assert credential.locked_until is None

        allowed = client.post(
            "/api/v1/auth/activation/lookup",
            json={"email": "jordan.avery@approach.com", "code": coded},
        )
        assert allowed.status_code == 200

    def test_a_wrong_code_cannot_set_a_password(self, client: TestClient, coded: str) -> None:
        response = client.post(
            "/api/v1/auth/activation/complete",
            json={
                "email": "jordan.avery@approach.com",
                "code": "AAAA-BBBB",
                "password": PASSWORD,
                "password_confirmation": PASSWORD,
            },
        )
        assert response.status_code == 403

    def test_an_account_with_no_code_issued_cannot_be_claimed(
        self, client: TestClient, unclaimed: User
    ) -> None:
        """Accepting would silently downgrade the gate to open for exactly the
        accounts a coach has not got round to yet."""
        response = client.post(
            "/api/v1/auth/activation/lookup",
            json={"email": "jordan.avery@approach.com", "code": "AAAA-BBBB"},
        )
        assert response.status_code == 403
        assert "no activation code yet" in response.json()["error"]["message"]

    def test_guessing_codes_locks_the_account(
        self, client: TestClient, db: Session, unclaimed: User, coded: str
    ) -> None:
        for _ in range(3):
            client.post(
                "/api/v1/auth/activation/lookup",
                json={"email": "jordan.avery@approach.com", "code": "AAAA-BBBB"},
            )
        blocked = client.post(
            "/api/v1/auth/activation/lookup",
            json={"email": "jordan.avery@approach.com", "code": coded},
        )
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "account_locked"


# -- signing in --------------------------------------------------------------


class TestSignIn:
    @pytest.fixture
    def claimed(self, db: Session, organization: Organization, athlete: Player) -> User:
        return provision(
            db,
            organization,
            email="jordan.avery@approach.com",
            player=athlete,
            password=PASSWORD,
        )

    def test_the_right_password_opens_a_session(self, client: TestClient, claimed: User) -> None:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "jordan.avery@approach.com", "password": PASSWORD},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["token"] and body["expires_at"]
        assert body["display_name"] == "Jordan Avery"

    def test_the_token_is_not_stored_in_the_database(
        self, client: TestClient, db: Session, claimed: User
    ) -> None:
        token = client.post(
            "/api/v1/auth/login",
            json={"email": "jordan.avery@approach.com", "password": PASSWORD},
        ).json()["token"]
        stored = db.scalars(select(UserSession)).all()
        assert len(stored) == 1
        assert stored[0].token_hash == hash_session_token(token)
        assert token not in stored[0].token_hash

    def test_a_session_reaches_the_athletes_own_data(
        self, client: TestClient, claimed: User
    ) -> None:
        token = client.post(
            "/api/v1/auth/login",
            json={"email": "jordan.avery@approach.com", "password": PASSWORD},
        ).json()["token"]
        me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["email"] == "jordan.avery@approach.com"
        assert me.json()["role"] == "PLAYER"

    @pytest.mark.parametrize(
        ("email", "password"),
        [
            ("jordan.avery@approach.com", "the wrong password"),
            ("nobody@approach.com", PASSWORD),
        ],
    )
    def test_a_wrong_address_and_a_wrong_password_look_identical(
        self, client: TestClient, claimed: User, email: str, password: str
    ) -> None:
        """Sign-in reveals nothing about which addresses exist. Only the
        activation step does that, because only there does a person need it."""
        response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert response.status_code == 401
        assert response.json()["error"]["message"] == "Email or password is incorrect."

    def test_an_unclaimed_account_is_told_to_set_one_up(
        self, client: TestClient, unclaimed: User
    ) -> None:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "jordan.avery@approach.com", "password": PASSWORD},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "password_not_set"

    def test_repeated_failures_lock_the_account(
        self, client: TestClient, db: Session, claimed: User
    ) -> None:
        for _ in range(3):
            client.post(
                "/api/v1/auth/login",
                json={"email": "jordan.avery@approach.com", "password": "wrong"},
            )
        blocked = client.post(
            "/api/v1/auth/login",
            json={"email": "jordan.avery@approach.com", "password": PASSWORD},
        )
        assert blocked.status_code == 429
        assert "Try again in" in blocked.json()["error"]["message"]

    def test_the_lock_is_recorded_in_the_database(
        self, client: TestClient, db: Session, claimed: User
    ) -> None:
        """Counted in Postgres, not in process memory: a restart or a second
        instance must not hand an attacker a fresh budget."""
        for _ in range(3):
            client.post(
                "/api/v1/auth/login",
                json={"email": "jordan.avery@approach.com", "password": "wrong"},
            )
        db.expire_all()
        credential = db.get(UserCredential, claimed.id)
        assert credential is not None
        assert credential.locked_until is not None

    def test_a_success_clears_the_failure_count(
        self, client: TestClient, db: Session, claimed: User
    ) -> None:
        client.post(
            "/api/v1/auth/login",
            json={"email": "jordan.avery@approach.com", "password": "wrong"},
        )
        client.post(
            "/api/v1/auth/login",
            json={"email": "jordan.avery@approach.com", "password": PASSWORD},
        )
        db.expire_all()
        credential = db.get(UserCredential, claimed.id)
        assert credential is not None
        assert credential.failed_attempts == 0
        assert credential.last_login_at is not None


# -- sessions ----------------------------------------------------------------


class TestSessions:
    @pytest.fixture
    def signed_in(self, client: TestClient, db: Session, organization: Organization, athlete):  # type: ignore[no-untyped-def]
        provision(
            db,
            organization,
            email="jordan.avery@approach.com",
            player=athlete,
            password=PASSWORD,
        )
        return client.post(
            "/api/v1/auth/login",
            json={"email": "jordan.avery@approach.com", "password": PASSWORD},
        ).json()["token"]

    def test_no_token_is_unauthenticated(self, client: TestClient) -> None:
        assert client.get("/api/v1/me").status_code == 401

    def test_an_invented_token_is_rejected(self, client: TestClient, signed_in: str) -> None:
        assert (
            client.get("/api/v1/me", headers={"Authorization": "Bearer made-up"}).status_code == 401
        )

    def test_signing_out_ends_the_session(self, client: TestClient, signed_in: str) -> None:
        headers = {"Authorization": f"Bearer {signed_in}"}
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
        assert client.get("/api/v1/me", headers=headers).status_code == 401

    def test_signing_out_needs_a_valid_token(self, client: TestClient) -> None:
        """So a token glimpsed in a log cannot be revoked by a stranger."""
        assert (
            client.post(
                "/api/v1/auth/logout", headers={"Authorization": "Bearer made-up"}
            ).status_code
            == 401
        )

    def test_an_expired_session_is_rejected(
        self, client: TestClient, db: Session, signed_in: str
    ) -> None:
        session = db.scalars(select(UserSession)).one()
        session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.flush()
        assert (
            client.get("/api/v1/me", headers={"Authorization": f"Bearer {signed_in}"}).status_code
            == 401
        )

    def test_revoking_every_session_signs_all_devices_out(
        self, client: TestClient, db: Session, signed_in: str
    ) -> None:
        user = db.scalars(select(User).where(User.email == "jordan.avery@approach.com")).one()
        assert accounts.revoke_all_sessions(db, user.id) == 1
        assert (
            client.get("/api/v1/me", headers={"Authorization": f"Bearer {signed_in}"}).status_code
            == 401
        )

    def test_a_deactivated_account_loses_access_immediately(
        self, client: TestClient, db: Session, signed_in: str
    ) -> None:
        """Authorization is re-read from our tables on every request, so a
        live token is not a licence that outlives the account."""
        user = db.scalars(select(User).where(User.email == "jordan.avery@approach.com")).one()
        user.active = False
        db.flush()
        assert (
            client.get("/api/v1/me", headers={"Authorization": f"Bearer {signed_in}"}).status_code
            == 401
        )


# -- authorization still holds -----------------------------------------------


def test_a_player_session_cannot_read_another_athlete(
    client: TestClient, db: Session, organization: Organization, athlete: Player
) -> None:
    """The point of per-person accounts: the server decides, per request, which
    athlete this particular person may read."""
    other = make_player(
        db, organization, first_name="Riley", last_name="Chen", external_id="TM-ROSTER-2"
    )
    provision(
        db, organization, email="jordan.avery@approach.com", player=athlete, password=PASSWORD
    )
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "jordan.avery@approach.com", "password": PASSWORD},
    ).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get(f"/api/v1/players/{athlete.id}", headers=headers).status_code == 200
    # 404, not 403: distinguishing them would confirm which athletes are enrolled.
    assert client.get(f"/api/v1/players/{other.id}", headers=headers).status_code == 404
    assert client.get("/api/v1/players", headers=headers).status_code == 403


def test_a_coach_session_reaches_the_whole_roster(
    client: TestClient, db: Session, organization: Organization, athlete: Player
) -> None:
    provision(
        db,
        organization,
        email="coach@approach.com",
        display_name="Coach",
        role=Role.COACH,
        password=PASSWORD,
    )
    token = client.post(
        "/api/v1/auth/login", json={"email": "coach@approach.com", "password": PASSWORD}
    ).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/players", headers=headers).status_code == 200
    assert client.get(f"/api/v1/players/{athlete.id}", headers=headers).status_code == 200


def test_an_account_from_another_auth_provider_cannot_be_claimed(
    client: TestClient, db: Session, organization: Organization
) -> None:
    """A leftover passcode-era row must not be claimable.

    Giving it a password would produce an account that signs in and is then
    rejected by the principal lookup, which matches on (provider, subject).
    """
    user = provision(db, organization, email="legacy@approach.com")
    user.auth_provider = "passcode"
    user.auth_subject = "coach"
    db.flush()

    assert (
        client.post(
            "/api/v1/auth/activation/lookup", json={"email": "legacy@approach.com"}
        ).status_code
        == 404
    )


def test_the_service_and_the_provider_agree_on_the_provider_name() -> None:
    """If these drift, every provisioned account signs in and is then rejected."""
    from bsa.integrations.auth.local import LocalAuthProvider

    assert LocalAuthProvider.name == accounts.LOCAL_PROVIDER


def test_two_athletes_who_share_an_address_cannot_both_exist(
    db: Session, organization: Organization
) -> None:
    """The database refuses it, not just the planner.

    `uq_users_email` is the last line of defence: if a future provisioning bug
    proposed one address twice, the insert fails rather than producing two
    accounts that can read each other's data.
    """
    from sqlalchemy.exc import IntegrityError

    provision(db, organization, email="alex.stone@approach.com")
    # A savepoint, so rolling back the failed insert leaves the fixture's own
    # transaction -- and therefore the rest of this test session -- intact.
    savepoint = db.begin_nested()
    with pytest.raises(IntegrityError):
        provision(db, organization, email="alex.stone@approach.com")
    savepoint.rollback()
