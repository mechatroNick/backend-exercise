"""Migrated-SQLite integration evidence for bookmark service transactions."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy import Connection, Engine, event, select
from sqlalchemy.engine import ExceptionContext
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.auth.models import User
from app.bookmarks.events import (
    BookmarkMutationKind,
    BookmarkStatsInvalidated,
    DomainEventPublisher,
    PublishOutcome,
)
from app.bookmarks.models import Bookmark, BookmarkTag, Tag
from app.bookmarks.repository import BookmarkRepository, TagRepository
from app.bookmarks.schemas import BookmarkCreate, BookmarkPatch
from app.bookmarks.service import BookmarkService, DirtyMarkerWriter
from app.bookmarks.stats.dirty import BookmarkStatsDirtyRepository, DirtyReason
from app.core.clock import Clock
from app.core.errors import NotFoundError

_NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
_LATER = _NOW + timedelta(seconds=1)
_CORRELATION_ID = UUID("12345678-1234-5678-9234-567812345678")


class FixedClock:
    def __init__(self, *instants: datetime) -> None:
        self._instants = list(instants)
        self.calls = 0

    def now(self) -> datetime:
        self.calls += 1
        return self._instants.pop(0)


class RecordingPublisher:
    def __init__(self) -> None:
        self.calls = 0
        self.events: list[BookmarkStatsInvalidated] = []

    def publish(self, event: BookmarkStatsInvalidated) -> PublishOutcome:
        self.calls += 1
        self.events.append(event)
        return PublishOutcome.ENQUEUED


class CommitObservingPublisher:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self.events: list[BookmarkStatsInvalidated] = []
        self.visible_bookmark_counts: list[int] = []
        self.visible_generations: list[int] = []

    def publish(self, event_value: BookmarkStatsInvalidated) -> PublishOutcome:
        with Session(self._engine) as verification:
            self.visible_bookmark_counts.append(
                len(verification.execute(select(Bookmark)).scalars().all())
            )
            marker = BookmarkStatsDirtyRepository(verification).observe()[0]
            self.visible_generations.append(marker.generation)
        self.events.append(event_value)
        return PublishOutcome.ENQUEUED


class MarkThenFailDirty:
    def __init__(self, session: Session) -> None:
        self._repository = BookmarkStatsDirtyRepository(session)

    def mark_dirty(
        self,
        user_id: int,
        window_start: datetime,
        reason: DirtyReason,
        marked_at: datetime,
    ) -> None:
        self._repository.mark_dirty(user_id, window_start, reason, marked_at)
        raise RuntimeError("failure after dirty upsert")


class _WinnerInsertedAfterMissTagRepository(TagRepository):
    """Create a canonical winner after one observed tag miss.

    SQLite permits only one writer while the service's outer transaction already owns
    the bookmark write lock.  This seam therefore uses that same real connection to
    reproduce the only relevant ordering: the lookup observes no tag, a competing
    canonical row appears before the savepoint's candidate insert, and the candidate
    then receives SQLite's native unique-constraint error.
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.lookup_results: list[Tag | None] = []
        self.injected_winner = False

    def find_by_name(self, name: str) -> Tag | None:
        tag = super().find_by_name(name)
        if tag is None and not self.injected_winner:
            self.lookup_results.append(None)
            self._session.connection().exec_driver_sql(
                "INSERT INTO tags (name) VALUES (?)",
                (name,),
            )
            self.injected_winner = True
            return None
        self.lookup_results.append(tag)
        return tag


class _NonblankConstraintTagRepository(TagRepository):
    """Force a different real SQLite integrity error at the candidate insert seam."""

    def add(self, tag: Tag) -> None:
        tag.name = " "
        super().add(tag)


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
    publisher: DomainEventPublisher | None = None,
    *,
    tags: TagRepository | None = None,
    dirty: DirtyMarkerWriter | None = None,
) -> BookmarkService:
    return BookmarkService(
        session=session,
        bookmarks=BookmarkRepository(session),
        tags=tags or TagRepository(session),
        clock=cast(Clock, clock),
        publisher=publisher or RecordingPublisher(),
        dirty=dirty or BookmarkStatsDirtyRepository(session),
        correlation_id_factory=lambda: _CORRELATION_ID,
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


def test_create_commits_canonical_state_and_marker_before_typed_publish(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        user = _add_user(session, "alice")
        assert user.id is not None
        session.commit()
        publisher = CommitObservingPublisher(migrated_engine)

        response = _service(session, FixedClock(_NOW), publisher).create(user.id, _create())

        assert publisher.visible_bookmark_counts == [1]
        assert publisher.visible_generations == [1]
        assert publisher.events == [
            BookmarkStatsInvalidated(
                user_id=user.id,
                window_start=datetime(2026, 8, 3, tzinfo=UTC),
                mutation_kind=BookmarkMutationKind.CREATED,
                bookmark_id=response.id,
                occurred_at=_NOW,
                correlation_id=_CORRELATION_ID,
            )
        ]


def test_failure_after_real_dirty_upsert_rolls_back_bookmark_marker_and_publication(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        user = _add_user(session, "alice")
        assert user.id is not None
        session.commit()
        publisher = RecordingPublisher()

        with pytest.raises(RuntimeError, match="failure after dirty upsert"):
            _service(
                session,
                FixedClock(_NOW),
                publisher,
                dirty=MarkThenFailDirty(session),
            ).create(user.id, _create())

        assert publisher.calls == 0

    with Session(migrated_engine) as verification:
        assert verification.execute(select(Bookmark)).scalars().all() == []
        assert BookmarkStatsDirtyRepository(verification).backlog().count == 0


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
        assert [event.mutation_kind for event in publisher.events] == [
            BookmarkMutationKind.CREATED,
            BookmarkMutationKind.CREATED,
        ]
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
        marker = BookmarkStatsDirtyRepository(verification).observe()[0]
        assert (marker.generation, marker.reason) == (2, DirtyReason.CREATE)


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
        assert [event.mutation_kind for event in publisher.events] == [
            BookmarkMutationKind.CREATED,
            BookmarkMutationKind.UPDATED,
            BookmarkMutationKind.DELETED,
        ]
        assert session.execute(select(BookmarkTag)).scalars().all() == []
        assert session.execute(select(Tag.name).order_by(Tag.name)).scalars().all() == [
            "async",
            "python",
        ]
        marker = BookmarkStatsDirtyRepository(session).observe()[0]
        assert marker.window_start == datetime(2026, 8, 3, tzinfo=UTC)
        assert (marker.generation, marker.reason) == (3, DirtyReason.DELETE)
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


def test_tag_unique_race_recovers_the_real_sqlite_savepoint_conflict_without_outer_rollback(
    migrated_engine: Engine,
) -> None:
    setup = Session(migrated_engine)
    try:
        user = _add_user(setup, "alice")
        assert user.id is not None
        setup.commit()
        user_id = user.id
    finally:
        setup.close()

    session = Session(migrated_engine)
    tags = _WinnerInsertedAfterMissTagRepository(session)
    sqlite_errors: list[sqlite3.IntegrityError] = []
    statements: list[str] = []
    commits: list[Connection] = []
    outer_rollbacks: list[Connection] = []

    def record_statement(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        statements.append(statement.lower())

    def record_sqlite_error(exception_context: ExceptionContext) -> None:
        original = exception_context.original_exception
        if isinstance(original, sqlite3.IntegrityError):
            sqlite_errors.append(original)

    def record_commit(connection: Connection) -> None:
        commits.append(connection)

    def record_outer_rollback(connection: Connection) -> None:
        outer_rollbacks.append(connection)

    event.listen(migrated_engine, "before_cursor_execute", record_statement)
    event.listen(migrated_engine, "handle_error", record_sqlite_error)
    event.listen(migrated_engine, "commit", record_commit)
    event.listen(migrated_engine, "rollback", record_outer_rollback)
    try:
        publisher = RecordingPublisher()
        response = _service(session, FixedClock(_NOW), publisher, tags=tags).create(
            user_id,
            _create(tags=["Race Tag"]),
        )

        assert tags.injected_winner
        assert tags.lookup_results[0] is None
        assert tags.lookup_results[1] is not None
        assert tags.lookup_results[1].name == "race tag"
        assert sqlite_errors
        assert sqlite_errors[0].sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_UNIQUE
        assert str(sqlite_errors[0]) == "UNIQUE constraint failed: tags.name"
        assert len(commits) == 1
        assert outer_rollbacks == []
        assert publisher.calls == 1
        assert [tag.name for tag in response.tags] == ["race tag"]

        tag_insert_indices = [
            index for index, statement in enumerate(statements) if "insert into tags" in statement
        ]
        savepoint_index = next(
            index for index, statement in enumerate(statements) if statement.startswith("savepoint")
        )
        rollback_to_savepoint_index = next(
            index
            for index, statement in enumerate(statements)
            if statement.startswith("rollback to savepoint")
        )
        assert len(tag_insert_indices) == 2
        assert tag_insert_indices[0] < savepoint_index < tag_insert_indices[1]
        assert tag_insert_indices[1] < rollback_to_savepoint_index
    finally:
        event.remove(migrated_engine, "before_cursor_execute", record_statement)
        event.remove(migrated_engine, "handle_error", record_sqlite_error)
        event.remove(migrated_engine, "commit", record_commit)
        event.remove(migrated_engine, "rollback", record_outer_rollback)
        session.close()

    with Session(migrated_engine) as verification:
        canonical_tags = (
            verification.execute(select(Tag).where(Tag.name == "race tag")).scalars().all()
        )
        links = verification.execute(select(BookmarkTag)).scalars().all()
        bookmarks = verification.execute(select(Bookmark)).scalars().all()
        assert len(canonical_tags) == len(bookmarks) == len(links) == 1
        assert links[0].tag_id == canonical_tags[0].id
        assert links[0].bookmark_id == bookmarks[0].id


def test_unrelated_real_tag_integrity_error_is_not_masked_by_unique_race_recovery(
    migrated_engine: Engine,
) -> None:
    session = Session(migrated_engine)
    try:
        user = _add_user(session, "alice")
        assert user.id is not None
        with pytest.raises(IntegrityError) as raised:
            _service(
                session,
                FixedClock(_NOW),
                tags=_NonblankConstraintTagRepository(session),
            ).create(user.id, _create(tags=["not-a-race"]))

        assert isinstance(raised.value.orig, sqlite3.IntegrityError)
        assert str(raised.value.orig) == "CHECK constraint failed: ck_tags_name_nonblank"
        assert session.execute(select(Bookmark)).scalars().all() == []
        assert session.execute(select(Tag)).scalars().all() == []
        assert session.execute(select(BookmarkTag)).scalars().all() == []
    finally:
        session.close()


def test_two_sessions_concurrently_complete_with_one_canonical_tag_final_state(
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
