"""local accounts: credentials and sessions

Adds per-person accounts with a password, replacing the one-passcode-per-role
demo gate. Two new tables plus a uniqueness guarantee on the login address.

The email normalisation below runs before the unique constraint on purpose: the
addresses already in the table were written by seed scripts with no casing rule,
and `Coach@...` and `coach@...` must not be allowed to become two accounts.

Revision ID: cc64187a927f
Revises: edcd18a85b3f
Create Date: 2026-10-15 22:26:14.664951+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cc64187a927f"
down_revision: str | None = "edcd18a85b3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_credentials",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("password_set_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activation_code_hash", sa.String(length=255), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_credentials_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_credentials")),
    )
    op.create_table(
        "user_sessions",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_sessions_token_hash")),
    )
    op.create_index(op.f("ix_user_sessions_user_id"), "user_sessions", ["user_id"], unique=False)
    op.create_index(
        "ix_user_sessions_user_id_expires_at",
        "user_sessions",
        ["user_id", "expires_at"],
        unique=False,
    )
    # Normalise before constraining, so an existing mixed-case address does not
    # make this migration fail on a database that is in fact consistent.
    op.execute("UPDATE users SET email = lower(btrim(email))")
    # Checked in Python rather than PL/pgSQL: a RAISE message containing a
    # "%" placeholder is indistinguishable from a bound parameter to the
    # driver, and a plain Python error reads better in a deploy log anyway.
    clashes = (
        op.get_bind()
        .execute(
            sa.text("SELECT email FROM users GROUP BY email HAVING count(*) > 1 ORDER BY email")
        )
        .scalars()
        .all()
    )
    if clashes:
        raise RuntimeError(
            "cannot make users.email unique: "
            + ", ".join(clashes)
            + " is used by more than one account. An email is now a login identifier, "
            "so these must be resolved by hand before upgrading."
        )
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    # Every existing account gets a credential row in the "provisioned, no
    # password" state, so the activation flow works for accounts that predate it.
    op.execute(
        """
        INSERT INTO user_credentials (user_id, failed_attempts, created_at, updated_at)
        SELECT id, 0, now(), now() FROM users
        ON CONFLICT (user_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_index("ix_user_sessions_user_id_expires_at", table_name="user_sessions")
    op.drop_index(op.f("ix_user_sessions_user_id"), table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_table("user_credentials")
