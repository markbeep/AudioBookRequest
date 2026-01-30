"""remove oidc_redirect_https setting

Revision ID: a1b2c3d4e5f6
Revises: d0fac85afd0f
Create Date: 2026-01-22

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "d0fac85afd0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove the deprecated oidc_redirect_https config key from the database
    op.execute("DELETE FROM config WHERE key = 'oidc_redirect_https'")

    print("""
    ╔════════════════════════════════════════════════════════════════════╗
    ║  OIDC Protocol Detection - Automatic!                             ║
    ╚════════════════════════════════════════════════════════════════════╝

    The manual oidc_redirect_https setting has been removed.

    Protocol (http/https) is now automatically detected from requests!

    Default Behavior:
    - All proxy headers are trusted (0.0.0.0/0)
    - Works out-of-the-box for all setups
    - Perfect for home labs and self-hosted instances

    For Production Security (Optional):
    Configure FORWARDED_ALLOW_IPS to only trust your reverse proxy IP.
    You'll see a warning in logs if you should do this.

    Example docker-compose.yml:
      environment:
        - FORWARDED_ALLOW_IPS=172.17.0.1

    For multiple proxies: FORWARDED_ALLOW_IPS=172.17.0.1,10.0.0.1
    For IP ranges: FORWARDED_ALLOW_IPS=172.17.0.0/16

    Learn more: https://github.com/markbeep/AudioBookRequest/docs/oidc
    """)


def downgrade() -> None:
    # Cannot restore - users would need to reconfigure manually
    pass
