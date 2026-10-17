"""videos belong to an athlete, with or without a session

`session_id` becomes nullable so a coach can attach a clip without first
inventing a session to file it under. The provider columns record where the
file actually lives, so a video uploaded to one media provider is still
findable after a deployment moves to another -- `url` is enough to play an
asset but not enough to delete one.

Existing rows are backfilled as "link", which is what they are: a URL somebody
pasted in before any upload path existed.

Revision ID: aece41b54e9f
Revises: cc64187a927f
Create Date: 2026-10-17 22:10:25.203269+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "aece41b54e9f"
down_revision: str | None = "cc64187a927f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Backfilled with a server default, then dropped: existing rows need a
    # value and they are exactly what "link" describes -- a URL pasted in
    # before any upload path existed. New rows get it from the model.
    op.add_column(
        "session_videos",
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="link"),
    )
    op.alter_column("session_videos", "provider", server_default=None)
    op.add_column(
        "session_videos", sa.Column("external_asset_id", sa.String(length=255), nullable=True)
    )
    op.add_column("session_videos", sa.Column("thumbnail_url", sa.Text(), nullable=True))
    op.add_column("session_videos", sa.Column("duration_seconds", sa.Float(), nullable=True))
    op.add_column("session_videos", sa.Column("byte_size", sa.Integer(), nullable=True))
    op.alter_column("session_videos", "session_id", existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    op.alter_column("session_videos", "session_id", existing_type=sa.UUID(), nullable=False)
    op.drop_column("session_videos", "byte_size")
    op.drop_column("session_videos", "duration_seconds")
    op.drop_column("session_videos", "thumbnail_url")
    op.drop_column("session_videos", "external_asset_id")
    op.drop_column("session_videos", "provider")
