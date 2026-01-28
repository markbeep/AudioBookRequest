"""add series index to audiobook

Revision ID: e2c8b1d0a9f4
Revises: f3b47c8d9e2a
Create Date: 2026-01-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e2c8b1d0a9f4"
down_revision: Union[str, None] = "f3b47c8d9e2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("audiobook", sa.Column("series_index", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("audiobook", "series_index")
