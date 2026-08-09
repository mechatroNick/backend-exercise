"""Tests for explicit application settings."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_SETTINGS_ENV_NAMES = (
    "APP_ENV",
    "DATABASE_URL",
    "JWT_SECRET",
    "ACCESS_TOKEN_TTL_MINUTES",
    "TOP_TAGS_LIMIT",
    "STATS_REFRESH_ENABLED",
    "STATS_REFRESH_INTERVAL_SECONDS",
    "STATS_STALE_AFTER_SECONDS",
    "STATS_INITIAL_REFRESH_TIMEOUT_SECONDS",
    "STATS_SHUTDOWN_TIMEOUT_SECONDS",
    "STATS_FULL_RECONCILIATION_SECONDS",
    "STATS_EVENT_QUEUE_CAPACITY",
    "STATS_DIRTY_MAX_AGE_SECONDS",
    "STATS_DIRTY_MAX_COUNT",
    "APP_WORKER_COUNT",
    "RATE_LIMIT_ENABLED",
    "RATE_LIMIT_AUTH_REQUESTS",
    "RATE_LIMIT_AUTH_WINDOW_SECONDS",
    "RATE_LIMIT_BOOKMARK_REQUESTS",
    "RATE_LIMIT_BOOKMARK_WINDOW_SECONDS",
    "RATE_LIMIT_MAX_KEYS",
    "RATE_LIMIT_IDLE_TTL_SECONDS",
    "CURSOR_TTL_SECONDS",
    "SQLITE_BUSY_TIMEOUT_MILLISECONDS",
    "LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def isolate_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _SETTINGS_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_defaults_are_safe_for_non_production() -> None:
    settings = Settings()

    assert settings.app_env == "development"
    assert settings.database_url == "sqlite:///./bookmarks.db"
    assert settings.access_token_ttl_minutes == 30
    assert settings.top_tags_limit == 5
    assert settings.stats_refresh_enabled is True
    assert settings.app_worker_count == 1
    assert settings.rate_limit_enabled is True
    assert settings.rate_limit_auth_requests == 10
    assert settings.rate_limit_auth_window_seconds == 60
    assert settings.rate_limit_bookmark_requests == 120
    assert settings.rate_limit_bookmark_window_seconds == 60
    assert settings.rate_limit_max_keys == 10_000
    assert settings.rate_limit_idle_ttl_seconds == 300
    assert settings.cursor_ttl_seconds == 900
    assert settings.sqlite_busy_timeout_milliseconds == 5_000
    assert settings.log_level == "INFO"


def test_environment_aliases_load_without_double_app_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("TOP_TAGS_LIMIT", "9")
    monkeypatch.setenv("RATE_LIMIT_AUTH_REQUESTS", "9")
    monkeypatch.setenv("LOG_LEVEL", "debug")

    settings = Settings()

    assert settings.app_env == "test"
    assert settings.database_url == "sqlite:///:memory:"
    assert settings.top_tags_limit == 9
    assert settings.rate_limit_auth_requests == 9
    assert settings.log_level == "DEBUG"


def test_explicit_constructor_values_take_precedence_over_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TOP_TAGS_LIMIT", "9")

    assert Settings(top_tags_limit=7).top_tags_limit == 7


@pytest.mark.parametrize(
    ("database_url", "message"),
    [
        ("postgresql://db.example/bookmarks", "local SQLite"),
        ("sqlite://remote-host/bookmarks", "local SQLite"),
    ],
)
def test_database_url_must_be_local_sqlite(database_url: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(database_url=database_url)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"access_token_ttl_minutes": 0}, "greater than or equal"),
        ({"access_token_ttl_minutes": 1_441}, "less than or equal"),
        ({"top_tags_limit": 0}, "greater than or equal"),
        ({"top_tags_limit": 101}, "less than or equal"),
        ({"stats_refresh_interval_seconds": 0}, "greater than or equal"),
        ({"stats_refresh_interval_seconds": 3_601}, "less than or equal"),
        ({"stats_stale_after_seconds": 0}, "greater than or equal"),
        ({"stats_stale_after_seconds": 3_601}, "less than or equal"),
        ({"stats_initial_refresh_timeout_seconds": -1}, "greater than or equal"),
        ({"stats_initial_refresh_timeout_seconds": 61}, "less than or equal"),
        ({"stats_shutdown_timeout_seconds": 0}, "greater than or equal"),
        ({"stats_shutdown_timeout_seconds": 61}, "less than or equal"),
        ({"stats_full_reconciliation_seconds": 0}, "greater than or equal"),
        ({"stats_full_reconciliation_seconds": 3_601}, "less than or equal"),
        ({"stats_event_queue_capacity": 0}, "greater than or equal"),
        ({"stats_event_queue_capacity": 1_000_001}, "less than or equal"),
        ({"stats_dirty_max_age_seconds": 0}, "greater than or equal"),
        ({"stats_dirty_max_age_seconds": 3_601}, "less than or equal"),
        ({"stats_dirty_max_count": 0}, "greater than or equal"),
        ({"stats_dirty_max_count": 1_000_001}, "less than or equal"),
        ({"app_worker_count": 0}, "greater than or equal"),
        ({"rate_limit_auth_requests": 0}, "greater than or equal"),
        ({"rate_limit_auth_requests": 10_001}, "less than or equal"),
        ({"rate_limit_auth_window_seconds": 0}, "greater than or equal"),
        ({"rate_limit_auth_window_seconds": 3_601}, "less than or equal"),
        ({"rate_limit_bookmark_requests": 0}, "greater than or equal"),
        ({"rate_limit_bookmark_requests": 10_001}, "less than or equal"),
        ({"rate_limit_bookmark_window_seconds": 0}, "greater than or equal"),
        ({"rate_limit_bookmark_window_seconds": 3_601}, "less than or equal"),
        ({"rate_limit_max_keys": 0}, "greater than or equal"),
        ({"rate_limit_max_keys": 100_001}, "less than or equal"),
        ({"rate_limit_idle_ttl_seconds": 0}, "greater than or equal"),
        ({"rate_limit_idle_ttl_seconds": 86_401}, "less than or equal"),
        ({"cursor_ttl_seconds": 59}, "greater than or equal"),
        ({"cursor_ttl_seconds": 3_601}, "less than or equal"),
        ({"sqlite_busy_timeout_milliseconds": 0}, "greater than or equal"),
        ({"sqlite_busy_timeout_milliseconds": 60_001}, "less than or equal"),
        (
            {"stats_refresh_enabled": False, "app_worker_count": 1_000_001},
            "less than or equal",
        ),
        ({"log_level": "TRACE"}, "literal_error"),
        ({"app_env": "staging"}, "literal_error"),
    ],
)
def test_individual_setting_ranges_are_enforced(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(**kwargs)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"stats_stale_after_seconds": 9}, "STALE_AFTER"),
        ({"stats_full_reconciliation_seconds": 9}, "FULL_RECONCILIATION"),
        ({"stats_dirty_max_age_seconds": 9}, "DIRTY_MAX_AGE"),
        ({"app_worker_count": 2}, "APP_WORKER_COUNT"),
        ({"rate_limit_idle_ttl_seconds": 59}, "RATE_LIMIT_IDLE_TTL_SECONDS"),
        (
            {"stats_refresh_enabled": False, "rate_limit_enabled": True, "app_worker_count": 2},
            "APP_WORKER_COUNT",
        ),
    ],
)
def test_cross_field_constraints_are_enforced(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(**kwargs)


def test_multiple_workers_are_allowed_when_refresher_is_disabled() -> None:
    settings = Settings(
        stats_refresh_enabled=False,
        rate_limit_enabled=False,
        app_worker_count=2,
    )

    assert settings.app_worker_count == 2


@pytest.mark.parametrize(
    "secret",
    [
        None,
        "development-only-secret-not-for-production",
        "placeholder-secret-that-is-definitely-long-enough",
        "short-secret",
    ],
)
def test_production_rejects_missing_placeholder_and_weak_secrets(secret: str | None) -> None:
    kwargs: dict[str, object] = {"app_env": "production"}
    if secret is not None:
        kwargs["jwt_secret"] = secret

    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(**kwargs)


def test_production_accepts_a_strong_non_placeholder_secret() -> None:
    settings = Settings(app_env="production", jwt_secret="a-unique-production-secret-with-32-chars")

    assert settings.app_env == "production"


def test_production_cannot_disable_the_local_rate_limit() -> None:
    with pytest.raises(ValidationError, match="RATE_LIMIT_ENABLED"):
        Settings(
            app_env="production",
            jwt_secret="a-unique-production-secret-with-32-chars",
            rate_limit_enabled=False,
        )


def test_secret_representation_and_dump_are_redacted() -> None:
    settings = Settings(jwt_secret="not-for-logs-very-sensitive-secret")

    assert "not-for-logs-very-sensitive-secret" not in repr(settings.jwt_secret)
    assert "not-for-logs-very-sensitive-secret" not in repr(settings.model_dump())
    assert settings.model_dump(mode="json")["jwt_secret"] == "**********"
