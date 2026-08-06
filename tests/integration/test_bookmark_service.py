"""Migrated-SQLite integration evidence for bookmark service transactions."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from typing import cast

import pytest
from sqlalchemy import Engine, event, select
from sqlmodel import Session

from app.auth.models import User
from app.bookmarks.events import DomainEventPublisher
from app.bookmarks.models import Bookmark, BookmarkTag, Tag
from app.bookmarks.repository import BookmarkRepository, TagRepository
from app.bookmarks.schemas import BookmarkCreate, BookmarkPatch
from app.bookmarks.service import BookmarkService
from app.core.clock import Clock
from app.core.errors import NotFoundError

_NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
_LATER = _NOW + timedelta(seconds=1)


class FixedClock:
    def __init__(self, *instants: datetime) -> None:
        self._instants = list(instants)
        self.calls = 0

    def now(self) -> datetime:
        self.calls += 1
        return self._instants.pop(0)


class RecordingPublisher:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls = 0

    def publish(self) -> None:
        self.calls += 1
        if self.failure is not None:
            raise self.failure


def _add_user(session: Session, username: str) -> User:
    user = User(
        username=username,
        email=f"{username}@example.test",
        password_hash="$argon2id$test-hash",
        created_at=_NOW,
    )
    session.add(user)
    session.flush()
    assert user.id is not None
    return user


def _service(
    session: Session,
    clock: FixedClock,
    publisher: RecordingPublisher | None = None,
    *,
    tags: TagRepository | None = None,
) -> BookmarkService:
    return BookmarkService(
        session=session,
        bookmarks=BookmarkRepository(session),
        tags=tags or TagRepository(session),
        clock=cast(Clock, clock),
        publisher=cast(DomainEventPublisher, publisher or RecordingPublisher()),
    )


def _create(**changes: object) -> BookmarkCreate:
    values: dict[str, object] = {
        "url": "https://example.test/bookmark",
        "title": "Bookmark",
        "description": "description",
        "tags": ["python"],
    }
    values.update(changes)
    return BookmarkCreate(**values)


def test_create_reuses_and_canonicalizes_tags_allows_duplicate_urls_and_returns_detached_dtos(
    migrated_engine: Engine,
) -> None:
    session = Session(migrated_engine)
    try:
        user = _add_user(session, "alice")
        assert user.id is not None
        publisher = RecordingPublisher()
        service = _service(session, FixedClock(_NOW, _LATER), publisher)

        first = service.create(
            user.id,
            _create(url="https://example.test/duplicate", tags=[" Python ", "async", "python"]),
        )
        second = service.create(
            user.id, _create(url="https://example.test/duplicate", tags=["python"])
        )
        session.close()

        assert str(first.url) == str(second.url) == "https://example.test/duplicate"
        assert [tag.name for tag in first.tags] == ["async", "python"]
        assert first.created_at == first.updated_at == _NOW
        assert second.created_at == second.updated_at == _LATER
        assert publisher.calls == 2
    finally:
        if session.is_active:
            session.close()

    with Session(migrated_engine) as verification:
        assert verification.execute(select(Tag.name).order_by(Tag.name)).scalars().all() == [
            "async",
            "python",
        ]
        assert len(verification.execute(select(Bookmark)).scalars().all()) == 2
        assert len(verification.execute(select(BookmarkTag)).scalars().all()) == 3


def test_patch_materiality_owner_concealment_rollback_and_orphan_tag_delete(
    migrated_engine: Engine,
) -> None:
    session = Session(migrated_engine)
    try:
        alice = _add_user(session, "alice")
        bob = _add_user(session, "bob")
        assert alice.id is not None
        assert bob.id is not None
        publisher = RecordingPublisher()
        service = _service(
            session, FixedClock(_NOW, _LATER, _LATER + timedelta(seconds=1)), publisher
        )
        created = service.create(alice.id, _create(tags=["python"]))

        no_op = service.patch(alice.id, created.id, BookmarkPatch(tags=["python"]))
        changed = service.patch(
            alice.id,
            created.id,
            BookmarkPatch(title="Changed", description=None, tags=["async"]),
        )
        with pytest.raises(NotFoundError) as other_user:
            service.patch(bob.id, created.id, BookmarkPatch(title="intrusion"))
        with pytest.raises(NotFoundError) as missing:
            service.get(alice.id, created.id + 100)

        assert (other_user.value.code, other_user.value.message) == (
            missing.value.code,
            missing.value.message,
        )
        assert no_op.updated_at == _NOW
        assert changed.created_at == _NOW
        assert changed.updated_at == _LATER
        assert changed.description is None
        assert [tag.name for tag in changed.tags] == ["async"]
        assert publisher.calls == 2

        service.delete(alice.id, created.id)
        assert publisher.calls == 3
        assert session.execute(select(BookmarkTag)).scalars().all() == []
        assert session.execute(select(Tag.name).order_by(Tag.name)).scalars().all() == [
            "async",
            "python",
        ]
    finally:
        session.close()


def test_link_failure_rolls_back_bookmark_new_tag_links_and_creation_timestamp(
    migrated_engine: Engine,
) -> None:
    session = Session(migrated_engine)
    try:
        user = _add_user(session, "alice")
        assert user.id is not None

        def fail_link_insert(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: object,
        ) -> None:
            if "insert into bookmark_tags" in statement.lower():
                raise RuntimeError("forced link failure")

        event.listen(migrated_engine, "before_cursor_execute", fail_link_insert)
        try:
            with pytest.raises(RuntimeError, match="forced link failure"):
                _service(session, FixedClock(_NOW)).create(user.id, _create(tags=["rollback-tag"]))
        finally:
            event.remove(migrated_engine, "before_cursor_execute", fail_link_insert)

        assert session.execute(select(Bookmark)).scalars().all() == []
        assert (
            session.execute(select(Tag).where(Tag.name == "rollback-tag")).scalar_one_or_none()
            is None
        )
        assert session.execute(select(BookmarkTag)).scalars().all() == []
    finally:
        session.close()


def test_baseline_list_keeps_repository_order_first_twenty_and_true_in_memory_total(
    migrated_engine: Engine,
) -> None:
    session = Session(migrated_engine)
    try:
        user = _add_user(session, "alice")
        assert user.id is not None
        service = _service(
            session,
            FixedClock(*[_NOW + timedelta(seconds=index) for index in range(24)]),
        )
        created = [
            service.create(user.id, _create(title=f"bookmark-{index}")) for index in range(24)
        ]

        listed = service.list(user.id)

        assert (listed.page, listed.page_size, listed.total) == (1, 20, 24)
        assert [item.id for item in listed.items] == [item.id for item in reversed(created[-20:])]
    finally:
        session.close()


def test_two_sessions_concurrently_create_the_same_canonical_tag_once(
    migrated_engine: Engine,
) -> None:
    setup = Session(migrated_engine)
    try:
        alice = _add_user(setup, "alice")
        bob = _add_user(setup, "bob")
        assert alice.id is not None
        assert bob.id is not None
        setup.commit()
        user_ids = (alice.id, bob.id)
    finally:
        setup.close()

    barrier = Barrier(2)

    def create_in_own_session(user_id: int) -> int:
        session = Session(migrated_engine)
        try:
            barrier.wait(timeout=5)
            response = _service(
                session,
                FixedClock(_NOW),
            ).create(user_id, _create(tags=["Shared "]))
            return response.id
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(create_in_own_session, user_id) for user_id in user_ids]
        bookmark_ids = [future.result(timeout=15) for future in futures]

    with Session(migrated_engine) as verification:
        assert len(set(bookmark_ids)) == 2
        assert verification.execute(select(Tag).where(Tag.name == "shared")).scalars().all()
        assert (
            len(verification.execute(select(Tag).where(Tag.name == "shared")).scalars().all()) == 1
        )
        assert len(verification.execute(select(BookmarkTag)).scalars().all()) == 2
