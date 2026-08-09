"""Migrated-SQLite recovery and race evidence for the statistics refresher."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from app.bookmarks.events import (
    BookmarkMutationKind,
    BookmarkStatsInvalidated,
)
from app.bookmarks.stats.dirty import BookmarkStatsDirtyRepository, DirtyReason
from app.bookmarks.stats.publisher import StatsInvalidationPublisher
from app.bookmarks.stats.raw_sql import TOTALS_SQL, BookmarkStatsReader
from app.bookmarks.stats.refresher import (
    ProjectionLifecycleStatus,
    StatsRefresher,
    _ProjectionCycleResult,
)
from app.bookmarks.stats.snapshots import StatsSnapshotStore
from app.core.config import Settings
from app.db.engine import create_session_factory
from app.main import create_app

_NOW = datetime(2026, 8, 6, 12, tzinfo=UTC)
_INSTANCE_ID = UUID("12345678-1234-5678-9234-567812345678")
_CORRELATION_ID = UUID("87654321-4321-6789-a234-567812345678")


class _Clock:
    def __init__(self) -> None:
        self.value = _NOW

    def now(self) -> datetime:
        self.value += timedelta(microseconds=1)
        return self.value


def _logger() -> logging.Logger:
    logger = logging.getLogger(f"test.stats.refresher.integration.{id(object())}")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def _runtime(
    engine: Engine,
    *,
    batch_size: int = 100,
    projection_enabled: bool = False,
) -> tuple[StatsRefresher, StatsInvalidationPublisher, StatsSnapshotStore]:
    store = StatsSnapshotStore()
    publisher = StatsInvalidationPublisher(
        store=store,
        capacity=100,
        logger=_logger(),
        service_instance_id=_INSTANCE_ID,
    )
    refresher = StatsRefresher(
        session_factory=create_session_factory(engine),
        publisher=publisher,
        store=store,
        clock=_Clock(),
        top_tags_limit=5,
        interval_seconds=1,
        full_reconciliation_seconds=1,
        batch_size=batch_size,
        logger=_logger(),
        service_instance_id=_INSTANCE_ID,
        projection_enabled=projection_enabled,
    )
    return refresher, publisher, store


def test_projection_failure_degrades_only_projection_not_current_refresh(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    refresher, _publisher, _store = _runtime(migrated_engine)
    monkeypatch.setattr(
        refresher,
        "_run_projection_phase",
        lambda: _ProjectionCycleResult(
            status=ProjectionLifecycleStatus.FAILED,
            successful=False,
            error_code="projection_cycle_failed",
        ),
    )

    assert refresher.run_cycle(full=True)
    state = refresher.state()
    assert state.successful_cycles == 1
    assert state.consecutive_failures == 0
    assert state.projection_consecutive_failures == 1


def test_default_enabled_projection_baselines_then_completes_dirty_generation(
    migrated_engine: Engine,
) -> None:
    refresher, _publisher, _store = _runtime(migrated_engine, projection_enabled=True)

    assert refresher.run_cycle(full=True)
    assert refresher.state().projection_baseline_status is ProjectionLifecycleStatus.ACTIVE

    _seed_users(migrated_engine, count=1)
    _seed_bookmark(migrated_engine)
    with Session(migrated_engine) as session:
        BookmarkStatsDirtyRepository(session).mark_dirty(1, _NOW, DirtyReason.CREATE, _NOW)
        session.commit()

    assert refresher.run_cycle()
    assert refresher.state().projection_successful
    with Session(migrated_engine) as session:
        assert BookmarkStatsDirtyRepository(session).backlog().count == 0


def _seed_users(engine: Engine, count: int = 2) -> None:
    with engine.begin() as connection:
        for user_id in range(1, count + 1):
            connection.execute(
                text(
                    "INSERT INTO users (id, username, email, password_hash, created_at) "
                    "VALUES (:id, :username, :email, 'hash', :created_at)"
                ),
                {
                    "id": user_id,
                    "username": f"user-{user_id}",
                    "email": f"user-{user_id}@example.test",
                    "created_at": "2026-08-06T12:00:00.000000Z",
                },
            )


def _seed_bookmark(engine: Engine, *, bookmark_id: int = 11, user_id: int = 1) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO bookmarks "
                "(id, url, title, description, user_id, created_at, updated_at) "
                "VALUES (:id, :url, :title, NULL, :user_id, :created_at, :created_at)"
            ),
            {
                "id": bookmark_id,
                "url": f"https://example.test/{bookmark_id}",
                "title": f"bookmark-{bookmark_id}",
                "user_id": user_id,
                "created_at": "2026-08-06T12:00:00.000000Z",
            },
        )


def _event(bookmark_id: int = 11) -> BookmarkStatsInvalidated:
    return BookmarkStatsInvalidated(
        user_id=1,
        window_start=datetime(2026, 8, 3, tzinfo=UTC),
        mutation_kind=BookmarkMutationKind.UPDATED,
        bookmark_id=bookmark_id,
        occurred_at=_NOW,
        correlation_id=_CORRELATION_ID,
    )


def test_full_reconciliation_publishes_zero_baseline_and_positive_marker_generation(
    migrated_engine: Engine,
) -> None:
    _seed_users(migrated_engine)
    _seed_bookmark(migrated_engine)
    with Session(migrated_engine) as session:
        dirty = BookmarkStatsDirtyRepository(session)
        dirty.mark_dirty(1, _NOW, DirtyReason.CREATE, _NOW)
        dirty.mark_dirty(1, _NOW, DirtyReason.UPDATE, _NOW + timedelta(seconds=1))
        session.commit()

    refresher, publisher, store = _runtime(migrated_engine)
    publisher.require_full_reconciliation()

    assert refresher.run_cycle(full=True)
    owner = store.get(1)
    empty = store.get(2)
    assert owner is not None and owner.source_generation == 2
    assert owner.stats.total_bookmarks == 1
    assert empty is not None and empty.source_generation == 0
    assert empty.stats.total_bookmarks == 0
    assert publisher.state().reconciliation_required
    with Session(migrated_engine) as verification:
        marker = BookmarkStatsDirtyRepository(verification).observe()[0]
        assert (marker.current_completed_generation, marker.projection_completed_generation) == (
            2,
            0,
        )


def test_lost_and_duplicate_hints_coalesce_behind_durable_marker(
    migrated_engine: Engine,
) -> None:
    _seed_users(migrated_engine, count=1)
    _seed_bookmark(migrated_engine)
    with Session(migrated_engine) as session:
        BookmarkStatsDirtyRepository(session).mark_dirty(1, _NOW, DirtyReason.CREATE, _NOW)
        session.commit()

    refresher, publisher, store = _runtime(migrated_engine)
    assert publisher.publish(_event(11)).value == "enqueued"
    assert publisher.publish(_event(12)).value == "enqueued"
    statements: list[str] = []

    def record(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement.strip())

    event.listen(migrated_engine, "before_cursor_execute", record)
    try:
        assert refresher.run_cycle()
    finally:
        event.remove(migrated_engine, "before_cursor_execute", record)

    record = store.get(1)
    assert record is not None and record.stats.total_bookmarks == 1
    compiled_totals = str(TOTALS_SQL.compile(dialect=migrated_engine.dialect)).strip()
    assert statements.count(compiled_totals) == 1
    with Session(migrated_engine) as verification:
        marker = BookmarkStatsDirtyRepository(verification).observe()[0]
        assert (marker.current_completed_generation, marker.projection_completed_generation) == (
            1,
            0,
        )


def test_concurrent_generation_increment_defeats_cleanup_and_snapshot_cas(
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_users(migrated_engine, count=1)
    _seed_bookmark(migrated_engine)
    with Session(migrated_engine) as session:
        BookmarkStatsDirtyRepository(session).mark_dirty(1, _NOW, DirtyReason.CREATE, _NOW)
        session.commit()

    refresher, publisher, store = _runtime(migrated_engine)
    original_acknowledge_current = BookmarkStatsDirtyRepository.acknowledge_current
    incremented = False

    def increment_then_acknowledge_current(
        repository: BookmarkStatsDirtyRepository,
        user_id: int,
        window_start: datetime,
        generation: int,
    ) -> Any:
        nonlocal incremented
        if not incremented:
            incremented = True
            with Session(migrated_engine) as writer:
                BookmarkStatsDirtyRepository(writer).mark_dirty(
                    1,
                    _NOW,
                    DirtyReason.UPDATE,
                    _NOW + timedelta(seconds=1),
                )
                writer.commit()
            assert publisher.publish(_event()).value == "enqueued"
        return original_acknowledge_current(repository, user_id, window_start, generation)

    monkeypatch.setattr(
        BookmarkStatsDirtyRepository,
        "acknowledge_current",
        increment_then_acknowledge_current,
    )
    assert not refresher.run_cycle()
    assert store.get(1) is None
    with Session(migrated_engine) as verification:
        marker = BookmarkStatsDirtyRepository(verification).observe()[0]
        assert marker.generation == 2


def test_compute_failure_keeps_marker_and_retry_recovers(
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_users(migrated_engine, count=1)
    with Session(migrated_engine) as session:
        BookmarkStatsDirtyRepository(session).mark_dirty(1, _NOW, DirtyReason.CREATE, _NOW)
        session.commit()

    refresher, _publisher, store = _runtime(migrated_engine)
    original_read = BookmarkStatsReader.read

    def fail_read(_reader: BookmarkStatsReader, _user_id: int) -> Any:
        raise RuntimeError("private-content-sentinel")

    monkeypatch.setattr(BookmarkStatsReader, "read", fail_read)
    assert not refresher.run_cycle()
    assert store.get(1) is None
    with Session(migrated_engine) as verification:
        assert BookmarkStatsDirtyRepository(verification).backlog().count == 1

    monkeypatch.setattr(BookmarkStatsReader, "read", original_read)
    assert refresher.run_cycle()
    assert store.get(1) is not None
    with Session(migrated_engine) as verification:
        marker = BookmarkStatsDirtyRepository(verification).observe()[0]
        assert (marker.current_completed_generation, marker.projection_completed_generation) == (
            1,
            0,
        )


def test_manual_cycles_never_overlap(
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_users(migrated_engine, count=1)
    with Session(migrated_engine) as session:
        BookmarkStatsDirtyRepository(session).mark_dirty(1, _NOW, DirtyReason.CREATE, _NOW)
        session.commit()

    refresher, _publisher, _store = _runtime(migrated_engine)
    entered = Event()
    release = Event()
    original_refresh = refresher._refresh_user

    def blocked_refresh(
        session: Session,
        user_id: int,
        markers: tuple[Any, ...],
    ) -> bool:
        entered.set()
        assert release.wait(2)
        return original_refresh(session, user_id, markers)

    monkeypatch.setattr(refresher, "_refresh_user", blocked_refresh)
    results: list[bool] = []
    thread = Thread(target=lambda: results.append(refresher.run_cycle()))
    thread.start()
    assert entered.wait(2)
    assert not refresher.run_cycle()
    release.set()
    thread.join(2)
    assert not thread.is_alive()
    assert results == [True]
    assert refresher.state().total_cycles == 1


def test_multiple_failed_users_preserve_first_failure_and_full_reconciliation(
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_users(migrated_engine)
    refresher, publisher, _store = _runtime(migrated_engine)

    def fail_users(_session: Session, user_id: int, _markers: tuple[Any, ...]) -> bool:
        assert user_id in {1, 2}
        return False

    monkeypatch.setattr(refresher, "_refresh_user", fail_users)
    assert not refresher.run_cycle(full=True)
    assert publisher.state().reconciliation_required


def test_multiple_user_exceptions_preserve_first_exception(
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_users(migrated_engine)
    refresher, publisher, _store = _runtime(migrated_engine)

    def raise_for_user(_session: Session, user_id: int, _markers: tuple[Any, ...]) -> bool:
        raise RuntimeError(f"private-user-{user_id}-sentinel")

    monkeypatch.setattr(refresher, "_refresh_user", raise_for_user)
    assert not refresher.run_cycle(full=True)
    assert publisher.state().reconciliation_required


def test_full_reconciliation_advances_bounded_cursor_before_acknowledging(
    migrated_engine: Engine,
) -> None:
    _seed_users(migrated_engine)
    refresher, publisher, store = _runtime(migrated_engine, batch_size=1)

    assert refresher.run_cycle(full=True)
    assert store.get(1) is not None and store.get(2) is None
    assert publisher.state().reconciliation_required
    assert refresher.run_cycle()
    assert store.get(2) is not None
    assert publisher.state().reconciliation_required
    assert refresher.run_cycle()
    assert not publisher.state().reconciliation_required


def test_snapshot_cas_rejection_rolls_back_marker_completion(
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_users(migrated_engine, count=1)
    with Session(migrated_engine) as session:
        BookmarkStatsDirtyRepository(session).mark_dirty(1, _NOW, DirtyReason.CREATE, _NOW)
        session.commit()

    refresher, _publisher, store = _runtime(migrated_engine)
    original_acknowledge_current = BookmarkStatsDirtyRepository.acknowledge_current

    def acknowledge_current_then_invalidate(
        repository: BookmarkStatsDirtyRepository,
        user_id: int,
        window_start: datetime,
        generation: int,
    ) -> Any:
        completed = original_acknowledge_current(repository, user_id, window_start, generation)
        store.invalidate(user_id)
        return completed

    monkeypatch.setattr(
        BookmarkStatsDirtyRepository,
        "acknowledge_current",
        acknowledge_current_then_invalidate,
    )
    assert not refresher.run_cycle()
    assert store.get(1) is None
    with Session(migrated_engine) as verification:
        assert BookmarkStatsDirtyRepository(verification).backlog().count == 1


def test_snapshot_publish_and_marker_commit_failures_remain_recoverable(
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_users(migrated_engine, count=1)
    with Session(migrated_engine) as session:
        BookmarkStatsDirtyRepository(session).mark_dirty(1, _NOW, DirtyReason.CREATE, _NOW)
        session.commit()

    refresher, _publisher, store = _runtime(migrated_engine)
    with Session(migrated_engine) as reader_session:
        prior_stats = BookmarkStatsReader(reader_session, 5).read(1)
        reader_session.rollback()
    assert store.publish(
        user_id=1,
        stats=prior_stats,
        generated_at=_NOW,
        source_generation=0,
        expected_epoch=0,
    )
    prior = store.get(1)

    def fail_publish(**_kwargs: object) -> bool:
        raise RuntimeError("private-publish-sentinel")

    monkeypatch.setattr(store, "publish", fail_publish)
    assert not refresher.run_cycle()
    assert store.epoch(1) == 0
    assert store.get(1) is prior
    with Session(migrated_engine) as verification:
        assert BookmarkStatsDirtyRepository(verification).backlog().count == 1

    monkeypatch.undo()

    class CommitFailingSession(Session):
        def commit(self) -> None:
            raise RuntimeError("private-commit-sentinel")

    failing_factory = sessionmaker(
        bind=migrated_engine,
        class_=CommitFailingSession,
        expire_on_commit=False,
    )
    commit_refresher, _publisher, commit_store = _runtime(migrated_engine)
    commit_refresher._session_factory = failing_factory
    assert not commit_refresher.run_cycle()
    assert commit_store.get(1) is None
    assert commit_store.epoch(1) == 1
    with Session(migrated_engine) as verification:
        assert BookmarkStatsDirtyRepository(verification).backlog().count == 1


def test_reconciliation_waits_for_every_dirty_batch_before_acknowledging(
    migrated_engine: Engine,
) -> None:
    _seed_users(migrated_engine, count=1)
    with Session(migrated_engine) as session:
        dirty = BookmarkStatsDirtyRepository(session)
        for weeks_ago in range(3):
            dirty.mark_dirty(
                1,
                _NOW - timedelta(weeks=weeks_ago),
                DirtyReason.RECONCILE,
                _NOW + timedelta(seconds=weeks_ago),
            )
        session.commit()

    refresher, publisher, _store = _runtime(migrated_engine, batch_size=1)
    publisher.require_full_reconciliation()
    assert refresher.run_cycle()
    assert refresher.run_cycle()
    assert publisher.state().reconciliation_required
    with Session(migrated_engine) as verification:
        assert BookmarkStatsDirtyRepository(verification).backlog().count == 3

    assert refresher.run_cycle()
    assert publisher.state().reconciliation_required


def test_new_reconciliation_epoch_cannot_be_cleared_by_an_older_full_scan(
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_users(migrated_engine, count=1)
    refresher, publisher, _store = _runtime(migrated_engine)
    publisher.require_full_reconciliation()
    original_acknowledge = publisher.acknowledge_full_reconciliation

    def race_acknowledgment(expected_epoch: int) -> bool:
        publisher.require_full_reconciliation()
        return original_acknowledge(expected_epoch)

    monkeypatch.setattr(publisher, "acknowledge_full_reconciliation", race_acknowledgment)
    assert refresher.run_cycle()
    assert publisher.state().reconciliation_required

    monkeypatch.setattr(publisher, "acknowledge_full_reconciliation", original_acknowledge)
    assert refresher.run_cycle()
    assert not publisher.state().reconciliation_required


def test_enabled_app_lifespan_owns_exact_worker_and_stops_it(
    database_url: str,
    migrated_engine: Engine,
) -> None:
    del migrated_engine
    app = create_app(
        Settings(
            app_env="test",
            database_url=database_url,
            stats_refresh_enabled=True,
            stats_refresh_interval_seconds=1,
            stats_stale_after_seconds=2,
            stats_full_reconciliation_seconds=1,
            stats_dirty_max_age_seconds=1,
        )
    )
    with TestClient(app):
        refresher: StatsRefresher = app.state.bookmark_stats_refresher
        state = refresher.state()
        assert state.started and state.alive and state.initial_completed and state.initial_success
        assert refresher._thread is not None
        assert refresher._thread.name == "bookmark-stats-refresher"
        assert not refresher._thread.daemon
        assert app.state.bookmark_stats_snapshot_healthy()

    assert not refresher.state().alive
