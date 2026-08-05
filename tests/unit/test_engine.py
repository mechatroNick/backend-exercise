"""Tests for engine-local SQLite connection policy and session lifecycle seams."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import text
from sqlmodel import Session

from app.core.config import Settings
from app.db.engine import (
    SessionFactory,
    _connection_policy,
    create_database_engine,
    create_session_factory,
    session_dependency,
    session_scope,
)


@pytest.mark.parametrize("in_memory", [True, False])
def test_engine_applies_sqlite_policy_to_each_connection(in_memory: bool, tmp_path: Path) -> None:
    database_url = "sqlite:///:memory:" if in_memory else f"sqlite:///{tmp_path / 'bookmarks.db'}"
    engine = create_database_engine(
        database_url=database_url,
        busy_timeout_milliseconds=4_321,
    )
    try:
        with engine.connect() as first_connection, engine.connect() as second_connection:
            for connection in (first_connection, second_connection):
                assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
                assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 4_321
    finally:
        engine.dispose()


def test_engine_uses_settings_timeout_and_is_configured_lazily(
    tmp_path: pytest.TempPathFactory,
) -> None:
    database_path = tmp_path / "bookmarks.db"
    settings = Settings(
        database_url=f"sqlite:///{database_path}", sqlite_busy_timeout_milliseconds=5_555
    )

    engine = create_database_engine(settings)
    try:
        assert not database_path.exists()
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 5_555
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("kwargs", "exception", "message"),
    [
        (
            {"database_url": "postgresql://db.example/bookmarks", "busy_timeout_milliseconds": 5},
            ValueError,
            "local SQLite",
        ),
        (
            {"database_url": "sqlite://remote-host/bookmarks", "busy_timeout_milliseconds": 5},
            ValueError,
            "local SQLite",
        ),
        (
            {"database_url": "", "busy_timeout_milliseconds": 5},
            ValueError,
            "valid local SQLite",
        ),
        (
            {"database_url": "sqlite:///:memory:", "busy_timeout_milliseconds": 0},
            ValueError,
            "between 1 and 60000",
        ),
        (
            {"database_url": "sqlite:///:memory:", "busy_timeout_milliseconds": True},
            TypeError,
            "integer",
        ),
    ],
)
def test_engine_rejects_invalid_explicit_configuration(
    kwargs: dict[str, object], exception: type[Exception], message: str
) -> None:
    with pytest.raises(exception, match=message):
        create_database_engine(**kwargs)  # type: ignore[arg-type]


def test_engine_requires_one_complete_configuration_boundary() -> None:
    with pytest.raises(ValueError, match="required without Settings"):
        create_database_engine(database_url="sqlite:///:memory:")
    with pytest.raises(ValueError, match="not both"):
        create_database_engine(
            Settings(), database_url="sqlite:///:memory:", busy_timeout_milliseconds=10
        )


@pytest.mark.parametrize(("foreign_keys", "busy_timeout"), [(0, 5_000), (1, 4_999)])
def test_connection_policy_fails_closed_and_closes_its_cursor(
    foreign_keys: int, busy_timeout: int
) -> None:
    class FakeCursor:
        def __init__(self) -> None:
            self.closed = False
            self.statements: list[str] = []
            self.results = [(foreign_keys,), (busy_timeout,)]

        def close(self) -> None:
            self.closed = True

        def execute(self, statement: str) -> FakeCursor:
            self.statements.append(statement)
            return self

        def fetchone(self) -> tuple[int]:
            return self.results.pop(0)

    class FakeConnection:
        def __init__(self, cursor: FakeCursor) -> None:
            self.cursor_instance = cursor

        def cursor(self) -> FakeCursor:
            return self.cursor_instance

    cursor = FakeCursor()

    with pytest.raises(RuntimeError, match="could not be applied"):
        _connection_policy(5_000)(cast(object, FakeConnection(cursor)), object())

    assert cursor.closed is True
    assert cursor.statements == [
        "PRAGMA foreign_keys = ON",
        "PRAGMA busy_timeout = 5000",
        "PRAGMA foreign_keys",
        "PRAGMA busy_timeout",
    ]


def test_session_factory_returns_short_lived_sqlmodel_sessions() -> None:
    engine = create_database_engine(
        database_url="sqlite:///:memory:", busy_timeout_milliseconds=1_000
    )
    try:
        factory = create_session_factory(engine)
        with session_scope(factory) as session:
            assert isinstance(session, Session)
            assert session.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()


def test_session_scope_rolls_back_and_closes_without_committing() -> None:
    events: list[str] = []

    class SpySession:
        def rollback(self) -> None:
            events.append("rollback")

        def close(self) -> None:
            events.append("close")

    def session_factory() -> Session:
        return cast(Session, SpySession())

    with (
        pytest.raises(RuntimeError, match="failure"),
        session_scope(cast(SessionFactory, session_factory)),
    ):
        raise RuntimeError("failure")

    assert events == ["rollback", "close"]


def test_session_dependency_closes_the_yielded_session() -> None:
    events: list[str] = []

    class SpySession:
        def rollback(self) -> None:
            events.append("rollback")

        def close(self) -> None:
            events.append("close")

    dependency = session_dependency(cast(SessionFactory, lambda: cast(Session, SpySession())))
    generator = dependency()

    next(generator)
    generator.close()

    assert events == ["close"]
