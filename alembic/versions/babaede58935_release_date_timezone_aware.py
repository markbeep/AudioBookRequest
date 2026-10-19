"""release_date timezone aware

Revision ID: babaede58935
Revises: 1718055d5ca8
Create Date: 2026-10-19 12:18:40.714196

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "babaede58935"
down_revision: str | None = "1718055d5ca8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing naive values are UTC. SQLite stores timestamps as text and has
    # no timezone-aware type, so only Postgres needs the column altered.
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column(
            "audiobook",
            "release_date",
            existing_type=sa.DateTime(timezone=False),
            type_=sa.DateTime(timezone=True),
            existing_nullable=False,
            postgresql_using="release_date AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column(
            "audiobook",
            "release_date",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(timezone=False),
            existing_nullable=False,
            postgresql_using="release_date AT TIME ZONE 'UTC'",
        )
