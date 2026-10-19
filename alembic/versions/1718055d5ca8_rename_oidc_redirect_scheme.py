"""rename oidc redirect scheme

Revision ID: 1718055d5ca8
Revises: d0fac85afd0f
Create Date: 2026-02-22 18:01:35.239629

"""

from collections.abc import Sequence

from sqlmodel import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1718055d5ca8"
down_revision: str | None = "d0fac85afd0f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Convert existing values: "true" -> "https", anything else -> "http"
    current = (
        op.get_bind()
        .execute(text("SELECT value FROM config WHERE key = 'oidc_redirect_https'"))
        .fetchone()
    )

    if current:
        if current[0] == "true":
            op.execute(
                "UPDATE config SET value = 'https' WHERE key = 'oidc_redirect_https'"
            )
        else:
            op.execute(
                "UPDATE config SET value = 'http' WHERE key = 'oidc_redirect_https'"
            )
    else:
        # If no existing value, set default to "http"
        op.execute(
            "INSERT INTO config (key, value) VALUES ('oidc_redirect_https', 'http')"
        )

    # Rename key
    op.execute(
        "UPDATE config SET key = 'oidc_redirect_scheme' WHERE key = 'oidc_redirect_https'"
    )


def downgrade() -> None:
    # Convert values back: "https" -> "true", anything else -> ""
    op.execute(
        "UPDATE config SET value = 'true' WHERE key = 'oidc_redirect_scheme' AND value = 'https'"
    )
    op.execute(
        "DELETE FROM config WHERE key = 'oidc_redirect_scheme' AND value != 'true'"
    )
    # Rename key back
    op.execute(
        "UPDATE config SET key = 'oidc_redirect_https' WHERE key = 'oidc_redirect_scheme'"
    )
