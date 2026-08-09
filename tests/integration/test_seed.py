"""Integration evidence for the safe deterministic seed command."""

from __future__ import annotations

import io
import json
import runpy
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, event
from sqlmodel import Session, select

import app.seed as seed
from alembic import command
from app.auth.models import User
from app.bookmarks.models import Bookmark, BookmarkTag, Tag
from app.seed import (
    _SEED_BOOKMARKS,
    SeedConflictError,
    SeedError,
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


def test_seed_rejects_duplicate_bookmark_seed_identity(migrated_engine: Engine) -> None:
    seed_database(migrated_engine)
    fixture = _SEED_BOOKMARKS[0]
    with Session(migrated_engine) as session:
        user = session.exec(select(User).where(User.username == "fictional-reader")).one()
        session.add(
            Bookmark(
                url=fixture.url,
                title=fixture.title,
                description=fixture.description,
                user_id=user.id,
                created_at=fixture.created_at,
                updated_at=fixture.created_at,
            )
        )
        session.commit()

    with pytest.raises(SeedConflictError, match="multiple existing bookmarks"):
        seed_database(migrated_engine)


@pytest.mark.parametrize("kind", ["scalar", "tags"])
def test_seed_rejects_existing_bookmark_fixture_divergence(
    migrated_engine: Engine, kind: str
) -> None:
    seed_database(migrated_engine)
    with Session(migrated_engine) as session:
        bookmark = session.exec(
            select(Bookmark).where(Bookmark.url == _SEED_BOOKMARKS[0].url)
        ).one()
        if kind == "scalar":
            bookmark.title = "Changed outside the fixture"
        else:
            link = session.exec(
                select(BookmarkTag).where(BookmarkTag.bookmark_id == bookmark.id)
            ).first()
            assert link is not None
            session.delete(link)
        session.add(bookmark)
        session.commit()

    with pytest.raises(SeedConflictError, match="existing bookmark conflicts"):
        seed_database(migrated_engine)


@pytest.mark.parametrize("value", [None, 0, -1, True, "1"])
def test_seed_rejects_invalid_persisted_identifiers(value: object) -> None:
    with pytest.raises(SeedError, match="persisted test did not receive"):
        seed._required_id(value, "test")

    assert seed._required_id(1, "test") == 1


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


def test_seed_settings_reject_invalid_environment_and_accepts_explicit_test_target() -> None:
    with pytest.raises(SeedSafetyError, match="APP_ENV is invalid"):
        seed._settings_from_explicit_environment(
            {"DATABASE_URL": "sqlite:///:memory:", "APP_ENV": "preview"}
        )

    settings = seed._settings_from_explicit_environment(
        {"DATABASE_URL": "sqlite:///:memory:", "APP_ENV": "test"}
    )
    assert settings.database_url == "sqlite:///:memory:"
    assert settings.app_env == "test"


def test_seed_explicit_environment_does_not_inherit_host_app_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "host-placeholder-must-not-affect-explicit-seed-mapping")
    monkeypatch.setenv("APP_WORKER_COUNT", "2")

    settings = seed._settings_from_explicit_environment(
        {"DATABASE_URL": "sqlite:///:memory:", "APP_ENV": "development"}
    )

    assert settings.app_env == "development"


class _DisposableEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


def test_seed_main_logs_success_and_disposes_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = io.StringIO()
    engine = _DisposableEngine()
    summary = seed.SeedSummary(users_created=1, bookmarks_created=2, tags_created=3)
    original_configure_logging = seed.configure_logging
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setattr(
        seed,
        "configure_logging",
        lambda settings: original_configure_logging(settings, stream=stream),
    )
    monkeypatch.setattr(seed, "create_database_engine", lambda settings: engine)
    monkeypatch.setattr(seed, "seed_database", lambda current_engine: summary)

    assert seed.main({"DATABASE_URL": "sqlite:///:memory:", "APP_ENV": "development"}) == 0
    assert engine.disposed is True
    payload = json.loads(stream.getvalue())
    assert payload["event"] == "seed.completed"
    assert payload["context"] == summary.as_context()


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_event"),
    [
        (SeedSafetyError("safe failure"), 2, "seed.rejected"),
        (RuntimeError("https://unsafe.example.test/secret-token"), 1, "seed.failed"),
    ],
)
def test_seed_main_logs_safe_failures_and_disposes_engine(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    expected_status: int,
    expected_event: str,
) -> None:
    stream = io.StringIO()
    engine = _DisposableEngine()
    original_configure_logging = seed.configure_logging
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setattr(
        seed,
        "configure_logging",
        lambda settings: original_configure_logging(settings, stream=stream),
    )
    monkeypatch.setattr(seed, "create_database_engine", lambda settings: engine)

    def fail_seed(current_engine: object) -> None:
        del current_engine
        raise failure

    monkeypatch.setattr(seed, "seed_database", fail_seed)

    assert seed.main({"DATABASE_URL": "sqlite:///:memory:"}) == expected_status
    assert engine.disposed is True
    payload = json.loads(stream.getvalue())
    assert payload["event"] == expected_event
    assert "unsafe.example.test" not in stream.getvalue()
    if expected_event == "seed.failed":
        assert payload["exception"]["message"] == "[REDACTED]"


def test_seed_module_main_boundary_exits_with_main_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit) as exited:
        runpy.run_path(str(Path(seed.__file__)), run_name="__main__")

    assert exited.value.code == 2


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
