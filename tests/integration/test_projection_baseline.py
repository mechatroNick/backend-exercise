"""Migrated-SQLite evidence for the restartable surviving-data projection baseline."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlmodel import Session

from app.bookmarks.stats.projection_repository import (
    ProjectionCalculationVersionMismatchError,
    ProjectionCandidateError,
    ProjectionStateTransitionError,
    WeeklyProjectionRepository,
)
from app.bookmarks.stats.projection_service import BaselineRunner
from app.bookmarks.stats.weekly import WeeklyStatsReader, calculation_version, weekly_window

_NOW = datetime(2026, 8, 18, 12, tzinfo=UTC)
_CLOSED = weekly_window(datetime(2026, 8, 5, 12, tzinfo=UTC))
_CURRENT = weekly_window(_NOW)
_RUNTIME_VERSION = calculation_version(5)


class _FixedClock:
    def __init__(self, value: datetime) -> None:
        self._value = value

    def now(self) -> datetime:
        return self._value


def _seed_user(session: Session, user_id: int) -> None:
    session.execute(
        text(
            "INSERT INTO users (id, username, email, password_hash, created_at) "
            "VALUES (:id, :username, :email, 'hash', :created_at)"
        ),
        {
            "id": user_id,
            "username": f"baseline-user-{user_id}",
            "email": f"baseline-user-{user_id}@example.test",
            "created_at": "2026-08-01T00:00:00.000000Z",
        },
    )


def _seed_bookmark(
    session: Session,
    *,
    bookmark_id: int,
    user_id: int,
    created_at: datetime,
    title: str = "Baseline bookmark",
) -> None:
    encoded = created_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    session.execute(
        text(
            "INSERT INTO bookmarks (id, url, title, description, user_id, created_at, updated_at) "
            "VALUES (:id, :url, :title, NULL, :user_id, :created_at, :updated_at)"
        ),
        {
            "id": bookmark_id,
            "url": f"https://example.test/{bookmark_id}",
            "title": title,
            "user_id": user_id,
            "created_at": encoded,
            "updated_at": encoded,
        },
    )


def _runner(
    engine: Engine,
    *,
    now: datetime = _NOW,
    batch_size: int = 100,
    session_factory: Callable[[], Session] | None = None,
    reader_factory: Callable[[Session, int], WeeklyStatsReader] = WeeklyStatsReader,
) -> BaselineRunner:
    return BaselineRunner(
        session_factory=session_factory or (lambda: Session(engine)),
        clock=_FixedClock(now),
        top_tags_limit=5,
        batch_size=batch_size,
        reader_factory=reader_factory,
    )


def _state(session: Session) -> tuple[object, ...]:
    return session.execute(
        text(
            "SELECT status, calculation_version, checkpoint_user_id, checkpoint_window_start, "
            "baseline_started_at, baseline_completed_at, failure_code "
            "FROM bookmark_stats_projection_state WHERE id=1"
        )
    ).one()


def test_empty_database_activates_without_projection_rows(migrated_engine: Engine) -> None:
    outcome = _runner(migrated_engine).run_step()

    assert outcome.processed_candidate_count == 0
    assert outcome.has_more is False
    assert outcome.active is True
    with Session(migrated_engine) as session:
        state = _state(session)
        assert state == (
            "active",
            _RUNTIME_VERSION,
            None,
            None,
            _NOW.isoformat().replace("+00:00", ".000000Z"),
            _NOW.isoformat().replace("+00:00", ".000000Z"),
            None,
        )
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_point")).scalar_one()
            == 0
        )
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_working")).scalar_one()
            == 0
        )

    assert _runner(migrated_engine).run_step().model_dump() == {
        "processed_candidate_count": 0,
        "has_more": False,
        "active": True,
    }


def test_baseline_creates_only_surviving_closed_and_current_windows(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session, 1)
        _seed_user(session, 2)
        _seed_bookmark(session, bookmark_id=1, user_id=1, created_at=_CLOSED.start)
        _seed_bookmark(session, bookmark_id=2, user_id=1, created_at=_CURRENT.start)
        _seed_bookmark(session, bookmark_id=3, user_id=2, created_at=_CLOSED.start)
        session.execute(text("DELETE FROM bookmarks WHERE id=3"))
        session.commit()

    assert _runner(migrated_engine).run_step().active is True

    with Session(migrated_engine) as session:
        points = session.execute(
            text(
                "SELECT user_id, window_start, revision, source_generation FROM "
                "bookmark_stats_window_point ORDER BY user_id, window_start"
            )
        ).all()
        working = session.execute(
            text(
                "SELECT user_id, window_start, source_generation FROM "
                "bookmark_stats_window_working ORDER BY user_id, window_start"
            )
        ).all()
        assert points == [(1, "2026-08-03T00:00:00.000000Z", 1, 0)]
        assert working == [(1, "2026-08-17T00:00:00.000000Z", 0)]
        assert (
            session.execute(
                text(
                    "SELECT count(*) FROM bookmark_stats_window_point "
                    "WHERE window_start='2026-08-10T00:00:00.000000Z'"
                )
            ).scalar_one()
            == 0
        )


def test_baseline_advances_exclusive_lexicographic_checkpoint_across_pages(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        for user_id in (1, 2):
            _seed_user(session, user_id)
        _seed_bookmark(session, bookmark_id=1, user_id=1, created_at=_CLOSED.start)
        _seed_bookmark(session, bookmark_id=2, user_id=1, created_at=_CURRENT.start)
        _seed_bookmark(session, bookmark_id=3, user_id=2, created_at=_CLOSED.start)
        session.commit()

    runner = _runner(migrated_engine, batch_size=1)
    assert runner.run_step().model_dump() == {
        "processed_candidate_count": 1,
        "has_more": True,
        "active": False,
    }
    with Session(migrated_engine) as session:
        assert _state(session)[0:4] == (
            "running",
            _RUNTIME_VERSION,
            1,
            "2026-08-03T00:00:00.000000Z",
        )
    assert runner.run_step().has_more is True
    assert runner.run_step().active is True

    with Session(migrated_engine) as session:
        assert _state(session)[0] == "active"
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_point")).scalar_one()
            == 2
        )
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_working")).scalar_one()
            == 1
        )


def test_restart_from_rewound_checkpoint_does_not_duplicate_root_and_replaces_working(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session, 1)
        _seed_bookmark(session, bookmark_id=1, user_id=1, created_at=_CLOSED.start)
        _seed_bookmark(session, bookmark_id=2, user_id=1, created_at=_CURRENT.start)
        session.commit()
    _runner(migrated_engine).run_step()
    later = _NOW + timedelta(seconds=1)
    with Session(migrated_engine) as session:
        session.execute(
            text(
                "UPDATE bookmark_stats_projection_state SET status='running', "
                "checkpoint_user_id=NULL, checkpoint_window_start=NULL, "
                "baseline_completed_at=NULL, "
                "updated_at=:now WHERE id=1"
            ),
            {"now": later.strftime("%Y-%m-%dT%H:%M:%S.%fZ")},
        )
        session.commit()

    assert _runner(migrated_engine, now=later).run_step().active is True
    with Session(migrated_engine) as session:
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_point")).scalar_one()
            == 1
        )
        assert session.execute(
            text("SELECT calculated_at FROM bookmark_stats_window_working")
        ).scalar_one() == later.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def test_same_version_changed_closed_root_is_left_immutable_for_later_dirty_correction(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session, 1)
        _seed_bookmark(session, bookmark_id=1, user_id=1, created_at=_CLOSED.start)
        session.commit()
    _runner(migrated_engine).run_step()
    with Session(migrated_engine) as session:
        before = session.execute(
            text("SELECT payload FROM bookmark_stats_window_point")
        ).scalar_one()
        _seed_bookmark(
            session, bookmark_id=2, user_id=1, created_at=_CLOSED.start + timedelta(days=1)
        )
        session.execute(
            text(
                "UPDATE bookmark_stats_projection_state SET status='running', "
                "checkpoint_user_id=NULL, checkpoint_window_start=NULL, baseline_completed_at=NULL "
                "WHERE id=1"
            )
        )
        session.commit()

    _runner(migrated_engine).run_step()
    with Session(migrated_engine) as session:
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_point")).scalar_one()
            == 1
        )
        assert (
            session.execute(text("SELECT payload FROM bookmark_stats_window_point")).scalar_one()
            == before
        )


def test_state_version_mismatch_is_typed_and_does_not_write(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        repository = WeeklyProjectionRepository(session)
        repository.ensure_state("weekly-v1;payload-schema=1;top-tags-limit=4", _NOW)
        session.commit()

    with pytest.raises(ProjectionCalculationVersionMismatchError):
        _runner(migrated_engine).run_step()
    with Session(migrated_engine) as session:
        assert _state(session)[0:2] == ("pending", "weekly-v1;payload-schema=1;top-tags-limit=4")


def test_repository_state_failure_and_candidate_limit_validation(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        repository = WeeklyProjectionRepository(session)
        assert repository.start_or_resume(_RUNTIME_VERSION, _NOW).status.value == "running"
        assert repository.fail(_RUNTIME_VERSION, "baseline_failed", _NOW).status.value == "failed"
        with pytest.raises(ProjectionStateTransitionError, match="failed"):
            repository.start_or_resume(_RUNTIME_VERSION, _NOW)
        with pytest.raises(TypeError, match="limit must be an integer"):
            repository.surviving_candidates_after(None, True)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="between 1 and 101"):
            repository.surviving_candidates_after(None, 102)
        with pytest.raises(ValueError, match="sanitized"):
            repository.fail(_RUNTIME_VERSION, "unsafe-code!", _NOW)
        session.rollback()


def test_future_candidate_rolls_back_state_and_projection_writes(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session, 1)
        _seed_bookmark(session, bookmark_id=1, user_id=1, created_at=_NOW + timedelta(days=7))
        session.commit()

    with pytest.raises(ProjectionCandidateError, match="future"):
        _runner(migrated_engine).run_step()
    with Session(migrated_engine) as session:
        assert (
            session.execute(
                text("SELECT count(*) FROM bookmark_stats_projection_state")
            ).scalar_one()
            == 0
        )
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_point")).scalar_one()
            == 0
        )
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_working")).scalar_one()
            == 0
        )


def test_baseline_leaves_dirty_marker_untouched_and_keeps_unicode_payload(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session, 1)
        _seed_bookmark(session, bookmark_id=1, user_id=1, created_at=_CLOSED.start)
        session.execute(text("INSERT INTO tags (id, name) VALUES (1, 'café')"))
        session.execute(text("INSERT INTO bookmark_tags (bookmark_id, tag_id) VALUES (1, 1)"))
        session.execute(
            text(
                "INSERT INTO bookmark_stats_window_dirty "
                "(user_id, window_start, generation, reason, first_marked_at, last_marked_at) "
                "VALUES (1, :start, 1, 'create', :now, :now)"
            ),
            {
                "start": _CLOSED.start.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "now": _NOW.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            },
        )
        session.commit()

    _runner(migrated_engine).run_step()
    with Session(migrated_engine) as session:
        assert (
            session.execute(text("SELECT generation FROM bookmark_stats_window_dirty")).scalar_one()
            == 1
        )
        payload = session.execute(
            text("SELECT payload FROM bookmark_stats_window_point")
        ).scalar_one()
        assert json.loads(payload)["stats"]["top_tags"] == [{"count": 1, "name": "café"}]


class _FailingReader:
    calculation_version = _RUNTIME_VERSION

    def __init__(self, _session: Session, _top_tags_limit: int) -> None:
        pass

    def read(self, _user_id: int, _window: object) -> object:
        raise RuntimeError("calculation dependency failed")


class _CommitFailingSession(Session):
    closed_for_test = False

    def commit(self) -> None:
        raise RuntimeError("commit dependency failed")

    def close(self) -> None:
        self.closed_for_test = True
        super().close()


def test_dependency_or_commit_failure_rolls_back_and_closes_session(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session, 1)
        _seed_bookmark(session, bookmark_id=1, user_id=1, created_at=_CLOSED.start)
        session.commit()

    with pytest.raises(RuntimeError, match="calculation dependency"):
        _runner(migrated_engine, reader_factory=_FailingReader).run_step()  # type: ignore[arg-type]
    with Session(migrated_engine) as session:
        assert (
            session.execute(
                text("SELECT count(*) FROM bookmark_stats_projection_state")
            ).scalar_one()
            == 0
        )

    failing_session = _CommitFailingSession(migrated_engine)
    with pytest.raises(RuntimeError, match="commit dependency"):
        _runner(
            migrated_engine,
            session_factory=lambda: failing_session,
        ).run_step()
    assert failing_session.closed_for_test is True
    with Session(migrated_engine) as session:
        assert (
            session.execute(
                text("SELECT count(*) FROM bookmark_stats_projection_state")
            ).scalar_one()
            == 0
        )
