import pathlib

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.internal.auth.login_types import LoginTypeEnum


class DBSettings(BaseModel):
    sqlite_path: str = "db.sqlite"
    """Relative path to the sqlite database given the config directory. If absolute, it ignores the config dir location."""
    use_postgres: bool = False
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "audiobookrequest"
    postgres_user: str = "abr"
    postgres_password: str = "password"
    postgres_ssl_mode: str = "prefer"


class ApplicationSettings(BaseModel):
    debug: bool = False
    openapi_enabled: bool = False
    config_dir: str = "/config"
    port: int = 8000
    version: str = "local"
    log_level: str = "INFO"
    base_url: str = ""
    disable_censor: bool = False
    forwarded_allow_ips: str = "0.0.0.0/0"
    """Trusted proxy IPs for forwarded headers. Used by Uvicorn's --proxy-headers."""

    default_region: str = "us"
    """Default region used in the search"""

    force_login_type: str = ""
    """Forces the login type used. If set, the login type cannot be changed in the UI."""

    init_root_username: str = ""
    init_root_password: str = ""

    def get_force_login_type(self) -> LoginTypeEnum | None:
        if self.force_login_type.strip():
            try:
                login_type = LoginTypeEnum(self.force_login_type.strip().lower())
                if login_type == LoginTypeEnum.api_key:
                    raise ValueError(
                        "API key login type is not supported for forced login type."
                    )
                return login_type
            except ValueError:
                raise ValueError(f"Invalid force login type: {self.force_login_type}")
        return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(  # pyright: ignore[reportUnannotatedClassAttribute]
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
