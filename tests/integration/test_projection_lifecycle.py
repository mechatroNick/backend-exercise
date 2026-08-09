"""Transaction-level evidence for developing weekly projection lifecycle work."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.bookmarks.stats.dirty import BookmarkStatsDirtyRepository, DirtyReason
from app.bookmarks.stats.projection_repository import (
    ProjectionCalculationVersionMismatchError,
    ProjectionCandidateError,
    WeeklyProjectionRepository,
)
from app.bookmarks.stats.projection_service import (
    BaselineRunner,
    ProjectionProcessor,
    ProjectionProcessOutcome,
)
from app.bookmarks.stats.weekly import weekly_window

_CLOSED_NOW = datetime(2026, 8, 18, 12, tzinfo=UTC)
_CLOSED_WINDOW = weekly_window(datetime(2026, 8, 5, 12, tzinfo=UTC))
_CURRENT_WINDOW = weekly_window(_CLOSED_NOW)


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def _seed_user(session: Session, user_id: int = 1) -> None:
    session.execute(
        text(
            "INSERT INTO users (id, username, email, password_hash, created_at) "
            "VALUES (:id, :username, :email, 'hash', '2026-08-01T00:00:00.000000Z')"
        ),
        {"id": user_id, "username": f"weekly-{user_id}", "email": f"weekly-{user_id}@example.test"},
    )


def _seed_bookmark(session: Session, bookmark_id: int, created_at: datetime) -> None:
    encoded = created_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    session.execute(
        text(
            "INSERT INTO bookmarks (id, url, title, description, user_id, created_at, updated_at) "
            "VALUES (:id, :url, 'weekly', NULL, 1, :created_at, :created_at)"
        ),
        {"id": bookmark_id, "url": f"https://example.test/{bookmark_id}", "created_at": encoded},
    )


def _baseline(engine: Engine, now: datetime) -> None:
    BaselineRunner(
        session_factory=lambda: Session(engine),
        clock=_Clock(now),
        top_tags_limit=5,
        batch_size=100,
    ).run_step()


def _processor(now: datetime) -> ProjectionProcessor:
    return ProjectionProcessor(clock=_Clock(now), top_tags_limit=5)


def test_closed_dirty_change_appends_revision_and_keeps_marker_until_current_ack(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session)
        _seed_bookmark(session, 1, _CLOSED_WINDOW.start)
        session.commit()
    _baseline(migrated_engine, _CLOSED_NOW)
    with Session(migrated_engine) as session:
        _seed_bookmark(session, 2, _CLOSED_WINDOW.start + timedelta(days=1))
        dirty = BookmarkStatsDirtyRepository(session)
        dirty.mark_dirty(1, _CLOSED_WINDOW.start, DirtyReason.CREATE, _CLOSED_NOW)
        session.commit()
    with Session(migrated_engine) as session:
        marker = BookmarkStatsDirtyRepository(session).observe()[0]
        result = _processor(_CLOSED_NOW).process_dirty(session, marker)
        assert result.outcome is ProjectionProcessOutcome.APPLIED
        assert result.appended_revision == 2
        session.commit()
    with Session(migrated_engine) as session:
        points = session.execute(
            text(
                "SELECT revision, supersedes_id, correction_reason, source_generation "
                "FROM bookmark_stats_window_point ORDER BY revision"
            )
        ).all()
        assert points[0][0] == 1
        assert points[1][0] == 2
        assert points[1][1] is not None
        assert points[1][2:] == ("late_recalculation", 1)
        marker = BookmarkStatsDirtyRepository(session).observe()[0]
        assert marker.projection_completed_generation == marker.generation == 1
        assert marker.current_completed_generation == 0


def test_current_dirty_replaces_developing_row_even_when_aggregate_is_empty(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session)
        _seed_bookmark(session, 1, _CURRENT_WINDOW.start)
        session.commit()
    _baseline(migrated_engine, _CLOSED_NOW)
    with Session(migrated_engine) as session:
        session.execute(text("DELETE FROM bookmarks WHERE id=1"))
        BookmarkStatsDirtyRepository(session).mark_dirty(
            1, _CURRENT_WINDOW.start, DirtyReason.DELETE, _CLOSED_NOW
        )
        session.commit()
    with Session(migrated_engine) as session:
        marker = BookmarkStatsDirtyRepository(session).observe()[0]
        assert (
            _processor(_CLOSED_NOW).process_dirty(session, marker).outcome
            is ProjectionProcessOutcome.APPLIED
        )
        session.commit()
    with Session(migrated_engine) as session:
        row = session.execute(
            text(
                "SELECT source_generation, payload FROM bookmark_stats_window_working "
                "WHERE user_id=1 AND window_start=:start"
            ),
            {"start": _CURRENT_WINDOW.start.strftime("%Y-%m-%dT%H:%M:%S.%fZ")},
        ).one()
        assert row[0] == 1
        assert '"total_bookmarks":0' in row[1]


def test_overdue_finalizes_fresh_payload_and_creates_only_the_window_containing_now(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session)
        _seed_bookmark(session, 1, _CURRENT_WINDOW.start)
        session.commit()
    _baseline(migrated_engine, _CLOSED_NOW)
    later = datetime(2026, 8, 25, 0, tzinfo=UTC)
    with Session(migrated_engine) as session:
        repository = WeeklyProjectionRepository(session)
        observed = repository.observe_overdue(later)[0]
        result = _processor(later).process_overdue(session, observed)
        assert result.outcome is ProjectionProcessOutcome.APPLIED
        assert result.appended_revision == 1
        assert result.created_current_working is True
        session.commit()
    with Session(migrated_engine) as session:
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_point")).scalar_one()
            == 1
        )
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_working")).scalar_one()
            == 1
        )
        assert (
            session.execute(
                text(
                    "SELECT count(*) FROM bookmark_stats_window_working "
                    "WHERE window_start='2026-08-24T00:00:00.000000Z'"
                )
            ).scalar_one()
            == 1
        )


def test_pending_dirty_defers_overdue_without_mutating_rows(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session)
        _seed_bookmark(session, 1, _CURRENT_WINDOW.start)
        session.commit()
    _baseline(migrated_engine, _CLOSED_NOW)
    later = datetime(2026, 8, 25, 0, tzinfo=UTC)
    with Session(migrated_engine) as session:
        BookmarkStatsDirtyRepository(session).mark_dirty(
            1, _CURRENT_WINDOW.start, DirtyReason.UPDATE, later
        )
        session.commit()
    with Session(migrated_engine) as session:
        repository = WeeklyProjectionRepository(session)
        observed = repository.observe_overdue(later)[0]
        assert (
            _processor(later).process_overdue(session, observed).outcome
            is ProjectionProcessOutcome.DEFERRED
        )
        session.commit()
    with Session(migrated_engine) as session:
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_point")).scalar_one()
            == 0
        )
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_working")).scalar_one()
            == 1
        )


@pytest.mark.parametrize("when", [_CLOSED_WINDOW.end, _CLOSED_WINDOW.end + timedelta(seconds=1)])
def test_exact_closed_boundary_is_developed_not_replaced(
    migrated_engine: Engine, when: datetime
) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session)
        _seed_bookmark(session, 1, _CLOSED_WINDOW.start)
        session.commit()
    _baseline(migrated_engine, _CLOSED_NOW)
    with Session(migrated_engine) as session:
        BookmarkStatsDirtyRepository(session).mark_dirty(
            1, _CLOSED_WINDOW.start, DirtyReason.UPDATE, when
        )
        session.commit()
    with Session(migrated_engine) as session:
        marker = BookmarkStatsDirtyRepository(session).observe()[0]
        assert _processor(when).process_dirty(session, marker).appended_revision is None
        session.commit()
    with Session(migrated_engine) as session:
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_working")).scalar_one()
            == 1
        )
        assert (
            session.execute(
                text("SELECT source_generation FROM bookmark_stats_window_working")
            ).scalar_one()
            == 0
        )


def test_overdue_working_version_mismatch_rolls_back_without_append_or_delete(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session)
        _seed_bookmark(session, 1, _CURRENT_WINDOW.start)
        session.commit()
    _baseline(migrated_engine, _CLOSED_NOW)
    later = datetime(2026, 8, 25, 0, tzinfo=UTC)
    with Session(migrated_engine) as session:
        session.execute(
            text(
                "UPDATE bookmark_stats_window_working "
                "SET calculation_version='weekly-v1;payload-schema=1;top-tags-limit=4'"
            )
        )
        session.commit()
    with Session(migrated_engine) as session:
        repository = WeeklyProjectionRepository(session)
        observed = repository.observe_overdue(later)[0]
        with pytest.raises(ProjectionCalculationVersionMismatchError, match="overdue working"):
            _processor(later).process_overdue(session, observed)
    with Session(migrated_engine) as session:
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_point")).scalar_one()
            == 0
        )
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_working")).scalar_one()
            == 1
        )


def test_current_dirty_working_version_mismatch_keeps_marker_unacknowledged(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session)
        _seed_bookmark(session, 1, _CURRENT_WINDOW.start)
        session.commit()
    _baseline(migrated_engine, _CLOSED_NOW)
    with Session(migrated_engine) as session:
        session.execute(
            text(
                "UPDATE bookmark_stats_window_working "
                "SET calculation_version='weekly-v1;payload-schema=1;top-tags-limit=4'"
            )
        )
        BookmarkStatsDirtyRepository(session).mark_dirty(
            1, _CURRENT_WINDOW.start, DirtyReason.UPDATE, _CLOSED_NOW
        )
        session.commit()
    with Session(migrated_engine) as session:
        marker = BookmarkStatsDirtyRepository(session).observe()[0]
        with pytest.raises(ProjectionCalculationVersionMismatchError, match="stored working"):
            _processor(_CLOSED_NOW).process_dirty(session, marker)
    with Session(migrated_engine) as session:
        assert (
            BookmarkStatsDirtyRepository(session).observe()[0].projection_completed_generation == 0
        )


def test_dirty_boundary_finalizes_actual_developing_row_and_creates_next_current(
    migrated_engine: Engine,
) -> None:
    initial_now = datetime(2026, 8, 18, 12, tzinfo=UTC)
    boundary = weekly_window(initial_now).end
    with Session(migrated_engine) as session:
        _seed_user(session)
        _seed_bookmark(session, 1, weekly_window(initial_now).start)
        session.commit()
    _baseline(migrated_engine, initial_now)
    with Session(migrated_engine) as session:
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_working")).scalar_one()
            == 1
        )
        BookmarkStatsDirtyRepository(session).mark_dirty(
            1, weekly_window(initial_now).start, DirtyReason.UPDATE, boundary
        )
        session.commit()
    with Session(migrated_engine) as session:
        marker = BookmarkStatsDirtyRepository(session).observe()[0]
        result = _processor(boundary).process_dirty(session, marker)
        assert result.outcome is ProjectionProcessOutcome.APPLIED
        assert result.appended_revision == 1
        assert result.created_current_working is True
        session.commit()
    with Session(migrated_engine) as session:
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_point")).scalar_one()
            == 1
        )
        current = session.execute(
            text("SELECT window_start, source_generation FROM bookmark_stats_window_working")
        ).one()
        assert current == (boundary.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), 0)


def test_overdue_ignores_corrupted_developing_payload_and_uses_fresh_canonical_read(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session)
        _seed_bookmark(session, 1, _CURRENT_WINDOW.start)
        session.commit()
    _baseline(migrated_engine, _CLOSED_NOW)
    later = datetime(2026, 8, 25, 0, tzinfo=UTC)
    with Session(migrated_engine) as session:
        session.execute(
            text("UPDATE bookmark_stats_window_working SET payload='stale-not-canonical'")
        )
        observed = WeeklyProjectionRepository(session).observe_overdue(later)[0]
        result = _processor(later).process_overdue(session, observed)
        assert result.appended_revision == 1
        session.commit()
    with Session(migrated_engine) as session:
        payload = session.execute(
            text("SELECT payload FROM bookmark_stats_window_point")
        ).scalar_one()
        assert payload != "stale-not-canonical"
        assert '"total_bookmarks":1' in payload


def test_overdue_absent_and_non_overdue_paths_do_not_mutate(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session)
        _seed_bookmark(session, 1, _CURRENT_WINDOW.start)
        session.commit()
    _baseline(migrated_engine, _CLOSED_NOW)
    with Session(migrated_engine) as session:
        observed = WeeklyProjectionRepository(session).get_working(1, _CURRENT_WINDOW)
        assert observed is not None
        session.execute(text("DELETE FROM bookmark_stats_window_working"))
        assert (
            _processor(_CLOSED_NOW).process_overdue(session, observed).outcome
            is ProjectionProcessOutcome.ABSENT
        )
        session.commit()
    with Session(migrated_engine) as session:
        WeeklyProjectionRepository(session).replace_working(observed)
        session.commit()
    with Session(migrated_engine) as session:
        observed = WeeklyProjectionRepository(session).get_working(1, _CURRENT_WINDOW)
        assert observed is not None
        with pytest.raises(ProjectionCandidateError, match="not overdue"):
            _processor(_CLOSED_NOW).process_overdue(session, observed)
    with Session(migrated_engine) as session:
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_working")).scalar_one()
            == 1
        )


def test_deleted_user_marker_cannot_recreate_private_projection_rows(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session)
        _seed_bookmark(session, 1, _CURRENT_WINDOW.start)
        session.commit()
    _baseline(migrated_engine, _CLOSED_NOW)
    with Session(migrated_engine) as session:
        BookmarkStatsDirtyRepository(session).mark_dirty(
            1, _CURRENT_WINDOW.start, DirtyReason.UPDATE, _CLOSED_NOW
        )
        marker = BookmarkStatsDirtyRepository(session).observe()[0]
        session.execute(text("DELETE FROM users WHERE id=1"))
        session.commit()
    with Session(migrated_engine) as session, pytest.raises(IntegrityError):
        _processor(_CLOSED_NOW).process_dirty(session, marker)
    with Session(migrated_engine) as session:
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_working")).scalar_one()
            == 0
        )
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_point")).scalar_one()
            == 0
        )
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_dirty")).scalar_one()
            == 0
        )


def test_overdue_preserves_existing_compatible_positive_generation_current_row(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session)
        _seed_bookmark(session, 1, _CURRENT_WINDOW.start)
        session.commit()
    _baseline(migrated_engine, _CLOSED_NOW)
    later = datetime(2026, 8, 25, 0, tzinfo=UTC)
    current = weekly_window(later)
    with Session(migrated_engine) as session:
        repository = WeeklyProjectionRepository(session)
        old = repository.get_working(1, _CURRENT_WINDOW)
        assert old is not None
        repository.replace_working(
            old.model_copy(
                update={"window": current, "source_generation": 9, "calculated_at": later}
            )
        )
        observed = repository.observe_overdue(later)[0]
        assert _processor(later).process_overdue(session, observed).created_current_working is False
        session.commit()
    with Session(migrated_engine) as session:
        assert (
            session.execute(
                text("SELECT source_generation FROM bookmark_stats_window_working")
            ).scalar_one()
            == 9
        )


@pytest.mark.parametrize("fault", ["read", "ack", "commit"])
def test_dirty_transaction_faults_leave_marker_and_working_row_retriable(
    migrated_engine: Engine, fault: str
) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session)
        _seed_bookmark(session, 1, _CURRENT_WINDOW.start)
        session.commit()
    _baseline(migrated_engine, _CLOSED_NOW)
    with Session(migrated_engine) as session:
        BookmarkStatsDirtyRepository(session).mark_dirty(
            1, _CURRENT_WINDOW.start, DirtyReason.UPDATE, _CLOSED_NOW
        )
        session.commit()

    if fault == "read":
        processor = ProjectionProcessor(
            clock=_Clock(_CLOSED_NOW),
            top_tags_limit=5,
            reader_factory=lambda _session, _limit: (_ for _ in ()).throw(
                RuntimeError("read fault")
            ),
        )
    elif fault == "ack":

        class _AckFault:
            def __init__(self, _session: Session) -> None:
                pass

            def acknowledge_projection(
                self, _user_id: int, _window_start: datetime, _generation: int
            ) -> None:
                raise RuntimeError("ack fault")

        processor = ProjectionProcessor(
            clock=_Clock(_CLOSED_NOW), top_tags_limit=5, dirty_repository_factory=_AckFault
        )
    else:
        processor = _processor(_CLOSED_NOW)

    with Session(migrated_engine) as session:
        marker = BookmarkStatsDirtyRepository(session).observe()[0]
        if fault == "commit":
            original_commit = session.commit

            def fail_commit() -> None:
                raise RuntimeError("commit fault")

            session.commit = fail_commit  # type: ignore[method-assign]
            assert (
                processor.process_dirty(session, marker).outcome is ProjectionProcessOutcome.APPLIED
            )
            with pytest.raises(RuntimeError, match="commit fault"):
                session.commit()
            session.rollback()
            session.commit = original_commit  # type: ignore[method-assign]
        else:
            with pytest.raises(RuntimeError, match=f"{fault} fault"):
                processor.process_dirty(session, marker)
    with Session(migrated_engine) as session:
        marker = BookmarkStatsDirtyRepository(session).observe()[0]
        assert marker.generation == 1 and marker.projection_completed_generation == 0
        assert (
            session.execute(
                text("SELECT source_generation FROM bookmark_stats_window_working")
            ).scalar_one()
            == 0
        )
