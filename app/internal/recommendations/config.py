from typing import Literal

from app.util.cache import StringConfigCache

RecommendationConfigKey = Literal[
    "recommendations_enabled",
]


class RecommendationConfig(StringConfigCache[RecommendationConfigKey]):
    def get_enabled(self, session) -> bool:
        val = self.get_bool(session, "recommendations_enabled")
        if val is None:
            return True  # enabled by default
        return val

    def set_enabled(self, session, value: bool):
        self.set_bool(session, "recommendations_enabled", value)


recommendation_config = RecommendationConfig()
