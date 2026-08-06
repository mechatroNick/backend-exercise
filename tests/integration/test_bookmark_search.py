"""Migrated-SQLite evidence for owner-scoped Track 04 ORM bookmark search."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from threading import Event, Thread
from uuid import UUID

import pytest
from sqlalchemy import Engine, event, select
from sqlalchemy.engine import Connection
from sqlmodel import Session

from app.auth.models import User
from app.bookmarks.events import BookmarkStatsInvalidated, PublishOutcome
from app.bookmarks.models import Bookmark, BookmarkTag, Tag
from app.bookmarks.repository import BookmarkRepository, TagRepository
from app.bookmarks.schemas import BookmarkList, BookmarkQuery
from app.bookmarks.service import BookmarkService
from app.bookmarks.stats.dirty import BookmarkStatsDirtyRepository

pytestmark = pytest.mark.mandatory

_NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
_CORRELATION_ID = UUID("12345678-1234-5678-9234-567812345678")


class _Clock:
    def now(self) -> datetime:
        return _NOW


class _Publisher:
    def __init__(self) -> None:
        self.calls = 0

    def publish(self, event: BookmarkStatsInvalidated) -> PublishOutcome:
        del event
        self.calls += 1
        return PublishOutcome.ENQUEUED


def _user(session: Session, name: str) -> User:
    value = User(
        username=name,
        email=f"{name}@example.test",
        password_hash="test-hash",
        created_at=_NOW,
    )
    session.add(value)
    session.flush()
    assert value.id is not None
    return value


def _bookmark(session: Session, user_id: int, title: str, created_at: datetime) -> Bookmark:
    value = Bookmark(
        url=f"https://example.test/{title}",
        title=title,
        description=None,
        user_id=user_id,
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(value)
    session.flush()
    assert value.id is not None
    return value


def _tag(session: Session, name: str) -> Tag:
    value = Tag(name=name)
    session.add(value)
    session.flush()
    assert value.id is not None
    return value


def _service(session: Session, publisher: _Publisher) -> BookmarkService:
    return BookmarkService(
        session=session,
        bookmarks=BookmarkRepository(session),
        tags=TagRepository(session),
        clock=_Clock(),  # type: ignore[arg-type]
        publisher=publisher,  # type: ignore[arg-type]
        dirty=BookmarkStatsDirtyRepository(session),
        correlation_id_factory=lambda: _CORRELATION_ID,
    )


def test_search_filters_literals_dates_tags_pagination_and_owner_scope(
    migrated_engine: Engine,
) -> None:
    session = Session(migrated_engine)
    try:
        alice = _user(session, "alice")
        bob = _user(session, "bob")
        assert alice.id is not None
        assert bob.id is not None
        older = _bookmark(session, alice.id, "Alpha %_\\", _NOW - timedelta(days=1))
        tied = _bookmark(session, alice.id, "Alpha later", _NOW)
        newest = _bookmark(session, alice.id, "ALPHA newest", _NOW)
        _bookmark(session, bob.id, "ALPHA bob", _NOW + timedelta(days=1))
        python = _tag(session, "python")
        api = _tag(session, "api")
        assert older.id is not None
        assert tied.id is not None
        assert newest.id is not None
        assert python.id is not None
        assert api.id is not None
        session.add_all(
            [
                BookmarkTag(bookmark_id=older.id, tag_id=python.id),
                BookmarkTag(bookmark_id=older.id, tag_id=api.id),
                BookmarkTag(bookmark_id=tied.id, tag_id=python.id),
                BookmarkTag(bookmark_id=newest.id, tag_id=python.id),
            ]
        )
        session.commit()

        publisher = _Publisher()
        service = _service(session, publisher)
        filtered = service.list(
            alice.id,
            BookmarkQuery(
                tag=" PYTHON ",
                q="ALPHA",
                created_from=date(2026, 8, 5),
                created_to=date(2026, 8, 6),
                page=1,
                page_size=2,
            ),
        )
        literal = service.list(alice.id, BookmarkQuery(q="%_\\"))
        out_of_range = service.list(alice.id, BookmarkQuery(page=3, page_size=2))
        date_max = service.list(alice.id, BookmarkQuery(created_to=date.max))
        created_equal_day = service.list(
            alice.id,
            BookmarkQuery(created_from=date(2026, 8, 6), created_to=date(2026, 8, 6)),
        )
        created_upper_exclusive = service.list(alice.id, BookmarkQuery(created_to=date(2026, 8, 5)))
        updated_equal_day = service.list(
            alice.id,
            BookmarkQuery(updated_from=date(2026, 8, 6), updated_to=date(2026, 8, 6)),
        )
        second_page = service.list(alice.id, BookmarkQuery(page=2, page_size=2))

        assert filtered.total == 3
        assert [item.id for item in filtered.items] == [newest.id, tied.id]
        assert [tag.name for tag in filtered.items[0].tags] == ["python"]
        assert [item.id for item in literal.items] == [older.id]
        assert [item.id for item in created_equal_day.items] == [newest.id, tied.id]
        assert [item.id for item in created_upper_exclusive.items] == [older.id]
        assert [item.id for item in updated_equal_day.items] == [newest.id, tied.id]
        assert [item.id for item in second_page.items] == [older.id]
        assert not {item.id for item in filtered.items} & {item.id for item in second_page.items}
        assert out_of_range.items == ()
        assert out_of_range.total == 3
        assert date_max.total == 3
        assert publisher.calls == 0
    finally:
        session.close()


def test_populated_search_executes_begin_count_page_and_bulk_tag_load_only(
    migrated_engine: Engine,
) -> None:
    statements: list[str] = []

    def record(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        statements.append(statement.lower())

    event.listen(migrated_engine, "before_cursor_execute", record)
    session = Session(migrated_engine)
    try:
        user = _user(session, "alice")
        assert user.id is not None
        bookmark = _bookmark(session, user.id, "bookmark", _NOW)
        tag = _tag(session, "python")
        assert bookmark.id is not None
        assert tag.id is not None
        session.add(BookmarkTag(bookmark_id=bookmark.id, tag_id=tag.id))
        session.commit()
        user_id = user.id
        statements.clear()

        result = _service(session, _Publisher()).list(user_id, BookmarkQuery(page_size=100))

        assert result.total == 1
        assert len(statements) == 4
        assert statements[0] == "begin deferred"
        assert "count" in statements[1]
        assert "from bookmarks" in statements[2]
        assert "from bookmark_tags join tags" in statements[3]
    finally:
        session.close()
        event.remove(migrated_engine, "before_cursor_execute", record)


def test_enormous_page_short_circuits_after_count_without_offset_query(
    migrated_engine: Engine,
) -> None:
    statements: list[str] = []

    def record(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        statements.append(statement.lower())

    event.listen(migrated_engine, "before_cursor_execute", record)
    session = Session(migrated_engine)
    try:
        user = _user(session, "alice")
        assert user.id is not None
        _bookmark(session, user.id, "only", _NOW)
        session.commit()
        user_id = user.id
        statements.clear()

        result = _service(session, _Publisher()).list(user_id, BookmarkQuery(page=1_000_000))

        assert result.items == ()
        assert result.total == 1
        assert len(statements) == 2
        assert statements[0] == "begin deferred"
        assert "count" in statements[1]
        assert "offset" not in "\n".join(statements)
    finally:
        session.close()
        event.remove(migrated_engine, "before_cursor_execute", record)


def test_service_list_keeps_generation_a_across_wal_writer_interleaving(
    migrated_engine: Engine,
) -> None:
    """A writer commits exactly between count and page; the reader keeps one generation."""
    with migrated_engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode = WAL").scalar_one() == "wal"
        connection.commit()

    setup = Session(migrated_engine)
    try:
        user = _user(setup, "alice")
        assert user.id is not None
        generation_a = _bookmark(setup, user.id, "generation-a", _NOW)
        alpha = _tag(setup, "alpha")
        assert generation_a.id is not None
        assert alpha.id is not None
        setup.add(BookmarkTag(bookmark_id=generation_a.id, tag_id=alpha.id))
        setup.commit()
        user_id = user.id
    finally:
        setup.close()

    writer_turn = Event()
    writer_done = Event()
    reader_errors: list[BaseException] = []
    reader_results: list[BookmarkList] = []
    reader_events: list[str] = []

    reader = Session(migrated_engine)
    reader_connection = reader.connection()
    driver_connection = reader_connection.connection.driver_connection
    assert isinstance(driver_connection, sqlite3.Connection)
    try:
        # This auth-equivalent ORM SELECT creates SQLAlchemy state without a driver transaction.
        assert reader.execute(select(User.id).where(User.id == user_id)).scalar_one() == user_id
        assert reader.in_transaction()
        assert driver_connection.in_transaction is False

        def pause_before_page(
            _connection: Connection,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: object,
        ) -> None:
            normalized = statement.lower()
            if "from bookmarks" in normalized and "count(" not in normalized:
                writer_turn.set()
                assert writer_done.wait(timeout=5)

        def record_reader_completion(connection: Connection) -> None:
            if connection is reader_connection:
                reader_events.append("commit-or-rollback")

        event.listen(migrated_engine, "before_cursor_execute", pause_before_page)
        event.listen(migrated_engine, "commit", record_reader_completion)
        event.listen(migrated_engine, "rollback", record_reader_completion)
        try:

            def read_generation_a() -> None:
                try:
                    reader_results.append(_service(reader, _Publisher()).list(user_id))
                except BaseException as error:  # pragma: no cover - surfaced below.
                    reader_errors.append(error)

            reader_thread = Thread(target=read_generation_a)
            reader_thread.start()
            assert writer_turn.wait(timeout=5)

            writer = Session(migrated_engine)
            try:
                generation_b = _bookmark(writer, user_id, "generation-b", _NOW + timedelta(days=1))
                beta = _tag(writer, "beta")
                assert generation_b.id is not None
                assert beta.id is not None
                writer.add(BookmarkTag(bookmark_id=generation_b.id, tag_id=beta.id))
                writer.commit()
            finally:
                writer.close()
            writer_done.set()
            reader_thread.join(timeout=5)
            assert not reader_thread.is_alive()
        finally:
            event.remove(migrated_engine, "before_cursor_execute", pause_before_page)
            event.remove(migrated_engine, "commit", record_reader_completion)
            event.remove(migrated_engine, "rollback", record_reader_completion)

        assert reader_errors == []
        response = reader_results[0]
        assert response.total == 1
        assert [item.title for item in response.items] == ["generation-a"]
        assert [tag.name for tag in response.items[0].tags] == ["alpha"]
        assert driver_connection.in_transaction is True
        assert reader_events == []
    finally:
        reader.close()

    fresh = Session(migrated_engine)
    try:
        response = _service(fresh, _Publisher()).list(user_id)
        assert response.total == 2
        assert {item.title for item in response.items} == {"generation-a", "generation-b"}
    finally:
        fresh.close()
