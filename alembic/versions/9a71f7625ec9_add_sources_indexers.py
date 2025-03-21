"""add sources & indexers

Revision ID: 9a71f7625ec9
Revises: cafe562e2832
Create Date: 2025-02-16 16:47:52.131857

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '9a71f7625ec9'
down_revision: Union[str, None] = 'cafe562e2832'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('indexer',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('privacy', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('prowlarrsource',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('guid', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('indexer_id', sa.Integer(), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('seeders', sa.Integer(), nullable=False),
    sa.Column('leechers', sa.Integer(), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('publishDate', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['indexer_id'], ['indexer.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('prowlarrsource')
    op.drop_table('indexer')
    # ### end Alembic commands ###
