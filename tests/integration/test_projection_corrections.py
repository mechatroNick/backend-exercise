"""Correction and stale-generation evidence for private weekly projections."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Barrier, Event, Thread

import pytest
from sqlalchemy import Engine, text
from sqlmodel import Session

from app.bookmarks.stats.dirty import (
    BookmarkStatsDirtyRepository,
    DirtyAcknowledgement,
    DirtyAcknowledgementStatus,
    DirtyReason,
)
from app.bookmarks.stats.projection_repository import (
    CorrectionReason,
    NewProjectionPoint,
    ProjectionCalculationVersionMismatchError,
    WeeklyProjectionRepository,
)
from app.bookmarks.stats.projection_service import (
    BaselineRunner,
    ProjectionProcessor,
    ProjectionProcessOutcome,
)
from app.bookmarks.stats.weekly import WeeklyStatsReader, calculate_weekly_payload, weekly_window

_NOW = datetime(2026, 8, 18, 12, tzinfo=UTC)
_CLOSED = weekly_window(datetime(2026, 8, 5, 12, tzinfo=UTC))
_CURRENT = weekly_window(_NOW)


class _Clock:
    def now(self) -> datetime:
        return _NOW


def _seed(session: Session, created_at: datetime) -> None:
    encoded = created_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    session.execute(
        text(
            "INSERT INTO users (id, username, email, password_hash, created_at) "
            "VALUES (1, 'correction', 'correction@example.test', 'hash', :created_at)"
        ),
        {"created_at": encoded},
    )
    session.execute(
        text(
            "INSERT INTO bookmarks (id, url, title, description, user_id, created_at, updated_at) "
            "VALUES (1, 'https://example.test/1', 'one', NULL, 1, :created_at, :created_at)"
        ),
        {"created_at": encoded},
    )


def _baseline(engine: Engine) -> None:
    BaselineRunner(
        session_factory=lambda: Session(engine), clock=_Clock(), top_tags_limit=5, batch_size=100
    ).run_step()


def _process_marker(session: Session) -> None:
    marker = BookmarkStatsDirtyRepository(session).observe()[0]
    result = ProjectionProcessor(clock=_Clock(), top_tags_limit=5).process_dirty(session, marker)
    assert result.outcome is ProjectionProcessOutcome.APPLIED


def test_a_b_a_corrections_are_append_only_with_immediate_predecessors(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed(session, _CLOSED.start)
        session.commit()
    _baseline(migrated_engine)
    with Session(migrated_engine) as session:
        original_hash = session.execute(
            text("SELECT content_hash FROM bookmark_stats_window_point WHERE revision=1")
        ).scalar_one()
        encoded = (_CLOSED.start + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        session.execute(
            text(
                "INSERT INTO bookmarks "
                "(id, url, title, description, user_id, created_at, updated_at) "
                "VALUES (2, 'https://example.test/2', 'two', NULL, 1, :created_at, :created_at)"
            ),
            {"created_at": encoded},
        )
        BookmarkStatsDirtyRepository(session).mark_dirty(1, _CLOSED.start, DirtyReason.CREATE, _NOW)
        session.commit()
    with Session(migrated_engine) as session:
        _process_marker(session)
        session.commit()
    with Session(migrated_engine) as session:
        session.execute(text("DELETE FROM bookmarks WHERE id=2"))
        BookmarkStatsDirtyRepository(session).mark_dirty(
            1, _CLOSED.start, DirtyReason.DELETE, _NOW + timedelta(seconds=1)
        )
        session.commit()
    with Session(migrated_engine) as session:
        _process_marker(session)
        session.commit()
    with Session(migrated_engine) as session:
        rows = session.execute(
            text(
                "SELECT id, revision, supersedes_id, content_hash, correction_reason "
                "FROM bookmark_stats_window_point ORDER BY revision"
            )
        ).all()
        assert [row[1] for row in rows] == [1, 2, 3]
        assert rows[1][2] == rows[0][0]
        assert rows[2][2] == rows[1][0]
        assert rows[0][3] == rows[2][3] == original_hash
        assert rows[1][4] == rows[2][4] == "late_recalculation"


def test_stale_projection_acknowledgement_rolls_back_replaced_current_row(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed(session, _CURRENT.start)
        session.commit()
    _baseline(migrated_engine)
    with Session(migrated_engine) as session:
        BookmarkStatsDirtyRepository(session).mark_dirty(
            1, _CURRENT.start, DirtyReason.UPDATE, _NOW
        )
        session.commit()

    class _StaleDirtyRepository:
        def __init__(self, session: Session) -> None:
            self._session = session

        def acknowledge_projection(
            self, user_id: int, window_start: datetime, generation: int
        ) -> DirtyAcknowledgement:
            del user_id, window_start, generation
            return DirtyAcknowledgement(status=DirtyAcknowledgementStatus.STALE)

    with Session(migrated_engine) as session:
        marker = BookmarkStatsDirtyRepository(session).observe()[0]
        result = ProjectionProcessor(
            clock=_Clock(), top_tags_limit=5, dirty_repository_factory=_StaleDirtyRepository
        ).process_dirty(session, marker)
        assert result.outcome is ProjectionProcessOutcome.STALE
        assert (
            session.execute(
                text(
                    "SELECT source_generation FROM bookmark_stats_window_working "
                    "WHERE user_id=1 AND window_start=:window_start"
                ),
                {"window_start": _CURRENT.start.strftime("%Y-%m-%dT%H:%M:%S.%fZ")},
            ).scalar_one()
            == 0
        )
    with Session(migrated_engine) as session:
        marker = BookmarkStatsDirtyRepository(session).observe()[0]
        assert marker.generation == 1
        assert marker.projection_completed_generation == 0


def test_state_version_mismatch_leaves_dirty_and_rows_untouched(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        _seed(session, _CLOSED.start)
        BookmarkStatsDirtyRepository(session).mark_dirty(1, _CLOSED.start, DirtyReason.UPDATE, _NOW)
        session.commit()
    _baseline(migrated_engine)
    with Session(migrated_engine) as session:
        session.execute(
            text(
                "UPDATE bookmark_stats_projection_state "
                "SET calculation_version='weekly-v1;payload-schema=1;top-tags-limit=4' WHERE id=1"
            )
        )
        session.commit()
    with Session(migrated_engine) as session:
        marker = BookmarkStatsDirtyRepository(session).observe()[0]
        with pytest.raises(ProjectionCalculationVersionMismatchError, match="calculation version"):
            ProjectionProcessor(clock=_Clock(), top_tags_limit=5).process_dirty(session, marker)
    with Session(migrated_engine) as session:
        marker = BookmarkStatsDirtyRepository(session).observe()[0]
        assert marker.projection_completed_generation == 0
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_point")).scalar_one()
            == 1
        )


def test_same_hash_dirty_acknowledges_then_last_bookmark_deletion_appends_zero_correction(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed(session, _CLOSED.start)
        session.commit()
    _baseline(migrated_engine)
    with Session(migrated_engine) as session:
        dirty = BookmarkStatsDirtyRepository(session)
        dirty.mark_dirty(1, _CLOSED.start, DirtyReason.UPDATE, _NOW)
        session.commit()
    with Session(migrated_engine) as session:
        _process_marker(session)
        session.commit()
    with Session(migrated_engine) as session:
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_point")).scalar_one()
            == 1
        )
        marker = BookmarkStatsDirtyRepository(session).observe()[0]
        assert marker.projection_completed_generation == marker.generation
        session.execute(text("DELETE FROM bookmarks WHERE id=1"))
        BookmarkStatsDirtyRepository(session).mark_dirty(
            1, _CLOSED.start, DirtyReason.DELETE, _NOW + timedelta(seconds=1)
        )
        session.commit()
    with Session(migrated_engine) as session:
        _process_marker(session)
        session.commit()
    with Session(migrated_engine) as session:
        point = session.execute(
            text(
                "SELECT revision, correction_reason, payload FROM bookmark_stats_window_point "
                "ORDER BY revision DESC LIMIT 1"
            )
        ).one()
        assert point[0:2] == (2, "late_recalculation")
        assert '"total_bookmarks":0' in point[2]


def test_barrier_controlled_generation_race_rolls_back_then_retries_once(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed(session, _CURRENT.start)
        BookmarkStatsDirtyRepository(session).mark_dirty(
            1, _CURRENT.start, DirtyReason.UPDATE, _NOW
        )
        session.commit()
    _baseline(migrated_engine)
    with Session(migrated_engine) as session:
        stale_marker = BookmarkStatsDirtyRepository(session).observe()[0]

    turn = Barrier(2)
    incremented = Event()
    writer_errors: list[BaseException] = []

    def increment_generation() -> None:
        try:
            turn.wait(timeout=5)
            with Session(migrated_engine) as writer:
                BookmarkStatsDirtyRepository(writer).mark_dirty(
                    1, _CURRENT.start, DirtyReason.UPDATE, _NOW + timedelta(seconds=1)
                )
                writer.commit()
        except BaseException as error:  # pragma: no cover - surfaced by assertion.
            writer_errors.append(error)
        finally:
            incremented.set()

    writer = Thread(target=increment_generation)
    writer.start()
    turn.wait(timeout=5)
    assert incremented.wait(timeout=5)
    writer.join(timeout=5)
    assert not writer.is_alive()
    assert writer_errors == []

    with Session(migrated_engine) as session:
        result = ProjectionProcessor(clock=_Clock(), top_tags_limit=5).process_dirty(
            session, stale_marker
        )
        assert result.outcome is ProjectionProcessOutcome.STALE
    with Session(migrated_engine) as session:
        marker = BookmarkStatsDirtyRepository(session).observe()[0]
        assert marker.generation == 2
        assert marker.projection_completed_generation == 0
        assert (
            session.execute(
                text("SELECT source_generation FROM bookmark_stats_window_working")
            ).scalar_one()
            == 0
        )
        result = ProjectionProcessor(clock=_Clock(), top_tags_limit=5).process_dirty(
            session, marker
        )
        assert result.outcome is ProjectionProcessOutcome.APPLIED
        session.commit()
    with Session(migrated_engine) as session:
        marker = BookmarkStatsDirtyRepository(session).observe()[0]
        assert marker.generation == marker.projection_completed_generation == 2


def test_barrier_revision_race_has_one_winner_and_retry_keeps_predecessor_chain(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed(session, _CLOSED.start)
        encoded = (_CLOSED.start + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        session.execute(
            text(
                "INSERT INTO bookmarks "
                "(id, url, title, description, user_id, created_at, updated_at) "
                "VALUES (2, 'https://example.test/2', 'two', NULL, 1, :created_at, :created_at)"
            ),
            {"created_at": encoded},
        )
        session.commit()
    _baseline(migrated_engine)

    start = Barrier(2)
    successes: list[int] = []
    failures: list[BaseException] = []

    def append_same_revision() -> None:
        try:
            with Session(migrated_engine) as session:
                repository = WeeklyProjectionRepository(session)
                previous = repository.effective_point(1, _CLOSED)
                assert previous is not None
                calculation = calculate_weekly_payload(
                    WeeklyStatsReader(session, 5).read(1, _CLOSED), 5
                )
                start.wait(timeout=5)
                point = repository.append_point(
                    NewProjectionPoint(
                        user_id=1,
                        window=_CLOSED,
                        revision=previous.revision + 1,
                        supersedes_id=previous.id,
                        payload=calculation.payload,
                        calculated_at=_NOW,
                        developed_at=_NOW,
                        correction_reason=CorrectionReason.LATE_RECALCULATION,
                        source_generation=1,
                        calculation_version=calculation.calculation_version,
                        content_hash=calculation.content_hash,
                    )
                )
                session.commit()
                successes.append(point.id)
        except BaseException as error:  # pragma: no cover - surfaced by assertion.
            failures.append(error)

    left, right = Thread(target=append_same_revision), Thread(target=append_same_revision)
    left.start()
    right.start()
    left.join(timeout=5)
    right.join(timeout=5)
    assert not left.is_alive() and not right.is_alive()
    assert len(successes) == 1
    assert len(failures) == 1

    with Session(migrated_engine) as session:
        repository = WeeklyProjectionRepository(session)
        previous = repository.effective_point(1, _CLOSED)
        assert previous is not None and previous.revision == 2
        encoded = (_CLOSED.start + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        session.execute(
            text(
                "INSERT INTO bookmarks "
                "(id, url, title, description, user_id, created_at, updated_at) "
                "VALUES (3, 'https://example.test/3', 'three', NULL, 1, :created_at, :created_at)"
            ),
            {"created_at": encoded},
        )
        calculation = calculate_weekly_payload(WeeklyStatsReader(session, 5).read(1, _CLOSED), 5)
        retried = repository.append_point(
            NewProjectionPoint(
                user_id=1,
                window=_CLOSED,
                revision=previous.revision + 1,
                supersedes_id=previous.id,
                payload=calculation.payload,
                calculated_at=_NOW,
                developed_at=_NOW,
                correction_reason=CorrectionReason.LATE_RECALCULATION,
                source_generation=2,
                calculation_version=calculation.calculation_version,
                content_hash=calculation.content_hash,
            )
        )
        session.commit()
        assert retried.revision == 3 and retried.supersedes_id == previous.id
