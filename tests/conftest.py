"""Shared fixtures that build isolated SQLite databases through real Alembic revisions."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine

from alembic import command
from app.db.engine import create_database_engine

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_BUSY_TIMEOUT_MILLISECONDS = 4_321


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    """Provide a unique file-backed SQLite URL without creating a database yet."""
    return f"sqlite:///{tmp_path / 'track01.sqlite3'}"


@pytest.fixture
def migration_config(database_url: str) -> Config:
    """Build an Alembic config pointed at this test's disposable SQLite file."""
    config = Config(str(_REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_REPOSITORY_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture
def migrated_engine(migration_config: Config, database_url: str) -> Iterator[Engine]:
    """Upgrade a disposable file database through Alembic before exposing an app engine."""
    command.upgrade(migration_config, "head")
    engine = create_database_engine(
        database_url=database_url,
        busy_timeout_milliseconds=_BUSY_TIMEOUT_MILLISECONDS,
    )
    try:
        yield engine
    finally:
        engine.dispose()
