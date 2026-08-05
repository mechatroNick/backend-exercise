"""Real Alembic migration lifecycle and emitted-DDL evidence."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, inspect, text

from alembic import command
from app.db import engine as database_engine
from app.db.engine import create_database_engine

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_EXPECTED_TABLES = {"alembic_version", "bookmark_tags", "bookmarks", "tags", "users"}


def test_upgrade_builds_exact_schema_and_connection_policy(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)

    assert set(inspector.get_table_names()) == _EXPECTED_TABLES
    with (
        migrated_engine.connect() as first_connection,
        migrated_engine.connect() as second_connection,
    ):
        for connection in (first_connection, second_connection):
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
            assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 4_321
        assert first_connection.execute(text("PRAGMA foreign_key_check")).all() == []
        assert (
            MigrationContext.configure(first_connection).get_current_revision()
            == "0001_core_schema"
        )


def test_emitted_schema_has_named_constraints_foreign_keys_and_ordered_indexes(
    migrated_engine: Engine,
) -> None:
    inspector = inspect(migrated_engine)
    expected_indexes = {
        "bookmarks": {
            "ix_bookmarks_user_created_id": ["user_id", "created_at", "id"],
            "ix_bookmarks_user_updated_id": ["user_id", "updated_at", "id"],
        },
        "bookmark_tags": {"ix_bookmark_tags_tag_bookmark": ["tag_id", "bookmark_id"]},
    }
    expected_foreign_keys = {
        "bookmarks": {"fk_bookmarks_user_id_users": ("user_id", "users", "CASCADE")},
        "bookmark_tags": {
            "fk_bookmark_tags_bookmark_id_bookmarks": ("bookmark_id", "bookmarks", "CASCADE"),
            "fk_bookmark_tags_tag_id_tags": ("tag_id", "tags", "CASCADE"),
        },
    }
    expected_constraint_names = {
        "users": {
            "ck_users_username_nonblank",
            "ck_users_username_length",
            "ck_users_email_nonblank",
            "ck_users_password_hash_nonblank",
            "pk_users",
            "uq_users_username",
            "uq_users_email",
        },
        "tags": {"ck_tags_name_nonblank", "ck_tags_name_length", "pk_tags", "uq_tags_name"},
        "bookmarks": {
            "ck_bookmarks_url_nonblank",
            "ck_bookmarks_title_nonblank",
            "ck_bookmarks_title_length",
            "ck_bookmarks_description_length",
            "ck_bookmarks_updated_not_before_created",
            "fk_bookmarks_user_id_users",
            "pk_bookmarks",
        },
        "bookmark_tags": {
            "fk_bookmark_tags_bookmark_id_bookmarks",
            "fk_bookmark_tags_tag_id_tags",
            "pk_bookmark_tags",
        },
    }

    for table_name, expected in expected_indexes.items():
        assert {
            index["name"]: index["column_names"] for index in inspector.get_indexes(table_name)
        } == expected
    for table_name, expected in expected_foreign_keys.items():
        assert {
            foreign_key["name"]: (
                foreign_key["constrained_columns"][0],
                foreign_key["referred_table"],
                foreign_key["options"].get("ondelete"),
            )
            for foreign_key in inspector.get_foreign_keys(table_name)
        } == expected

    with migrated_engine.connect() as connection:
        for table_name, expected in expected_constraint_names.items():
            ddl = connection.execute(
                text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name"),
                {"name": table_name},
            ).scalar_one()
            assert all(constraint_name in ddl for constraint_name in expected)


def test_downgrade_removes_core_tables_and_reupgrade_restores_them(
    migration_config: Config, database_url: str
) -> None:
    command.upgrade(migration_config, "head")
    command.downgrade(migration_config, "base")
    engine = create_database_engine(
        database_url=database_url,
        busy_timeout_milliseconds=4_321,
    )
    try:
        assert inspect(engine).get_table_names() == ["alembic_version"]
    finally:
        engine.dispose()

    command.upgrade(migration_config, "head")
    engine = create_database_engine(
        database_url=database_url,
        busy_timeout_milliseconds=4_321,
    )
    try:
        assert set(inspect(engine).get_table_names()) == _EXPECTED_TABLES
    finally:
        engine.dispose()


def test_current_heads_and_autogenerate_check_are_clean(migration_config: Config) -> None:
    command.upgrade(migration_config, "head")

    command.current(migration_config)
    command.heads(migration_config)
    command.check(migration_config)


def test_command_uses_settings_database_url_when_alembic_config_has_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = f"sqlite:///{tmp_path / 'settings-resolved.sqlite3'}"
    config = Config(str(_REPOSITORY_ROOT / "alembic.ini"))
    monkeypatch.setenv("DATABASE_URL", database_url)

    command.upgrade(config, "head")

    engine = create_database_engine(database_url=database_url, busy_timeout_milliseconds=4_321)
    try:
        with engine.connect() as connection:
            assert (
                MigrationContext.configure(connection).get_current_revision() == "0001_core_schema"
            )
    finally:
        engine.dispose()


def test_offline_migration_mode_fails_instead_of_bypassing_connection_policy(
    migration_config: Config,
) -> None:
    with pytest.raises(RuntimeError, match="offline migrations are unsupported"):
        command.upgrade(migration_config, "head", sql=True)


def test_migration_fails_closed_when_the_connection_policy_cannot_enable_foreign_keys(
    migration_config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    def disable_connection_policy(_timeout: int) -> object:
        return lambda _connection, _record: None

    monkeypatch.setattr(database_engine, "_connection_policy", disable_connection_policy)

    with pytest.raises(RuntimeError, match="Alembic requires SQLite foreign_keys=ON"):
        command.upgrade(migration_config, "head")


def test_importing_persistence_modules_does_not_create_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "unmigrated.sqlite3"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path}"

    completed = subprocess.run(
        [sys.executable, "-c", "import app.db.engine; import app.db.models"],
        cwd=_REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert not database_path.exists()
