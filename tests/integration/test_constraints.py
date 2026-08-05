"""Real SQLite enforcement tests against databases built through Alembic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlmodel import Session, select

from app.auth.models import User

_TIMESTAMP = "2026-08-06T00:30:01.123456Z"


def _insert_user(
    connection: object, *, username: str = "alice", email: str = "alice@example.test"
) -> int:
    result = connection.execute(
        text(
            "INSERT INTO users (username, email, password_hash, created_at) "
            "VALUES (:username, :email, :password_hash, :created_at)"
        ),
        {
            "username": username,
            "email": email,
            "password_hash": "argon2id$valid-hash",
            "created_at": _TIMESTAMP,
        },
    )
    return int(result.lastrowid)


def _insert_bookmark(connection: object, user_id: int, *, title: str = "A bookmark") -> int:
    result = connection.execute(
        text(
            "INSERT INTO bookmarks (url, title, description, user_id, created_at, updated_at) "
            "VALUES (:url, :title, :description, :user_id, :created_at, :updated_at)"
        ),
        {
            "url": "https://example.test/bookmark",
            "title": title,
            "description": None,
            "user_id": user_id,
            "created_at": _TIMESTAMP,
            "updated_at": _TIMESTAMP,
        },
    )
    return int(result.lastrowid)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("username", ""),
        ("username", "  "),
        ("email", ""),
        ("email", "  "),
        ("password_hash", ""),
        ("password_hash", "  "),
    ],
)
def test_user_required_strings_fail_at_the_database_boundary(
    migrated_engine: Engine, column: str, value: str
) -> None:
    values = {
        "username": "alice",
        "email": "alice@example.test",
        "password_hash": "argon2id$valid-hash",
        "created_at": _TIMESTAMP,
    }
    values[column] = value

    with migrated_engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO users (username, email, password_hash, created_at) "
                "VALUES (:username, :email, :password_hash, :created_at)"
            ),
            values,
        )


@pytest.mark.parametrize(
    ("column", "value"), [("url", ""), ("url", "  "), ("title", ""), ("title", "  ")]
)
def test_bookmark_required_strings_fail_at_the_database_boundary(
    migrated_engine: Engine, column: str, value: str
) -> None:
    with migrated_engine.begin() as connection:
        user_id = _insert_user(connection)
        values = {
            "url": "https://example.test/bookmark",
            "title": "A bookmark",
            "description": None,
            "user_id": user_id,
            "created_at": _TIMESTAMP,
            "updated_at": _TIMESTAMP,
        }
        values[column] = value
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO bookmarks "
                    "(url, title, description, user_id, created_at, updated_at) "
                    "VALUES (:url, :title, :description, :user_id, :created_at, :updated_at)"
                ),
                values,
            )


@pytest.mark.parametrize("value", ["", "  "])
def test_tag_required_strings_fail_at_the_database_boundary(
    migrated_engine: Engine, value: str
) -> None:
    with migrated_engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text("INSERT INTO tags (name) VALUES (:name)"), {"name": value})


@pytest.mark.parametrize(
    ("statement", "parameters"),
    [
        (
            "INSERT INTO users (username, email, password_hash, created_at) "
            "VALUES (:username, 'overlong@example.test', 'hash', :timestamp)",
            {"username": "x" * 81, "timestamp": _TIMESTAMP},
        ),
        (
            "INSERT INTO bookmarks (url, title, description, user_id, created_at, updated_at) "
            "VALUES ('https://example.test', :title, NULL, 1, :timestamp, :timestamp)",
            {"title": "x" * 201, "timestamp": _TIMESTAMP},
        ),
        (
            "INSERT INTO bookmarks (url, title, description, user_id, created_at, updated_at) "
            "VALUES ('https://example.test', 'title', :description, 1, :timestamp, :timestamp)",
            {"description": "x" * 501, "timestamp": _TIMESTAMP},
        ),
        ("INSERT INTO tags (name) VALUES (:name)", {"name": "x" * 51}),
    ],
)
def test_assessed_string_limits_fail_at_the_database_boundary(
    migrated_engine: Engine, statement: str, parameters: dict[str, str]
) -> None:
    if "bookmarks" in statement:
        with migrated_engine.begin() as connection:
            _insert_user(connection)
    with migrated_engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text(statement), parameters)


def test_username_length_and_timestamp_order_checks_fail_at_the_database_boundary(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO users (username, email, password_hash, created_at) "
                "VALUES (:username, 'long@example.test', 'hash', :timestamp)"
            ),
            {"username": "x" * 81, "timestamp": _TIMESTAMP},
        )

    with migrated_engine.begin() as connection:
        user_id = _insert_user(connection)
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO bookmarks "
                    "(url, title, description, user_id, created_at, updated_at) "
                    "VALUES ('https://example.test', 'title', NULL, :user_id, "
                    ":created_at, :updated_at)"
                ),
                {
                    "user_id": user_id,
                    "created_at": "2026-08-06T00:30:01.123456Z",
                    "updated_at": "2026-08-06T00:30:00.123456Z",
                },
            )


def test_unique_composite_key_and_foreign_keys_fail_at_the_database_boundary(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.begin() as connection:
        user_id = _insert_user(connection)
        bookmark_id = _insert_bookmark(connection, user_id)
        tag_id = int(
            connection.execute(text("INSERT INTO tags (name) VALUES ('python')")).lastrowid
        )
        connection.execute(
            text("INSERT INTO bookmark_tags (bookmark_id, tag_id) VALUES (:bookmark_id, :tag_id)"),
            {"bookmark_id": bookmark_id, "tag_id": tag_id},
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO users (username, email, password_hash, created_at) VALUES "
                    "('alice', 'other@example.test', 'hash', :timestamp)"
                ),
                {"timestamp": _TIMESTAMP},
            )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO users (username, email, password_hash, created_at) VALUES "
                    "('other', 'alice@example.test', 'hash', :timestamp)"
                ),
                {"timestamp": _TIMESTAMP},
            )
        with pytest.raises(IntegrityError):
            connection.execute(text("INSERT INTO tags (name) VALUES ('python')"))
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO bookmark_tags (bookmark_id, tag_id) VALUES (:bookmark_id, :tag_id)"
                ),
                {"bookmark_id": bookmark_id, "tag_id": tag_id},
            )
        with pytest.raises(IntegrityError):
            _insert_bookmark(connection, 9_999)
        with pytest.raises(IntegrityError):
            connection.execute(
                text("INSERT INTO bookmark_tags (bookmark_id, tag_id) VALUES (9999, :tag_id)"),
                {"tag_id": tag_id},
            )
        with pytest.raises(IntegrityError):
            connection.execute(
                text("INSERT INTO bookmark_tags (bookmark_id, tag_id) VALUES (:bookmark_id, 9999)"),
                {"bookmark_id": bookmark_id},
            )


def test_user_and_bookmark_deletions_apply_the_expected_cascades(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        user_id = _insert_user(connection)
        bookmark_id = _insert_bookmark(connection, user_id)
        tag_id = int(
            connection.execute(text("INSERT INTO tags (name) VALUES ('python')")).lastrowid
        )
        connection.execute(
            text("INSERT INTO bookmark_tags (bookmark_id, tag_id) VALUES (:bookmark_id, :tag_id)"),
            {"bookmark_id": bookmark_id, "tag_id": tag_id},
        )
        connection.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
        assert connection.execute(text("SELECT count(*) FROM bookmarks")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM bookmark_tags")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM tags")).scalar_one() == 1

        second_user_id = _insert_user(connection, username="bob", email="bob@example.test")
        second_bookmark_id = _insert_bookmark(connection, second_user_id, title="Second bookmark")
        connection.execute(
            text("INSERT INTO bookmark_tags (bookmark_id, tag_id) VALUES (:bookmark_id, :tag_id)"),
            {"bookmark_id": second_bookmark_id, "tag_id": tag_id},
        )
        connection.execute(
            text("DELETE FROM bookmarks WHERE id = :bookmark_id"),
            {"bookmark_id": second_bookmark_id},
        )
        assert connection.execute(text("SELECT count(*) FROM bookmark_tags")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM tags")).scalar_one() == 1


def test_utc_round_trip_and_naive_datetime_rejection(migrated_engine: Engine) -> None:
    offset_created_at = datetime(
        2026, 8, 6, 10, 30, 1, 123_456, tzinfo=timezone(timedelta(hours=10))
    )
    session = Session(migrated_engine)
    try:
        session.add(
            User(
                username="utc-user",
                email="utc@example.test",
                password_hash="argon2id$valid-hash",
                created_at=offset_created_at,
            )
        )
        session.commit()
        stored = session.exec(select(User).where(User.username == "utc-user")).one()
        assert stored.created_at == datetime(2026, 8, 6, 0, 30, 1, 123_456, tzinfo=UTC)
        assert stored.created_at.tzinfo is UTC

        session.add(
            User(
                username="naive-user",
                email="naive@example.test",
                password_hash="argon2id$valid-hash",
                created_at=datetime(2026, 8, 6, 0, 30),
            )
        )
        with pytest.raises(StatementError, match="timezone-aware"):
            session.commit()
        session.rollback()
    finally:
        session.close()


def test_explicit_transaction_rollback_leaves_no_persisted_row(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        transaction = connection.begin()
        _insert_user(connection)
        transaction.rollback()
        assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 0
