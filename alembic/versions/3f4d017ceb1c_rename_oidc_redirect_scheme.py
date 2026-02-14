"""rename oidc redirect scheme

Revision ID: 3f4d017ceb1c
Revises: 03bea7e891dd
Create Date: 2026-02-13
"""

from typing import Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f4d017ceb1c"
down_revision: Union[str, None] = "03bea7e891dd"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    # Convert existing values: "true" -> "https", anything else -> "http"
    op.execute(
        "UPDATE config SET value = 'https' WHERE key = 'oidc_redirect_https' AND value = 'true'"
    )
    op.execute(
        "UPDATE config SET value = 'http' WHERE key = 'oidc_redirect_https' AND value != 'https'"
    )
    # Rename the key
    op.execute(
        "UPDATE config SET key = 'oidc_redirect_scheme' WHERE key = 'oidc_redirect_https'"
    )


def downgrade() -> None:
    # Convert values back: "https" -> "true", anything else -> ""
    op.execute(
        "UPDATE config SET value = 'true' WHERE key = 'oidc_redirect_scheme' AND value = 'https'"
    )
    op.execute(
        "UPDATE config SET value = '' WHERE key = 'oidc_redirect_scheme' AND value != 'true'"
    )
    # Rename key back
    op.execute(
        "UPDATE config SET key = 'oidc_redirect_https' WHERE key = 'oidc_redirect_scheme'"
    )
