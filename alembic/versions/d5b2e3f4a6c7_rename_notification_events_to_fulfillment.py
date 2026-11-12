"""rename notification events to fulfillment

Revision ID: d5b2e3f4a6c7
Revises: c4a1f2b3d4e5
Create Date: 2026-10-22 00:00:01.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5b2e3f4a6c7"
down_revision: str | None = "c4a1f2b3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "ALTER TYPE eventenum RENAME VALUE "
            + "'on_successful_download' TO 'on_fulfilled'"
        )
        op.execute(
            "ALTER TYPE eventenum RENAME VALUE "
            + "'on_failed_download' TO 'on_failed_fulfillment'"
        )
    else:
        op.execute(
            "UPDATE notification SET event = 'on_fulfilled' "
            + "WHERE event = 'on_successful_download'"
        )
        op.execute(
            "UPDATE notification SET event = 'on_failed_fulfillment' "
            + "WHERE event = 'on_failed_download'"
        )
        # "on_fulfilled" shortens the longest label, so narrow the column to
        # match the enum inferred from the models.
        with op.batch_alter_table("notification", schema=None) as batch_op:
            batch_op.alter_column(
                "event",
                existing_type=sa.VARCHAR(length=22),
                type_=sa.Enum(
                    "on_new_request",
                    "on_fulfilled",
                    "on_failed_fulfillment",
                    name="eventenum",
                ),
                existing_nullable=False,
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "ALTER TYPE eventenum RENAME VALUE "
            + "'on_fulfilled' TO 'on_successful_download'"
        )
        op.execute(
            "ALTER TYPE eventenum RENAME VALUE "
            + "'on_failed_fulfillment' TO 'on_failed_download'"
        )
    else:
        with op.batch_alter_table("notification", schema=None) as batch_op:
            batch_op.alter_column(
                "event",
                existing_type=sa.Enum(
                    "on_new_request",
                    "on_fulfilled",
                    "on_failed_fulfillment",
                    name="eventenum",
                ),
                type_=sa.Enum(
                    "on_new_request",
                    "on_successful_download",
                    "on_failed_download",
                    name="eventenum",
                ),
                existing_nullable=False,
            )
        op.execute(
            "UPDATE notification SET event = 'on_successful_download' "
            + "WHERE event = 'on_fulfilled'"
        )
        op.execute(
            "UPDATE notification SET event = 'on_failed_download' "
            + "WHERE event = 'on_failed_fulfillment'"
        )
