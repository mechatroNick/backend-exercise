"""Integration evidence for the safe deterministic seed command."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, event
from sqlmodel import Session, select

from alembic import command
from app.auth.models import User
from app.bookmarks.models import Bookmark, BookmarkTag, Tag
from app.seed import (
    _SEED_BOOKMARKS,
    SeedConflictError,
    SeedSafetyError,
    main,
    seed_database,
)


def _state(engine: Engine) -> tuple[list[User], list[Bookmark], list[Tag], list[BookmarkTag]]:
    with Session(engine) as session:
        return (
            list(session.exec(select(User))),
            list(session.exec(select(Bookmark))),
            list(session.exec(select(Tag))),
            list(session.exec(select(BookmarkTag))),
        )


def test_seed_first_run_repeat_and_deterministic_fixed_records(migrated_engine: Engine) -> None:
    first = seed_database(migrated_engine)
    first_state = _state(migrated_engine)
    second = seed_database(migrated_engine)

    users, bookmarks, tags, links = first_state
    assert first.as_context() == {
        "created_records": 6,
        "unchanged_seed_records": 0,
    }
    assert second.as_context() == {
        "created_records": 0,
        "unchanged_seed_records": 3,
    }
    assert [(user.username, user.email) for user in users] == [
        ("fictional-reader", "fictional-reader@example.test")
    ]
    assert [(bookmark.url, bookmark.title, bookmark.created_at) for bookmark in bookmarks] == [
        (item.url, item.title, item.created_at) for item in _SEED_BOOKMARKS
    ]
    assert [tag.name for tag in tags] == ["fiction", "reading", "reference"]
    assert len(links) == 4
    assert _state(migrated_engine) == first_state


def test_seed_preserves_unrelated_rows_and_can_complete_partial_compatible_state(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        unrelated = User(
            username="unrelated-user",
            email="unrelated@example.test",
            password_hash="$argon2id$unrelated",
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        session.add(unrelated)
        session.commit()

    seed_database(migrated_engine)
    with Session(migrated_engine) as session:
        missing_bookmark = session.exec(
            select(Bookmark).where(Bookmark.url == _SEED_BOOKMARKS[1].url)
        ).one()
        session.delete(missing_bookmark)
        session.commit()

    result = seed_database(migrated_engine)

    users, bookmarks, _tags, _links = _state(migrated_engine)
    assert result.bookmarks_created == 1
    assert [(user.username, user.email) for user in users] == [
        ("unrelated-user", "unrelated@example.test"),
        ("fictional-reader", "fictional-reader@example.test"),
    ]
    assert len(bookmarks) == 2


def test_seed_rejects_partial_identity_conflict_without_mutating(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        session.add(
            User(
                username="fictional-reader",
                email="different@example.test",
                password_hash="$argon2id$existing",
                created_at=datetime(2025, 1, 1, tzinfo=UTC),
            )
        )
        session.commit()

    with pytest.raises(SeedConflictError):
        seed_database(migrated_engine)

    users, bookmarks, tags, links = _state(migrated_engine)
    assert len(users) == 1
    assert bookmarks == []
    assert tags == []
    assert links == []


def test_seed_rolls_back_all_rows_when_link_insert_fails(migrated_engine: Engine) -> None:
    def fail_link_insert(*args: object) -> None:
        if "insert into bookmark_tags" in str(args[2]).lower():
            raise RuntimeError("forced database failure")

    event.listen(migrated_engine, "before_cursor_execute", fail_link_insert)
    try:
        with pytest.raises(RuntimeError, match="forced database failure"):
            seed_database(migrated_engine)
    finally:
        event.remove(migrated_engine, "before_cursor_execute", fail_link_insert)

    assert _state(migrated_engine) == ([], [], [], [])


def test_seed_rejects_unmigrated_database(database_url: str) -> None:
    from app.db.engine import create_database_engine

    engine = create_database_engine(database_url=database_url, busy_timeout_milliseconds=1_000)
    try:
        with pytest.raises(SeedSafetyError, match="Alembic"):
            seed_database(engine)
    finally:
        engine.dispose()


@pytest.mark.parametrize("database_url", [None, "postgresql://unsafe.example.test/bookmarks"])
def test_seed_cli_rejects_missing_or_unsafe_target_without_logging_configuration_values(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    database_url: str | None,
) -> None:
    if database_url is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", database_url)

    assert main() == 2

    output = capsys.readouterr().err
    payload = json.loads(output)
    assert payload["event"] == "seed.rejected"
    assert "DATABASE_URL" not in output
    assert "sqlite:///" not in output


def test_seed_cli_rejects_an_explicit_production_environment_before_engine_creation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main({"DATABASE_URL": "sqlite:///:memory:", "APP_ENV": "production"}) == 2

    output = capsys.readouterr().err
    payload = json.loads(output)
    assert payload["event"] == "seed.rejected"
    assert "production" not in output
    assert "sqlite:///" not in output


def test_seed_cli_logs_safe_json_summary_without_fixture_or_url_leakage(
    migration_config: Config, database_url: str
) -> None:
    command.upgrade(migration_config, "head")
    result = subprocess.run(
        [sys.executable, "-m", "app.seed"],
        cwd=Path(__file__).resolve().parents[2],
        env={"DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    payload = json.loads(combined)
    assert payload["event"] == "seed.completed"
    assert payload["context"] == {
        "created_records": 6,
        "unchanged_seed_records": 0,
    }
    assert database_url not in combined
    assert "fictional-seed-password-only" not in combined
    assert "Field Notes" not in combined
