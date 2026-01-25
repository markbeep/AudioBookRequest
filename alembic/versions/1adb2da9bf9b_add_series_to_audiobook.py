"""add series to audiobook

Revision ID: 1adb2da9bf9b
Revises: 0c948752a9c2
Create Date: 2026-01-21 19:52:43.248457

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1adb2da9bf9b"
down_revision: Union[str, None] = "0c948752a9c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("audiobook", sa.Column("series", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("audiobook", "series")
