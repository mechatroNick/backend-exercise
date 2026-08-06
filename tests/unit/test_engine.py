"""Tests for engine-local SQLite connection policy and session lifecycle seams."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session

from app.core.config import Settings
from app.db.engine import (
    SessionFactory,
    _connection_policy,
    begin_sqlite_read_snapshot,
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


def test_read_snapshot_promotes_legacy_logical_read_to_a_real_sqlite_transaction() -> None:
    engine = create_database_engine(
        database_url="sqlite:///:memory:", busy_timeout_milliseconds=1_000
    )
    session = Session(engine)
    statements: list[str] = []

    def record_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        connection = session.connection()
        driver_connection = connection.connection.driver_connection
        assert isinstance(driver_connection, sqlite3.Connection)

        assert session.execute(text("SELECT 1")).scalar_one() == 1
        assert session.in_transaction() is True
        assert driver_connection.in_transaction is False

        statements.clear()
        begin_sqlite_read_snapshot(session)

        assert driver_connection.in_transaction is True
        assert statements == ["BEGIN DEFERRED"]

        statements.clear()
        begin_sqlite_read_snapshot(session)

        assert statements == []
        assert driver_connection.in_transaction is True
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)
        session.close()
        engine.dispose()


def test_read_snapshot_reuses_an_existing_real_transaction_without_issuing_sql() -> None:
    engine = create_database_engine(
        database_url="sqlite:///:memory:", busy_timeout_milliseconds=1_000
    )
    session = Session(engine)
    statements: list[str] = []

    def record_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        connection = session.connection()
        driver_connection = connection.connection.driver_connection
        assert isinstance(driver_connection, sqlite3.Connection)
        connection.exec_driver_sql("BEGIN DEFERRED")
        assert driver_connection.in_transaction is True

        statements.clear()
        begin_sqlite_read_snapshot(session)

        assert statements == []
        assert driver_connection.in_transaction is True
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)
        session.close()
        engine.dispose()


def test_read_snapshot_does_not_complete_the_transaction_and_session_close_clears_it() -> None:
    engine = create_database_engine(
        database_url="sqlite:///:memory:", busy_timeout_milliseconds=1_000
    )
    session = Session(engine)
    transaction_events: list[str] = []
    event.listen(engine, "commit", lambda _connection: transaction_events.append("commit"))
    event.listen(engine, "rollback", lambda _connection: transaction_events.append("rollback"))
    try:
        connection = session.connection()
        driver_connection = connection.connection.driver_connection
        assert isinstance(driver_connection, sqlite3.Connection)

        begin_sqlite_read_snapshot(session)

        assert driver_connection.in_transaction is True
        assert transaction_events == []
        session.close()
        assert driver_connection.in_transaction is False
        assert transaction_events == ["rollback"]
    finally:
        if session.is_active:
            session.close()
        engine.dispose()


@pytest.mark.parametrize(
    ("connection", "message"),
    [
        (
            SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
            "require a SQLite connection",
        ),
        (
            SimpleNamespace(
                dialect=SimpleNamespace(name="sqlite"),
                connection=SimpleNamespace(driver_connection=object()),
            ),
            "require a sqlite3 driver connection",
        ),
        (
            SimpleNamespace(dialect=SimpleNamespace(name="sqlite"), connection=object()),
            "require a sqlite3 driver connection",
        ),
    ],
)
def test_read_snapshot_rejects_unsupported_dialects_and_drivers(
    connection: object, message: str
) -> None:
    class FakeSession:
        def connection(self) -> object:
            return connection

    with pytest.raises(RuntimeError, match=message):
        begin_sqlite_read_snapshot(cast(Session, FakeSession()))


def test_read_snapshot_wraps_a_driver_begin_failure() -> None:
    driver_connection = sqlite3.connect(":memory:")

    class FakeConnection:
        dialect = SimpleNamespace(name="sqlite")
        connection = SimpleNamespace(driver_connection=driver_connection)

        def exec_driver_sql(self, statement: str) -> None:
            assert statement == "BEGIN DEFERRED"
            raise OperationalError(statement, {}, RuntimeError("driver unavailable"))

    class FakeSession:
        def connection(self) -> FakeConnection:
            return FakeConnection()

    try:
        with pytest.raises(RuntimeError, match="could not begin") as error:
            begin_sqlite_read_snapshot(cast(Session, FakeSession()))
    finally:
        driver_connection.close()

    assert isinstance(error.value.__cause__, OperationalError)


def test_read_snapshot_fails_closed_when_begin_does_not_start_a_driver_transaction() -> None:
    driver_connection = sqlite3.connect(":memory:")

    class FakeConnection:
        dialect = SimpleNamespace(name="sqlite")
        connection = SimpleNamespace(driver_connection=driver_connection)

        def exec_driver_sql(self, statement: str) -> None:
            assert statement == "BEGIN DEFERRED"

    class FakeSession:
        def connection(self) -> FakeConnection:
            return FakeConnection()

    try:
        with pytest.raises(RuntimeError, match="did not start"):
            begin_sqlite_read_snapshot(cast(Session, FakeSession()))
    finally:
        driver_connection.close()


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
