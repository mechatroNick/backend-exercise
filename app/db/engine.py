"""Synchronous SQLModel engine and short-lived session infrastructure."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session
from sqlmodel import create_engine as sqlmodel_create_engine

from app.core.config import Settings

_MIN_BUSY_TIMEOUT_MILLISECONDS = 1
_MAX_BUSY_TIMEOUT_MILLISECONDS = 60_000
SessionFactory = Callable[[], Session]


def _validate_sqlite_url(database_url: str) -> URL:
    """Reject non-local SQLite URLs before creating a connection-capable engine."""
    try:
        url = make_url(database_url)
    except Exception as exc:
        msg = "database_url must be a valid local SQLite URL"
        raise ValueError(msg) from exc
    if url.get_backend_name() != "sqlite" or url.host is not None:
        msg = "database_url must be a local SQLite URL"
        raise ValueError(msg)
    return url


def _validate_busy_timeout_milliseconds(value: int) -> int:
    """Keep the SQLite lock wait finite and aligned with the Settings boundary."""
    if isinstance(value, bool) or not isinstance(value, int):
        msg = "busy_timeout_milliseconds must be an integer"
        raise TypeError(msg)
    if not _MIN_BUSY_TIMEOUT_MILLISECONDS <= value <= _MAX_BUSY_TIMEOUT_MILLISECONDS:
        msg = "busy_timeout_milliseconds must be between 1 and 60000"
        raise ValueError(msg)
    return value


def _connection_policy(busy_timeout_milliseconds: int) -> Callable[..., None]:
    """Build an engine-scoped SQLite DB-API connection hook."""

    def configure_connection(
        dbapi_connection: sqlite3.Connection, _connection_record: object
    ) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute(f"PRAGMA busy_timeout = {busy_timeout_milliseconds}")
            foreign_keys = cursor.execute("PRAGMA foreign_keys").fetchone()[0]
            busy_timeout = cursor.execute("PRAGMA busy_timeout").fetchone()[0]
        finally:
            cursor.close()
        if foreign_keys != 1 or busy_timeout != busy_timeout_milliseconds:
            msg = "SQLite connection policy could not be applied"
            raise RuntimeError(msg)

    return configure_connection


def create_database_engine(
    settings: Settings | None = None,
    *,
    database_url: str | None = None,
    busy_timeout_milliseconds: int | None = None,
) -> Engine:
    """Create one synchronous, local SQLite engine without schema or session side effects."""
    if settings is not None:
        if database_url is not None or busy_timeout_milliseconds is not None:
            msg = "pass Settings or explicit database_url and busy_timeout_milliseconds, not both"
            raise ValueError(msg)
        database_url = settings.database_url
        busy_timeout_milliseconds = settings.sqlite_busy_timeout_milliseconds
    elif database_url is None or busy_timeout_milliseconds is None:
        msg = "explicit database_url and busy_timeout_milliseconds are required without Settings"
        raise ValueError(msg)

    _validate_sqlite_url(database_url)
    timeout = _validate_busy_timeout_milliseconds(busy_timeout_milliseconds)
    engine = sqlmodel_create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _connection_policy(timeout))
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a caller-owned factory for short-lived synchronous SQLModel sessions."""
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def begin_sqlite_read_snapshot(session: Session) -> None:
    """Start one SQLite read snapshot without taking ownership of session completion.

    SQLAlchemy can consider a session transaction active after a read even while
    SQLite's DB-API connection has not started a real read transaction.  Statistics
    callers use this explicit seam before their first aggregate read so later
    statements observe the same SQLite snapshot.
    """
    connection = session.connection()
    if connection.dialect.name != "sqlite":
        msg = "SQLite read snapshots require a SQLite connection"
        raise RuntimeError(msg)

    try:
        driver_connection = connection.connection.driver_connection
    except AttributeError as error:
        msg = "SQLite read snapshots require a sqlite3 driver connection"
        raise RuntimeError(msg) from error
    if not isinstance(driver_connection, sqlite3.Connection):
        msg = "SQLite read snapshots require a sqlite3 driver connection"
        raise RuntimeError(msg)
    if driver_connection.in_transaction:
        return

    try:
        connection.exec_driver_sql("BEGIN DEFERRED")
    except SQLAlchemyError as error:
        msg = "SQLite read snapshot could not begin"
        raise RuntimeError(msg) from error
    if not driver_connection.in_transaction:
        msg = "SQLite read snapshot did not start a driver transaction"
        raise RuntimeError(msg)


@contextmanager
def session_scope(session_factory: SessionFactory) -> Iterator[Session]:
    """Yield one session, roll it back on failure, and always close it without committing."""
    session = session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def session_dependency(
    session_factory: SessionFactory,
) -> Callable[[], Generator[Session, None, None]]:
    """Return a FastAPI-compatible dependency seam while keeping session ownership explicit."""

    def dependency() -> Generator[Session, None, None]:
        with session_scope(session_factory) as session:
            yield session

    return dependency
