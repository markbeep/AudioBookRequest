"""add admin note to requests

Revision ID: f1a2b3c4d5e6
Revises: d5b2e3f4a6c7
Create Date: 2026-11-12 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "d5b2e3f4a6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("audiobook", schema=None) as batch_op:
        batch_op.add_column(sa.Column("admin_note", sa.Text(), nullable=True))

    with op.batch_alter_table("manualbookrequest", schema=None) as batch_op:
        batch_op.add_column(sa.Column("admin_note", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("manualbookrequest", schema=None) as batch_op:
        batch_op.drop_column("admin_note")

    with op.batch_alter_table("audiobook", schema=None) as batch_op:
        batch_op.drop_column("admin_note")
