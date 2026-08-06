"""Migrated-SQLite evidence for owner-scoped Track 04 ORM bookmark search."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Engine, event
from sqlmodel import Session

from app.auth.models import User
from app.bookmarks.models import Bookmark, BookmarkTag, Tag
from app.bookmarks.repository import BookmarkRepository, TagRepository
from app.bookmarks.schemas import BookmarkQuery
from app.bookmarks.service import BookmarkService

_NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


class _Clock:
    def now(self) -> datetime:
        return _NOW


class _Publisher:
    def __init__(self) -> None:
        self.calls = 0

    def publish(self) -> None:
        self.calls += 1


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

        assert filtered.total == 3
        assert [item.id for item in filtered.items] == [newest.id, tied.id]
        assert [tag.name for tag in filtered.items[0].tags] == ["python"]
        assert [item.id for item in literal.items] == [older.id]
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
