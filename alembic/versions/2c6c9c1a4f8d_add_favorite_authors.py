"""add favorite authors

Revision ID: 2c6c9c1a4f8d
Revises: e4f418be2275
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2c6c9c1a4f8d"
down_revision: Union[str, None] = "e4f418be2275"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "favoriteauthor",
        sa.Column("user_username", sa.String(), nullable=False),
        sa.Column("author", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_username"], ["user.username"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_username", "author"),
    )


def downgrade() -> None:
    op.drop_table("favoriteauthor")
