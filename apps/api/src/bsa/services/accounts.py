"""Account activation, sign-in and sessions.

The whole flow in one place, because it is the only part of the system where a
mistake hands one athlete another athlete's data:

    provisioned (no password)  --activate-->  claimable  --sign in-->  session

Three rules this module exists to hold:

1. **Step two re-proves step one.** The client sends the email (and code) again
   when setting a password. Completing a setup never trusts that the caller
   passed the lookup, because the lookup hands out nothing it could present as
   evidence.
2. **Failures are counted in the database.** A process restart, or a second
   instance, must not reset an attacker's budget.
3. **Only one caller can claim an account.** The password is written with a
   conditional UPDATE that matches only while no password is set, so two
   simultaneous setups cannot both succeed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.orm import Session

from bsa.core.config import Settings, SignupGate
from bsa.core.errors import (
    AccountLockedError,
    ActivationCodeError,
    AlreadyActivatedError,
    AuthenticationError,
    EmailNotRecognizedError,
    PasswordNotSetError,
    ValidationError,
)
from bsa.core.logging import get_logger
from bsa.core.password import (
    dummy_verify,
    hash_password,
    needs_rehash,
    password_problems,
    verify_password,
)
from bsa.core.tokens import (
    hash_session_token,
    new_activation_code,
    new_session_token,
    normalize_activation_code,
)
from bsa.db.models import Player, User, UserCredential, UserSession

log = get_logger(__name__)

#: Must match `LocalAuthProvider.name`. Accounts belonging to another provider
#: are invisible here: letting one be given a password would produce an account
#: that signs in successfully and is then rejected by the principal lookup,
#: because that lookup matches on (auth_provider, auth_subject).
LOCAL_PROVIDER = "local"

#: `last_used_at` is refreshed at most this often, so a chatty dashboard does
#: not turn every read request into a write.
_TOUCH_INTERVAL = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class ActivationTarget:
    """What the setup screen may safely know after a successful lookup."""

    email: str
    #: For the greeting on the password screen. Already implied by the address.
    first_name: str
    requires_code: bool


@dataclass(frozen=True, slots=True)
class IssuedSession:
    user: User
    token: str
    expires_at: datetime


def _now() -> datetime:
    return datetime.now(UTC)


def normalize_email(value: str) -> str:
    """Lower-cased and trimmed.

    Addresses are stored normalized, so this is applied on every read *and*
    every write -- a login must not fail because someone's keyboard
    capitalized the first letter.
    """
    return value.strip().lower()


# -- lookup ------------------------------------------------------------------


def _load(db: Session, email: str) -> tuple[User, UserCredential] | None:
    """The local account for this address, or None.

    Inactive accounts, and accounts belonging to another auth provider, both
    count as None -- there is no partial state a caller could act on.
    """
    user = db.scalars(
        select(User).where(
            User.email == normalize_email(email),
            User.auth_provider == LOCAL_PROVIDER,
            User.active.is_(True),
        )
    ).first()
    if user is None:
        return None
    credential = db.get(UserCredential, user.id)
    if credential is None:
        # Provisioned before this table existed, or created by an older seed.
        # Treated as "no password yet" rather than as an error.
        credential = UserCredential(user_id=user.id)
        db.add(credential)
        db.flush()
    return user, credential


def _personal_terms(db: Session, user: User) -> tuple[str, ...]:
    """Strings a password must not simply restate.

    Includes the athlete's real name as well as the account's display name: the
    display name may be an abbreviation, and "ColtJacobs2026" is exactly what
    someone picks when the hint is their own email address.
    """
    terms = {user.email.split("@")[0], *user.display_name.split()}
    if user.player_id is not None:
        player = db.get(Player, user.player_id)
        if player is not None:
            terms.update({player.first_name, player.last_name})
    return tuple(t for t in terms if t)


# -- failure accounting ------------------------------------------------------


def _assert_not_locked(credential: UserCredential, now: datetime) -> None:
    if credential.locked_until is not None and credential.locked_until > now:
        minutes = max(1, int((credential.locked_until - now).total_seconds() // 60) + 1)
        raise AccountLockedError(
            f"Too many failed attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}."
        )


def _register_failure(db: Session, settings: Settings, credential: UserCredential) -> None:
    """Count one failure and lock the account once the budget is spent.

    Committed immediately: the caller is about to raise, and an uncommitted
    counter would make the lockout unenforceable.
    """
    credential.failed_attempts += 1
    if credential.failed_attempts >= settings.login_max_attempts:
        credential.locked_until = _now() + timedelta(minutes=settings.login_lockout_minutes)
        credential.failed_attempts = 0
        log.warning("account.locked", user_id=str(credential.user_id))
    db.commit()


def _clear_failures(credential: UserCredential) -> None:
    credential.failed_attempts = 0
    credential.locked_until = None


# -- activation --------------------------------------------------------------


def begin_activation(
    db: Session, settings: Settings, *, email: str, code: str | None = None
) -> ActivationTarget:
    """Check an address against the roster before showing the password screen.

    This is the step that tells someone "email does not match", which is the
    one piece of deliberate information disclosure in the system: a person
    given their address verbally cannot fix a typo otherwise. What stops that
    disclosure becoming a way in is the activation code, when the deployment
    requires one.
    """
    found = _load(db, email)
    if found is None:
        raise EmailNotRecognizedError("Email does not match.")
    user, credential = found

    now = _now()
    _assert_not_locked(credential, now)

    if credential.has_password:
        raise AlreadyActivatedError("This account already has a password. Sign in instead.")

    _check_activation_code(db, settings, credential, code)

    return ActivationTarget(
        email=user.email,
        first_name=(user.display_name.split(" ") or [""])[0],
        requires_code=settings.signup_gate is SignupGate.CODE,
    )


def _check_activation_code(
    db: Session, settings: Settings, credential: UserCredential, code: str | None
) -> None:
    if settings.signup_gate is not SignupGate.CODE:
        return

    if credential.activation_code_hash is None:
        # The deployment demands a code but none was ever issued for this
        # account. Refusing is the only safe answer: accepting would silently
        # downgrade the gate to OPEN for exactly the accounts a coach has not
        # got round to yet.
        raise ActivationCodeError(
            "This account has no activation code yet. Ask your coach to issue one."
        )

    if not code:
        # Not a guess, so it costs no attempt. The setup screen asks for an
        # email first and only learns a code is needed from this reply; making
        # that discovery consume part of the lockout budget would lock people
        # out for following the form.
        raise ActivationCodeError(
            "This account needs the activation code your coach gave you.",
            details={"code_required": True},
        )

    if not verify_password(credential.activation_code_hash, normalize_activation_code(code)):
        _register_failure(db, settings, credential)
        raise ActivationCodeError("That activation code is not correct.")


def complete_activation(
    db: Session,
    settings: Settings,
    *,
    email: str,
    password: str,
    confirmation: str,
    code: str | None = None,
) -> User:
    """Set the account's first password.

    Every check from `begin_activation` is repeated here on purpose -- see this
    module's docstring. Does not sign the person in: they are sent to the login
    page to use the password they just chose, which is both what was asked for
    and the only way they find out immediately that they can remember it.
    """
    found = _load(db, email)
    if found is None:
        raise EmailNotRecognizedError("Email does not match.")
    user, credential = found

    _assert_not_locked(credential, _now())
    if credential.has_password:
        raise AlreadyActivatedError("This account already has a password. Sign in instead.")
    _check_activation_code(db, settings, credential, code)

    if password != confirmation:
        raise ValidationError("Those passwords do not match.")

    problems = password_problems(password, personal=_personal_terms(db, user))
    if problems:
        raise ValidationError(problems[0], details={"problems": problems})

    now = _now()
    # Conditional on the password still being unset, so of two simultaneous
    # setups exactly one wins and the loser is told the account is already
    # claimed rather than silently overwriting the winner's password.
    # cast: Session.execute is typed as Result, but a DML statement always
    # returns a CursorResult, which is what carries rowcount.
    claimed = cast(
        "CursorResult[Any]",
        db.execute(
            update(UserCredential)
            .where(UserCredential.user_id == user.id, UserCredential.password_hash.is_(None))
            .values(
                password_hash=hash_password(password),
                password_set_at=now,
                activated_at=now,
                failed_attempts=0,
                locked_until=None,
            )
        ),
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise AlreadyActivatedError("This account already has a password. Sign in instead.")

    db.commit()
    log.info("account.activated", user_id=str(user.id), role=user.role.value)
    return user


# -- sign in -----------------------------------------------------------------


def authenticate(db: Session, settings: Settings, *, email: str, password: str) -> IssuedSession:
    """Verify a password and open a session.

    A wrong address and a wrong password produce the same message and the same
    amount of work. The activation step reveals which addresses exist because a
    person needs that; sign-in does not, so it does not.
    """
    found = _load(db, email)
    if found is None:
        dummy_verify()
        raise AuthenticationError("Email or password is incorrect.")
    user, credential = found

    now = _now()
    _assert_not_locked(credential, now)

    if credential.password_hash is None:
        raise PasswordNotSetError("You haven't set a password yet. Set up your account first.")

    if not verify_password(credential.password_hash, password):
        _register_failure(db, settings, credential)
        raise AuthenticationError("Email or password is incorrect.")

    if needs_rehash(credential.password_hash):
        # The only moment the plaintext exists and the hash is known good.
        credential.password_hash = hash_password(password)

    _clear_failures(credential)
    credential.last_login_at = now

    token = new_session_token()
    expires_at = now + timedelta(seconds=settings.session_ttl_seconds)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            expires_at=expires_at,
            last_used_at=now,
        )
    )

    # Bounded growth: this account's dead sessions go when it signs in again.
    db.execute(
        delete(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.expires_at < now - timedelta(days=7),
        )
    )

    user.last_seen_at = now
    db.commit()
    log.info("account.signed_in", user_id=str(user.id), role=user.role.value)
    return IssuedSession(user=user, token=token, expires_at=expires_at)


# -- sessions ----------------------------------------------------------------


def user_id_for_token(db: Session, token: str) -> uuid.UUID | None:
    """Resolve a bearer token to the user it belongs to, or None.

    None covers every rejection -- unknown, expired, revoked -- because the
    caller has nothing useful to do with the difference and reporting it would
    confirm that a token was once valid.
    """
    now = _now()
    session = db.scalars(
        select(UserSession).where(UserSession.token_hash == hash_session_token(token))
    ).first()
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        return None

    if session.last_used_at is None or now - session.last_used_at > _TOUCH_INTERVAL:
        session.last_used_at = now
        db.commit()
    return session.user_id


def revoke_session(db: Session, token: str) -> None:
    """Sign out. Silent when the token is already gone -- the goal is reached."""
    session = db.scalars(
        select(UserSession).where(UserSession.token_hash == hash_session_token(token))
    ).first()
    if session is not None and session.revoked_at is None:
        session.revoked_at = _now()
        db.commit()


def revoke_all_sessions(db: Session, user_id: uuid.UUID) -> int:
    """End every session for one account. Returns how many were ended."""
    result = cast(
        "CursorResult[Any]",
        db.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=_now())
        ),
    )
    db.commit()
    return int(result.rowcount or 0)


# -- provisioning helpers ----------------------------------------------------


def issue_activation_code(db: Session, credential: UserCredential) -> str:
    """Mint a code, store only its hash, and return the one readable copy.

    The caller is responsible for getting it to the athlete. It cannot be read
    back later; a lost code is reissued, not recovered.
    """
    code = new_activation_code()
    credential.activation_code_hash = hash_password(code)
    return code
