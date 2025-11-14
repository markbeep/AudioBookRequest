from typing import Literal, Optional

from sqlmodel import Session

from app.util.cache import StringConfigCache


AIConfigKey = Literal[
    "ai_ollama_endpoint",
    "ai_ollama_model",
]


class AIConfig(StringConfigCache[AIConfigKey]):
    """Configuration for AI-backed recommendations (Ollama)."""

    def get_endpoint(self, session: Session) -> Optional[str]:
        ep = self.get(session, "ai_ollama_endpoint")
        if ep:
            return ep.rstrip("/")
        return None

    def set_endpoint(self, session: Session, endpoint: str):
        self.set(session, "ai_ollama_endpoint", endpoint)

    def get_model(self, session: Session) -> Optional[str]:
        return self.get(session, "ai_ollama_model")

    def set_model(self, session: Session, model: str):
        self.set(session, "ai_ollama_model", model)

    def is_configured(self, session: Session) -> bool:
        return bool(self.get_endpoint(session) and self.get_model(session))


ai_config = AIConfig()
