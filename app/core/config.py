from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Work Order Backend"
    app_env: str = "development"
    debug: bool = False
    database_url: str = Field(
        default="sqlite:///./local.db",
        description="Database connection string. Swap for PostgreSQL in higher environments.",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()