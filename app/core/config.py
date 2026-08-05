"""Explicit, validated runtime configuration for the application."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_DEVELOPMENT_JWT_SECRET = "development-only-secret-not-for-production"
_PLACEHOLDER_SECRET_MARKERS = ("development", "example", "placeholder", "change-me", "changeme")
_MAX_TUNABLE_VALUE = 1_000_000


class Settings(BaseSettings):
    """Settings constructed at an application composition boundary and injected onward."""

    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        populate_by_name=True,
    )

    app_env: Environment = Field(default="development", validation_alias="APP_ENV")
    database_url: str = Field(default="sqlite:///./bookmarks.db", validation_alias="DATABASE_URL")
    jwt_secret: SecretStr = Field(
        default_factory=lambda: SecretStr(_DEVELOPMENT_JWT_SECRET),
        validation_alias="JWT_SECRET",
    )
    access_token_ttl_minutes: Annotated[int, Field(ge=1, le=1_440)] = Field(
        default=30, validation_alias="ACCESS_TOKEN_TTL_MINUTES"
    )
    top_tags_limit: Annotated[int, Field(ge=1, le=100)] = Field(
        default=5, validation_alias="TOP_TAGS_LIMIT"
    )
    stats_refresh_enabled: bool = Field(default=True, validation_alias="STATS_REFRESH_ENABLED")
    stats_refresh_interval_seconds: Annotated[int, Field(ge=1, le=3_600)] = Field(
        default=10, validation_alias="STATS_REFRESH_INTERVAL_SECONDS"
    )
    stats_stale_after_seconds: Annotated[int, Field(ge=1, le=3_600)] = Field(
        default=30, validation_alias="STATS_STALE_AFTER_SECONDS"
    )
    stats_initial_refresh_timeout_seconds: Annotated[int, Field(ge=0, le=60)] = Field(
        default=5, validation_alias="STATS_INITIAL_REFRESH_TIMEOUT_SECONDS"
    )
    stats_shutdown_timeout_seconds: Annotated[int, Field(ge=1, le=60)] = Field(
        default=5, validation_alias="STATS_SHUTDOWN_TIMEOUT_SECONDS"
    )
    stats_full_reconciliation_seconds: Annotated[int, Field(ge=1, le=3_600)] = Field(
        default=300, validation_alias="STATS_FULL_RECONCILIATION_SECONDS"
    )
    stats_event_queue_capacity: Annotated[int, Field(ge=1, le=_MAX_TUNABLE_VALUE)] = Field(
        default=1_000, validation_alias="STATS_EVENT_QUEUE_CAPACITY"
    )
    stats_dirty_max_age_seconds: Annotated[int, Field(ge=1, le=3_600)] = Field(
        default=60, validation_alias="STATS_DIRTY_MAX_AGE_SECONDS"
    )
    stats_dirty_max_count: Annotated[int, Field(ge=1, le=_MAX_TUNABLE_VALUE)] = Field(
        default=1_000, validation_alias="STATS_DIRTY_MAX_COUNT"
    )
    app_worker_count: Annotated[int, Field(ge=1, le=_MAX_TUNABLE_VALUE)] = Field(
        default=1, validation_alias="APP_WORKER_COUNT"
    )
    sqlite_busy_timeout_milliseconds: Annotated[int, Field(ge=1, le=60_000)] = Field(
        default=5_000, validation_alias="SQLITE_BUSY_TIMEOUT_MILLISECONDS"
    )
    log_level: LogLevel = Field(default="INFO", validation_alias="LOG_LEVEL")

    @field_validator("database_url")
    @classmethod
    def validate_local_sqlite_url(cls, value: str) -> str:
        """Accept only local SQLite URLs; remote database support is out of scope."""
        if not value.startswith("sqlite:///"):
            msg = "DATABASE_URL must be a local SQLite URL beginning with sqlite:///"
            raise ValueError(msg)
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_cross_field_constraints(self) -> Settings:
        interval = self.stats_refresh_interval_seconds
        if self.stats_stale_after_seconds < interval:
            raise ValueError("STATS_STALE_AFTER_SECONDS must be at least the refresh interval")
        if self.stats_full_reconciliation_seconds < interval:
            raise ValueError(
                "STATS_FULL_RECONCILIATION_SECONDS must be at least the refresh interval"
            )
        if self.stats_dirty_max_age_seconds < interval:
            raise ValueError("STATS_DIRTY_MAX_AGE_SECONDS must be at least the refresh interval")
        if self.stats_refresh_enabled and self.app_worker_count != 1:
            raise ValueError("APP_WORKER_COUNT must equal 1 while STATS_REFRESH_ENABLED is true")

        secret = self.jwt_secret.get_secret_value()
        if self.app_env == "production" and (
            len(secret) < 32
            or secret == _DEVELOPMENT_JWT_SECRET
            or any(marker in secret.lower() for marker in _PLACEHOLDER_SECRET_MARKERS)
        ):
            raise ValueError(
                "JWT_SECRET must be a non-placeholder value of at least 32 characters in production"
            )
        return self
