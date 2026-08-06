"""SQLite read-snapshot integration evidence for Track 04 statistics readers."""

from __future__ import annotations

from sqlalchemy import Engine, text
from sqlmodel import Session

from app.db.engine import begin_sqlite_read_snapshot


def _generation_count(session: Session) -> int:
    """Use the same shape as an auth-scoped aggregate before statistics reads exist."""
    return session.execute(
        text("SELECT count(*) FROM users WHERE email LIKE :email_pattern"),
        {"email_pattern": "snapshot-generation-%@example.test"},
    ).scalar_one()


def test_explicit_read_snapshot_keeps_one_generation_across_a_wal_writer(
    migrated_engine: Engine,
) -> None:
    """WAL enables this deterministic scheduling proof; it is not production policy."""
    with migrated_engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode = WAL").scalar_one() == "wal"
        connection.commit()

    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (username, email, password_hash, created_at) "
                "VALUES (:username, :email, :password_hash, :created_at)"
            ),
            {
                "username": "snapshot-generation-a",
                "email": "snapshot-generation-a@example.test",
                "password_hash": "test-only-noncredential-marker",
                "created_at": "2026-08-06T00:00:00.000000Z",
            },
        )

    reader = Session(migrated_engine)
    try:
        # A normal read gives SQLAlchemy a logical transaction but SQLite has no snapshot yet.
        assert _generation_count(reader) == 1
        begin_sqlite_read_snapshot(reader)
        assert _generation_count(reader) == 1

        with migrated_engine.begin() as writer:
            writer.execute(
                text(
                    "INSERT INTO users (username, email, password_hash, created_at) "
                    "VALUES (:username, :email, :password_hash, :created_at)"
                ),
                {
                    "username": "snapshot-generation-b",
                    "email": "snapshot-generation-b@example.test",
                    "password_hash": "test-only-noncredential-marker",
                    "created_at": "2026-08-06T00:00:01.000000Z",
                },
            )

        assert _generation_count(reader) == 1
    finally:
        reader.close()

    with Session(migrated_engine) as fresh_reader:
        assert _generation_count(fresh_reader) == 2
