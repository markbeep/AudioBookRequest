from typing import Literal

from sqlmodel import Session

from app.util.cache import StringConfigCache

MamFreeleechConfigKey = Literal[
    "mam_freeleech_ttl",
    "mam_freeleech_trusted_visible",
]


class MamFreeleechConfig(StringConfigCache[MamFreeleechConfigKey]):
    """Configuration for the MaM freeleech browse page."""

    def get_ttl_seconds(self, session: Session) -> int:
        """Cache TTL in seconds (default 15 minutes)."""
        return self.get_int(session, "mam_freeleech_ttl", 15 * 60)

    def set_ttl_seconds(self, session: Session, ttl: int):
        self.set_int(session, "mam_freeleech_ttl", ttl)

    def get_trusted_visible(self, session: Session) -> bool:
        """Whether Trusted users can see the freeleech page (default: admin only)."""
        val = self.get_bool(session, "mam_freeleech_trusted_visible")
        if val is None:
            return False
        return val

    def set_trusted_visible(self, session: Session, value: bool):
        self.set_bool(session, "mam_freeleech_trusted_visible", value)


mam_freeleech_config = MamFreeleechConfig()
