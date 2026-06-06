from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Work Order Backend"
    app_env: str = "development"
    debug: bool = False
    backend_cors_origins: list[str] = Field(
        default=["http://127.0.0.1:5173", "http://localhost:5173"],
        description="Allowed origins for browser clients. Override in non-local environments.",
    )
    database_url: str = Field(
        default="sqlite:///./local.db",
        description="Database connection string. Swap for PostgreSQL in higher environments.",
    )
    work_order_attachments_dir: str = Field(
        default="./storage/work_order_attachments",
        description="Local filesystem directory for work order attachments.",
    )
    work_order_attachment_max_size_bytes: int = Field(
        default=10 * 1024 * 1024,
        gt=0,
        description="Maximum allowed attachment size in bytes.",
    )
    jwt_secret: str = Field(
        default="lakiernia-tuszko-secret-2026",
        description="Secret key for signing JWT tokens.",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_work_order_attachments_path() -> Path:
    return Path(get_settings().work_order_attachments_dir).resolve()