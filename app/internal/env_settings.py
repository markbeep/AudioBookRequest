import pathlib
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class DBSettings(BaseModel):
    sqlite_path: str = "db.sqlite"
    """Relative path to the sqlite database given the config directory. If absolute, it ignores the config dir location."""


class ApplicationSettings(BaseModel):
    debug: bool = False
    openapi_enabled: bool = False
    config_dir: str = "/config"
    port: int = 8000
    version: str = "local"
    log_level: str = "INFO"
    base_url: str = ""
    default_region: str = "us"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ABR_",
        env_nested_delimiter="__",
        nested_model_default_partial_update=True,
        env_file=(".env.local", ".env"),
    )

    db: DBSettings = DBSettings()
    app: ApplicationSettings = ApplicationSettings()

    def get_sqlite_path(self):
        if self.db.sqlite_path.startswith("/"):
            return self.db.sqlite_path
        return str(pathlib.Path(self.app.config_dir) / self.db.sqlite_path)
