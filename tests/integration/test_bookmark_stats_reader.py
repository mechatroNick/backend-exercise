"""Database-level correctness and snapshot evidence for current bookmark statistics."""

from __future__ import annotations

from threading import Event, Thread
from typing import Any

from sqlalchemy import Engine, TextClause, event, text
from sqlmodel import Session

from app.bookmarks.stats.raw_sql import MONTHS_SQL, TOP_TAGS_SQL, TOTALS_SQL, BookmarkStatsReader
from app.bookmarks.stats.schemas import BookmarksPerMonth, BookmarkStats, TopTag

_OWNER_ID = 1
_OTHER_USER_ID = 2
_PASSWORD_MARKER = "test-only-noncredential-marker"


def _insert_user(connection: Any, user_id: int, name: str) -> None:
    connection.execute(
        text(
            "INSERT INTO users (id, username, email, password_hash, created_at) "
            "VALUES (:id, :username, :email, :password_hash, :created_at)"
        ),
        {
            "id": user_id,
            "username": name,
            "email": f"{name}@example.test",
            "password_hash": _PASSWORD_MARKER,
            "created_at": "2026-08-06T00:00:00.000000Z",
        },
    )


def _insert_bookmark(connection: Any, bookmark_id: int, user_id: int, created_at: str) -> None:
    connection.execute(
        text(
            "INSERT INTO bookmarks (id, url, title, description, user_id, created_at, updated_at) "
            "VALUES (:id, :url, :title, NULL, :user_id, :created_at, :updated_at)"
        ),
        {
            "id": bookmark_id,
            "url": f"https://example.test/{bookmark_id}",
            "title": f"bookmark-{bookmark_id}",
            "user_id": user_id,
            "created_at": created_at,
            "updated_at": created_at,
        },
    )


def _insert_tag(connection: Any, tag_id: int, name: str) -> None:
    connection.execute(
        text("INSERT INTO tags (id, name) VALUES (:id, :name)"), {"id": tag_id, "name": name}
    )


def _link(connection: Any, bookmark_id: int, tag_id: int) -> None:
    connection.execute(
        text("INSERT INTO bookmark_tags (bookmark_id, tag_id) VALUES (:bookmark_id, :tag_id)"),
        {"bookmark_id": bookmark_id, "tag_id": tag_id},
    )


def _seed_populated_stats_fixture(engine: Engine) -> None:
    with engine.begin() as connection:
        _insert_user(connection, _OWNER_ID, "stats-owner")
        _insert_user(connection, _OTHER_USER_ID, "stats-other")
        _insert_bookmark(connection, 11, _OWNER_ID, "2025-01-10T00:00:00.000000Z")
        _insert_bookmark(connection, 12, _OWNER_ID, "2026-01-10T00:00:00.000000Z")
        _insert_bookmark(connection, 13, _OWNER_ID, "2026-02-10T00:00:00.000000Z")
        _insert_bookmark(connection, 21, _OTHER_USER_ID, "2026-03-10T00:00:00.000000Z")
        _insert_tag(connection, 31, "alpha")
        _insert_tag(connection, 32, "beta")
        _insert_tag(connection, 33, "shared")
        _link(connection, 11, 31)
        _link(connection, 11, 33)
        _link(connection, 12, 32)
        _link(connection, 12, 33)
        _link(connection, 13, 32)
        _link(connection, 21, 33)


def _read(engine: Engine, user_id: int, top_tags_limit: int = 5) -> BookmarkStats:
    with Session(engine) as session:
        return BookmarkStatsReader(session, top_tags_limit).read(user_id)


def _compiled_statement(statement: TextClause, engine: Engine) -> str:
    return str(statement.compile(dialect=engine.dialect)).strip()


def test_reader_returns_empty_owner_scoped_immutable_statistics(migrated_engine: Engine) -> None:
    statements: list[str] = []

    def record_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement.strip())

    event.listen(migrated_engine, "before_cursor_execute", record_statement)
    try:
        stats = _read(migrated_engine, _OWNER_ID)
    finally:
        event.remove(migrated_engine, "before_cursor_execute", record_statement)

    assert stats == BookmarkStats(
        total_bookmarks=0,
        total_tags=0,
        top_tags=(),
        bookmarks_per_month=(),
    )
    assert statements == [
        "BEGIN DEFERRED",
        _compiled_statement(TOTALS_SQL, migrated_engine),
        _compiled_statement(TOP_TAGS_SQL, migrated_engine),
        _compiled_statement(MONTHS_SQL, migrated_engine),
    ]


def test_reader_counts_distinct_attached_tags_owner_scope_ties_and_months(
    migrated_engine: Engine,
) -> None:
    _seed_populated_stats_fixture(migrated_engine)

    stats = _read(migrated_engine, _OWNER_ID, top_tags_limit=2)

    assert stats.model_dump(mode="json") == {
        "total_bookmarks": 3,
        "total_tags": 3,
        "top_tags": [{"name": "beta", "count": 2}, {"name": "shared", "count": 2}],
        "bookmarks_per_month": [
            {"month": "2025-01", "count": 1},
            {"month": "2026-01", "count": 1},
            {"month": "2026-02", "count": 1},
        ],
    }
    assert _read(migrated_engine, _OTHER_USER_ID).model_dump(mode="json") == {
        "total_bookmarks": 1,
        "total_tags": 1,
        "top_tags": [{"name": "shared", "count": 1}],
        "bookmarks_per_month": [{"month": "2026-03", "count": 1}],
    }


def test_reader_reflects_link_and_bookmark_deletion_on_a_fresh_live_read(
    migrated_engine: Engine,
) -> None:
    _seed_populated_stats_fixture(migrated_engine)

    with migrated_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM bookmark_tags WHERE bookmark_id = :bookmark_id AND tag_id = :tag_id"),
            {"bookmark_id": 11, "tag_id": 31},
        )
    after_link_removal = _read(migrated_engine, _OWNER_ID)
    assert after_link_removal.total_tags == 2
    assert {tag.name for tag in after_link_removal.top_tags} == {"beta", "shared"}

    with migrated_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM bookmarks WHERE id = :bookmark_id"), {"bookmark_id": 12}
        )
    after_bookmark_removal = _read(migrated_engine, _OWNER_ID)
    assert after_bookmark_removal.model_dump(mode="json") == {
        "total_bookmarks": 2,
        "total_tags": 2,
        "top_tags": [{"name": "beta", "count": 1}, {"name": "shared", "count": 1}],
        "bookmarks_per_month": [
            {"month": "2025-01", "count": 1},
            {"month": "2026-02", "count": 1},
        ],
    }


def test_reader_uses_one_snapshot_three_bound_selects_and_no_completion(
    migrated_engine: Engine,
) -> None:
    _seed_populated_stats_fixture(migrated_engine)
    statements: list[str] = []
    transaction_events: list[str] = []

    def record_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement.strip())

    event.listen(migrated_engine, "before_cursor_execute", record_statement)
    event.listen(migrated_engine, "commit", lambda _connection: transaction_events.append("commit"))
    event.listen(
        migrated_engine, "rollback", lambda _connection: transaction_events.append("rollback")
    )
    session = Session(migrated_engine)
    try:
        assert BookmarkStatsReader(session, 5).read(_OWNER_ID).total_bookmarks == 3
        assert statements == [
            "BEGIN DEFERRED",
            _compiled_statement(TOTALS_SQL, migrated_engine),
            _compiled_statement(TOP_TAGS_SQL, migrated_engine),
            _compiled_statement(MONTHS_SQL, migrated_engine),
        ]
        assert transaction_events == []
    finally:
        event.remove(migrated_engine, "before_cursor_execute", record_statement)
        session.close()
        if session.is_active:
            session.close()

    assert transaction_events == ["rollback"]


def test_reader_keeps_whole_response_on_generation_a_during_a_wal_writer_commit(
    migrated_engine: Engine,
) -> None:
    """WAL is deterministic test scheduling only; application policy remains unchanged."""
    with migrated_engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode = WAL").scalar_one() == "wal"
        connection.commit()
    with migrated_engine.begin() as connection:
        _insert_user(connection, _OWNER_ID, "snapshot-owner")
        _insert_bookmark(connection, 11, _OWNER_ID, "2026-01-10T00:00:00.000000Z")
        _insert_tag(connection, 31, "alpha")
        _link(connection, 11, 31)

    writer_turn = Event()
    writer_done = Event()
    reader_errors: list[BaseException] = []
    reader_stats: list[BookmarkStats] = []

    def pause_before_top_tags(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if statement.strip() == _compiled_statement(TOP_TAGS_SQL, migrated_engine):
            writer_turn.set()
            assert writer_done.wait(timeout=5)

    event.listen(migrated_engine, "before_cursor_execute", pause_before_top_tags)

    def read_generation_a() -> None:
        try:
            reader_stats.append(_read(migrated_engine, _OWNER_ID))
        except BaseException as error:  # pragma: no cover - surfaced by the main thread assertion.
            reader_errors.append(error)

    reader_thread = Thread(target=read_generation_a)
    reader_thread.start()
    try:
        assert writer_turn.wait(timeout=5)
        with migrated_engine.begin() as connection:
            _insert_bookmark(connection, 12, _OWNER_ID, "2026-02-10T00:00:00.000000Z")
            _insert_tag(connection, 32, "beta")
            _link(connection, 12, 32)
        writer_done.set()
        reader_thread.join(timeout=5)
        assert reader_thread.is_alive() is False
    finally:
        writer_done.set()
        reader_thread.join(timeout=5)
        event.remove(migrated_engine, "before_cursor_execute", pause_before_top_tags)

    assert reader_errors == []
    assert reader_stats == [
        BookmarkStats(
            total_bookmarks=1,
            total_tags=1,
            top_tags=(TopTag(name="alpha", count=1),),
            bookmarks_per_month=(BookmarksPerMonth(month="2026-01", count=1),),
        )
    ]
    assert _read(migrated_engine, _OWNER_ID).model_dump(mode="json") == {
        "total_bookmarks": 2,
        "total_tags": 2,
        "top_tags": [{"name": "alpha", "count": 1}, {"name": "beta", "count": 1}],
        "bookmarks_per_month": [{"month": "2026-01", "count": 1}, {"month": "2026-02", "count": 1}],
    }
