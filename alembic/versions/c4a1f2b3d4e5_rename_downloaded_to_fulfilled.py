"""rename downloaded to fulfilled

Revision ID: c4a1f2b3d4e5
Revises: babaede58935
Create Date: 2026-10-22 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4a1f2b3d4e5"
down_revision: str | None = "babaede58935"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("audiobook", schema=None) as batch_op:
        batch_op.alter_column(
            "downloaded",
            new_column_name="fulfilled",
            existing_type=sa.Boolean(),
            existing_nullable=False,
        )

    with op.batch_alter_table("manualbookrequest", schema=None) as batch_op:
        batch_op.alter_column(
            "downloaded",
            new_column_name="fulfilled",
            existing_type=sa.Boolean(),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("manualbookrequest", schema=None) as batch_op:
        batch_op.alter_column(
            "fulfilled",
            new_column_name="downloaded",
            existing_type=sa.Boolean(),
            existing_nullable=False,
        )

    with op.batch_alter_table("audiobook", schema=None) as batch_op:
        batch_op.alter_column(
            "fulfilled",
            new_column_name="downloaded",
            existing_type=sa.Boolean(),
            existing_nullable=False,
        )
