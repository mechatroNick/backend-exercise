"""Migrated-SQLite evidence for durable current-statistics invalidation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from alembic.config import Config
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from alembic import command
from app.bookmarks.stats.dirty import (
    BookmarkStatsDirtyRepository,
    DirtyAcknowledgementStatus,
    DirtyReason,
    utc_monday,
)
from app.db.engine import create_database_engine


def _insert_users(session: Session, moment: datetime) -> None:
    session.execute(
        text(
            "INSERT INTO users (id, username, email, password_hash, created_at) "
            "VALUES (1, 'one', 'one@example.test', 'hash', :created), "
            "(2, 'two', 'two@example.test', 'hash', :created)"
        ),
        {"created": moment.isoformat().replace("+00:00", "Z")},
    )


def test_atomic_upsert_preserves_first_mark_and_updates_generation(
    migrated_engine: Engine,
) -> None:
    first = datetime(2026, 8, 6, 12, tzinfo=UTC)
    second = first + timedelta(minutes=1)
    with Session(migrated_engine) as session:
        _insert_users(session, first)
        session.commit()
        repository = BookmarkStatsDirtyRepository(session)

        repository.mark_dirty(1, first, DirtyReason.CREATE, first)
        repository.mark_dirty(1, first + timedelta(days=1), DirtyReason.UPDATE, second)
        session.commit()

        marker = repository.observe()[0]
        assert marker.user_id == 1
        assert marker.window_start == datetime(2026, 8, 3, tzinfo=UTC)
        assert marker.generation == 2
        assert marker.reason is DirtyReason.UPDATE
        assert marker.first_marked_at == first
        assert marker.last_marked_at == second
        assert marker.current_completed_generation == 0
        assert marker.projection_completed_generation == 0


def test_two_consumer_acknowledgements_delete_only_after_both_and_reset_on_increment(
    migrated_engine: Engine,
) -> None:
    moment = datetime(2026, 8, 6, 12, tzinfo=UTC)
    with Session(migrated_engine) as session:
        _insert_users(session, moment)
        repository = BookmarkStatsDirtyRepository(session)
        repository.mark_dirty(1, moment, DirtyReason.CREATE, moment)
        repository.mark_dirty(2, moment, DirtyReason.CREATE, moment)
        session.commit()

        assert (
            repository.acknowledge_projection(2, moment, 1).status
            is DirtyAcknowledgementStatus.ACKNOWLEDGED
        )
        assert (
            repository.acknowledge_current(2, moment, 1).status
            is DirtyAcknowledgementStatus.DELETED
        )
        session.commit()
        marker = repository.observe()[0]
        assert marker.user_id == 1
        assert (
            repository.acknowledge_current(1, moment, 1).status
            is DirtyAcknowledgementStatus.ACKNOWLEDGED
        )
        session.commit()
        marker = repository.observe()[0]
        assert (marker.current_completed_generation, marker.projection_completed_generation) == (
            1,
            0,
        )

        repository.mark_dirty(1, moment, DirtyReason.UPDATE, moment + timedelta(seconds=1))
        session.commit()
        marker = repository.observe()[0]
        assert (
            marker.generation,
            marker.current_completed_generation,
            marker.projection_completed_generation,
        ) == (
            2,
            0,
            0,
        )
        assert (
            repository.acknowledge_projection(1, moment, 2).status
            is DirtyAcknowledgementStatus.ACKNOWLEDGED
        )
        assert (
            repository.acknowledge_current(1, moment, 2).status
            is DirtyAcknowledgementStatus.DELETED
        )
        session.commit()
        assert repository.backlog().count == 0


def test_current_acknowledgement_rolls_back_with_caller_transaction(
    migrated_engine: Engine,
) -> None:
    moment = datetime(2026, 8, 6, 12, tzinfo=UTC)
    with Session(migrated_engine) as session:
        _insert_users(session, moment)
        repository = BookmarkStatsDirtyRepository(session)
        repository.mark_dirty(1, moment, DirtyReason.CREATE, moment)
        session.commit()

        assert (
            repository.acknowledge_current(1, moment, 1).status
            is DirtyAcknowledgementStatus.ACKNOWLEDGED
        )
        session.rollback()
        marker = repository.observe()[0]
        assert (marker.current_completed_generation, marker.projection_completed_generation) == (
            0,
            0,
        )


def test_observation_backlog_bounds_order_and_generation_completion(
    migrated_engine: Engine,
) -> None:
    moment = datetime(2026, 8, 6, 12, tzinfo=UTC)
    prior_window = moment - timedelta(days=7)
    with Session(migrated_engine) as session:
        _insert_users(session, moment)
        session.commit()
        repository = BookmarkStatsDirtyRepository(session)
        repository.mark_dirty(1, moment, DirtyReason.UPDATE, moment + timedelta(minutes=2))
        repository.mark_dirty(2, moment, DirtyReason.DELETE, moment)
        repository.mark_dirty(1, prior_window, DirtyReason.RECONCILE, moment + timedelta(minutes=1))
        session.commit()

        observed = repository.observe(limit=2)
        assert [(item.user_id, item.window_start) for item in observed] == [
            (2, datetime(2026, 8, 3, tzinfo=UTC)),
            (1, datetime(2026, 7, 27, tzinfo=UTC)),
        ]
        assert repository.backlog().count == 3
        assert repository.backlog().oldest_marked_at == moment

        assert (
            repository.acknowledge_current(2, moment, generation=2).status
            is DirtyAcknowledgementStatus.STALE
        )
        session.commit()
        assert repository.backlog().count == 3
        assert (
            repository.acknowledge_current(2, moment, generation=1).status
            is DirtyAcknowledgementStatus.ACKNOWLEDGED
        )
        session.commit()
        assert repository.backlog().count == 3
        assert (
            repository.acknowledge_projection(2, moment, generation=1).status
            is DirtyAcknowledgementStatus.DELETED
        )
        session.commit()
        assert repository.backlog().count == 2


def test_full_reconciliation_user_cursor_is_bounded_and_stable(
    migrated_engine: Engine,
) -> None:
    moment = datetime(2026, 8, 6, 12, tzinfo=UTC)
    with Session(migrated_engine) as session:
        _insert_users(session, moment)
        session.commit()
        repository = BookmarkStatsDirtyRepository(session)

        assert repository.user_ids_after(limit=1) == (1,)
        assert repository.user_ids_after(after_id=1, limit=1) == (2,)
        assert repository.user_ids_after(after_id=2, limit=1) == ()
        for after_id in (-1, True, "1"):
            with pytest.raises(ValueError, match="after_id"):
                repository.user_ids_after(after_id=after_id)  # type: ignore[arg-type]
        for limit in (0, -1, True, 101):
            with pytest.raises(ValueError, match="limit"):
                repository.user_ids_after(limit=limit)


def test_fixed_width_timestamp_ordering_handles_fractional_seconds(
    migrated_engine: Engine,
) -> None:
    whole = datetime(2026, 8, 6, 12, tzinfo=UTC)
    fractional = whole.replace(microsecond=500_000)
    with Session(migrated_engine) as session:
        _insert_users(session, whole)
        session.commit()
        repository = BookmarkStatsDirtyRepository(session)
        repository.mark_dirty(1, whole, DirtyReason.CREATE, whole)
        repository.mark_dirty(2, whole, DirtyReason.CREATE, fractional)
        session.commit()

        assert [marker.user_id for marker in repository.observe()] == [1, 2]
        assert repository.backlog().oldest_marked_at == whole
        persisted = session.execute(
            text("SELECT first_marked_at FROM bookmark_stats_window_dirty ORDER BY user_id")
        ).scalars()
        assert [len(value) for value in persisted] == [27, 27]


def test_dirty_query_shapes_use_the_declared_indexes(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        user_plan = connection.execute(
            text(
                "EXPLAIN QUERY PLAN SELECT generation "
                "FROM bookmark_stats_window_dirty "
                "WHERE user_id = 1 AND window_start = '2026-08-03T00:00:00.000000Z'"
            )
        ).all()
        window_plan = connection.execute(
            text(
                "EXPLAIN QUERY PLAN SELECT user_id "
                "FROM bookmark_stats_window_dirty WHERE window_start = "
                "'2026-08-03T00:00:00.000000Z'"
            )
        ).all()
        ordered_plan = connection.execute(
            text(
                "EXPLAIN QUERY PLAN SELECT user_id, window_start "
                "FROM bookmark_stats_window_dirty "
                "ORDER BY last_marked_at, user_id, window_start LIMIT 100"
            )
        ).all()

    assert "sqlite_autoindex_bookmark_stats_window_dirty_1" in user_plan[0][3]
    assert "ix_stats_dirty_window_user" in window_plan[0][3]
    assert "ix_stats_dirty_last_marked_user_window" in ordered_plan[0][3]


def test_marker_participates_in_caller_rollback(migrated_engine: Engine) -> None:
    moment = datetime(2026, 8, 6, 12, tzinfo=UTC)
    with Session(migrated_engine) as session:
        _insert_users(session, moment)
        session.commit()
        BookmarkStatsDirtyRepository(session).mark_dirty(1, moment, DirtyReason.CREATE, moment)
        session.rollback()
        assert BookmarkStatsDirtyRepository(session).backlog().count == 0
        assert session.execute(text("SELECT count(*) FROM users")).scalar_one() == 2


def test_conditional_completion_preserves_concurrent_generation_and_rolls_back(
    migrated_engine: Engine,
) -> None:
    moment = datetime(2026, 8, 6, 12, tzinfo=UTC)
    with Session(migrated_engine) as setup:
        _insert_users(setup, moment)
        repository = BookmarkStatsDirtyRepository(setup)
        repository.mark_dirty(1, moment, DirtyReason.CREATE, moment)
        setup.commit()

    with Session(migrated_engine) as worker:
        observed_generation = BookmarkStatsDirtyRepository(worker).observe()[0].generation
        worker.rollback()
        with Session(migrated_engine) as writer:
            BookmarkStatsDirtyRepository(writer).mark_dirty(
                1,
                moment,
                DirtyReason.UPDATE,
                moment + timedelta(seconds=1),
            )
            writer.commit()

        worker_repository = BookmarkStatsDirtyRepository(worker)
        assert (
            worker_repository.acknowledge_current(1, moment, observed_generation).status
            is DirtyAcknowledgementStatus.STALE
        )
        worker.commit()

    with Session(migrated_engine) as verification:
        marker = BookmarkStatsDirtyRepository(verification).observe()[0]
        assert marker.generation == 2
        assert (
            BookmarkStatsDirtyRepository(verification).acknowledge_current(1, moment, 2).status
            is DirtyAcknowledgementStatus.ACKNOWLEDGED
        )
        verification.rollback()

    with Session(migrated_engine) as after_rollback:
        marker = BookmarkStatsDirtyRepository(after_rollback).observe()[0]
        assert marker.generation == 2


def test_marker_validates_inputs_and_database_constraints(migrated_engine: Engine) -> None:
    moment = datetime(2026, 8, 6, 12, tzinfo=UTC)
    naive = moment.replace(tzinfo=None)
    with Session(migrated_engine) as session:
        _insert_users(session, moment)
        session.commit()
        repository = BookmarkStatsDirtyRepository(session)

        for invalid_user_id in (0, -1, True):
            with pytest.raises(ValueError, match="user_id must be a positive integer"):
                repository.mark_dirty(invalid_user_id, moment, DirtyReason.CREATE, moment)
        with pytest.raises(TypeError, match="reason must be a DirtyReason"):
            repository.mark_dirty(1, moment, "create", moment)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="timestamps must be timezone-aware"):
            repository.mark_dirty(1, naive, DirtyReason.CREATE, moment)
        with pytest.raises(ValueError, match="timestamps must be timezone-aware"):
            repository.mark_dirty(1, moment, DirtyReason.CREATE, naive)
        for invalid_limit in (0, -1, True, 101):
            with pytest.raises(ValueError, match="limit"):
                repository.observe(invalid_limit)
        for invalid_generation in (0, -1, True):
            with pytest.raises(ValueError, match="generation must be a positive integer"):
                repository.acknowledge_current(1, moment, invalid_generation)

        invalid_parameters = {
            "user_id": 1,
            "window": "2026-08-03T00:00:00.000000Z",
            "marked": "2026-08-06T12:00:00.000000Z",
        }
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO bookmark_stats_window_dirty "
                    "(user_id, window_start, generation, reason, first_marked_at, last_marked_at) "
                    "VALUES (:user_id, :window, 0, 'create', :marked, :marked)"
                ),
                invalid_parameters,
            )
        session.rollback()
        malformed_window = {**invalid_parameters, "window": "2026-08-04T00:00:00.000000Z"}
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO bookmark_stats_window_dirty "
                    "(user_id, window_start, generation, reason, first_marked_at, last_marked_at) "
                    "VALUES (:user_id, :window, 1, 'create', :marked, :marked)"
                ),
                malformed_window,
            )
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO bookmark_stats_window_dirty "
                    "(user_id, window_start, generation, reason, first_marked_at, last_marked_at) "
                    "VALUES (:user_id, :window, 1, 'content-derived', :marked, :marked)"
                ),
                invalid_parameters,
            )


def test_observation_fails_closed_for_corrupt_persisted_timestamps(
    migrated_engine: Engine,
) -> None:
    moment = datetime(2026, 8, 6, 12, tzinfo=UTC)
    canonical_marked = "2026-08-06T12:00:00.000000Z"
    insert_corrupt = text(
        "INSERT INTO bookmark_stats_window_dirty "
        "(user_id, window_start, generation, reason, first_marked_at, last_marked_at) "
        "VALUES (1, :window, 1, 'create', :marked, :marked)"
    )
    with Session(migrated_engine) as session:
        _insert_users(session, moment)
        session.commit()
        session.execute(text("PRAGMA ignore_check_constraints = ON"))
        try:
            session.execute(
                insert_corrupt,
                {"window": "not-a-canonical-utc-value", "marked": canonical_marked},
            )
            with pytest.raises(ValueError, match="persisted dirty timestamp"):
                BookmarkStatsDirtyRepository(session).observe()
            session.execute(text("DELETE FROM bookmark_stats_window_dirty"))

            session.execute(
                insert_corrupt,
                {
                    "window": "2026-08-04T00:00:00.000000Z",
                    "marked": canonical_marked,
                },
            )
            with pytest.raises(ValueError, match="persisted dirty window"):
                BookmarkStatsDirtyRepository(session).observe()
            session.execute(text("DELETE FROM bookmark_stats_window_dirty"))

            session.execute(
                insert_corrupt,
                {
                    "window": "2026-08-03T00:00:00.000000Z",
                    "marked": canonical_marked,
                },
            )
            session.execute(
                text("UPDATE bookmark_stats_window_dirty SET current_completed_generation = -1")
            )
            with pytest.raises(ValueError, match="persisted current_completed_generation"):
                BookmarkStatsDirtyRepository(session).observe()
            session.execute(text("DELETE FROM bookmark_stats_window_dirty"))
        finally:
            session.execute(text("PRAGMA ignore_check_constraints = OFF"))
            session.commit()


def test_cascade_and_non_utc_window_normalization(migrated_engine: Engine) -> None:
    local_time = datetime(2026, 8, 10, 1, tzinfo=timezone(timedelta(hours=10)))
    expected_window = datetime(2026, 8, 3, tzinfo=UTC)
    with Session(migrated_engine) as session:
        _insert_users(session, local_time.astimezone(UTC))
        session.commit()
        repository = BookmarkStatsDirtyRepository(session)
        repository.mark_dirty(1, local_time, DirtyReason.CREATE, local_time)
        session.commit()
        assert utc_monday(local_time) == expected_window
        assert repository.observe()[0].window_start == expected_window

        session.execute(text("DELETE FROM users WHERE id = 1"))
        session.commit()
        assert repository.backlog().count == 0


def test_existing_core_upgrade_track06_downgrade_and_reupgrade(
    migration_config: Config,
    database_url: str,
) -> None:
    command.upgrade(migration_config, "0001_core_schema")
    engine = create_database_engine(
        database_url=database_url,
        busy_timeout_milliseconds=4_321,
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id, username, email, password_hash, created_at) "
                    "VALUES (1, 'existing', 'existing@example.test', 'hash', "
                    "'2026-08-01T00:00:00Z')"
                )
            )
    finally:
        engine.dispose()

    command.upgrade(migration_config, "head")
    engine = create_database_engine(
        database_url=database_url,
        busy_timeout_milliseconds=4_321,
    )
    try:
        assert "bookmark_stats_window_dirty" in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 1
    finally:
        engine.dispose()

    command.downgrade(migration_config, "0001_core_schema")
    engine = create_database_engine(
        database_url=database_url,
        busy_timeout_milliseconds=4_321,
    )
    try:
        assert "bookmark_stats_window_dirty" not in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 1
    finally:
        engine.dispose()

    command.upgrade(migration_config, "head")
    command.check(migration_config)


def test_committed_marker_recovers_after_engine_restart(
    migration_config: Config,
    database_url: str,
) -> None:
    command.upgrade(migration_config, "head")
    moment = datetime(2026, 8, 6, 12, tzinfo=UTC)
    first_engine = create_database_engine(
        database_url=database_url,
        busy_timeout_milliseconds=4_321,
    )
    try:
        with Session(first_engine) as session:
            _insert_users(session, moment)
            BookmarkStatsDirtyRepository(session).mark_dirty(1, moment, DirtyReason.CREATE, moment)
            session.commit()
    finally:
        first_engine.dispose()

    second_engine = create_database_engine(
        database_url=database_url,
        busy_timeout_milliseconds=4_321,
    )
    try:
        with Session(second_engine) as session:
            repository = BookmarkStatsDirtyRepository(session)
            recovered = repository.observe()
            assert len(recovered) == 1
            assert recovered[0].generation == 1
            assert (
                repository.acknowledge_current(1, moment, 1).status
                is DirtyAcknowledgementStatus.ACKNOWLEDGED
            )
            assert (
                repository.acknowledge_projection(1, moment, 1).status
                is DirtyAcknowledgementStatus.DELETED
            )
            session.commit()
    finally:
        second_engine.dispose()
