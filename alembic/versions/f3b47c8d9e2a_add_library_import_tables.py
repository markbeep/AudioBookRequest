"""add library import tables

Revision ID: f3b47c8d9e2a
Revises: e58129ba2119
Create Date: 2026-01-22 19:00:00.000000

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = "f3b47c8d9e2a"
down_revision: Union[str, None] = "e58129ba2119"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "libraryimportsession",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("root_path", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("current_timestamp"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "libraryimportitem",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("source_path", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("detected_title", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("detected_author", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("match_asin", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("match_score", sa.Float(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("error_msg", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["libraryimportsession.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["match_asin"], ["audiobook.asin"], ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("libraryimportitem")
    op.drop_table("libraryimportsession")
