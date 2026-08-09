"""Migrated-SQLite constraints for private weekly projection persistence."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

_START = "2026-08-03T00:00:00.000000Z"
_END = "2026-08-10T00:00:00.000000Z"
_CALCULATED = "2026-08-06T12:00:00.000000Z"
_HASH_A = "a" * 64
_HASH_B = "b" * 64


def _seed_user(session: Session, user_id: int = 1) -> None:
    session.execute(
        text(
            "INSERT INTO users (id, username, email, password_hash, created_at) "
            "VALUES (:id, :username, :email, 'hash', :created_at)"
        ),
        {
            "id": user_id,
            "username": f"user-{user_id}",
            "email": f"user-{user_id}@example.test",
            "created_at": _CALCULATED,
        },
    )


def _point_parameters(**overrides: object) -> dict[str, object]:
    return {
        "id": 1,
        "user_id": 1,
        "window_start": _START,
        "window_end": _END,
        "revision": 1,
        "supersedes_id": None,
        "payload": '{"schema":1}',
        "calculated_at": _CALCULATED,
        "developed_at": _CALCULATED,
        "correction_reason": None,
        "source_generation": 0,
        "calculation_version": "weekly-v1",
        "content_hash": _HASH_A,
    } | overrides


_INSERT_POINT = text(
    "INSERT INTO bookmark_stats_window_point "
    "(id, user_id, window_start, window_end, revision, supersedes_id, payload, calculated_at, "
    "developed_at, correction_reason, source_generation, calculation_version, content_hash) "
    "VALUES (:id, :user_id, :window_start, :window_end, :revision, :supersedes_id, :payload, "
    ":calculated_at, :developed_at, :correction_reason, :source_generation, "
    ":calculation_version, :content_hash)"
)


def test_projection_working_and_state_constraints(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session)
        session.execute(
            text(
                "INSERT INTO bookmark_stats_window_working "
                "(user_id, window_start, window_end, payload, calculated_at, source_generation, "
                "calculation_version, content_hash) VALUES "
                "(1, :start, :end, :payload, :calculated, 0, 'weekly-v1', :hash)"
            ),
            {
                "start": _START,
                "end": _END,
                "payload": '{"schema":1}',
                "calculated": _CALCULATED,
                "hash": _HASH_A,
            },
        )
        session.execute(
            text(
                "INSERT INTO bookmark_stats_projection_state "
                "(id, status, calculation_version, checkpoint_user_id, checkpoint_window_start, "
                "baseline_started_at, baseline_completed_at, updated_at, "
                "last_projection_success_at, "
                "failure_code) VALUES "
                "(1, 'pending', 'weekly-v1', NULL, NULL, NULL, NULL, :updated, NULL, NULL)"
            ),
            {"updated": _CALCULATED},
        )
        session.commit()

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO bookmark_stats_window_working "
                    "(user_id, window_start, window_end, payload, calculated_at, "
                    "source_generation, "
                    "calculation_version, content_hash) VALUES "
                    "(1, :start, '2026-08-17T00:00:00.000000Z', :payload, :calculated, "
                    "0, 'weekly-v1', :hash)"
                ),
                {
                    "start": _START,
                    "payload": '{"schema":1}',
                    "calculated": _CALCULATED,
                    "hash": _HASH_A,
                },
            )
        session.rollback()

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO bookmark_stats_window_working "
                    "(user_id, window_start, window_end, payload, calculated_at, "
                    "source_generation, "
                    "calculation_version, content_hash) VALUES "
                    "(1, :start, :end, :payload, :calculated, 0, '', :hash)"
                ),
                {
                    "start": _START,
                    "end": _END,
                    "payload": '{"schema":1}',
                    "calculated": _CALCULATED,
                    "hash": _HASH_A,
                },
            )
        session.rollback()

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO bookmark_stats_projection_state "
                    "(id, status, calculation_version, updated_at) "
                    "VALUES (2, 'pending', 'weekly-v1', :updated)"
                ),
                {"updated": _CALCULATED},
            )
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(
                text("UPDATE bookmark_stats_projection_state SET status = 'unknown' WHERE id = 1")
            )
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "UPDATE bookmark_stats_projection_state SET checkpoint_user_id = 1 WHERE id = 1"
                )
            )
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "UPDATE bookmark_stats_projection_state "
                    "SET checkpoint_user_id = 1, "
                    "checkpoint_window_start = '2026-08-04T00:00:00.000000Z' WHERE id = 1"
                )
            )
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "UPDATE bookmark_stats_projection_state "
                    "SET baseline_started_at = '2026-08-06T12:00:00.000000Z', "
                    "baseline_completed_at = '2026-08-06T11:59:59.000000Z' WHERE id = 1"
                )
            )
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "UPDATE bookmark_stats_projection_state SET failure_code = 'unsafe-code!' "
                    "WHERE id = 1"
                )
            )


def test_point_same_window_supersession_no_branch_and_a_b_a_history(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session)
        session.execute(_INSERT_POINT, _point_parameters())
        session.execute(
            _INSERT_POINT,
            _point_parameters(
                id=2,
                revision=2,
                supersedes_id=1,
                correction_reason="late_recalculation",
                content_hash=_HASH_B,
            ),
        )
        session.execute(
            _INSERT_POINT,
            _point_parameters(
                id=3,
                revision=3,
                supersedes_id=2,
                correction_reason="late_recalculation",
                content_hash=_HASH_A,
            ),
        )
        session.commit()

        with pytest.raises(IntegrityError):
            session.execute(
                _INSERT_POINT,
                _point_parameters(
                    id=4,
                    revision=4,
                    supersedes_id=2,
                    correction_reason="late_recalculation",
                    content_hash=_HASH_B,
                ),
            )
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(
                _INSERT_POINT,
                _point_parameters(
                    id=4,
                    revision=4,
                    supersedes_id=3,
                    window_start="2026-08-10T00:00:00.000000Z",
                    window_end="2026-08-17T00:00:00.000000Z",
                    correction_reason="late_recalculation",
                    content_hash=_HASH_B,
                ),
            )
        session.rollback()

        session.execute(text("DELETE FROM users WHERE id = 1"))
        session.commit()
        assert (
            session.execute(text("SELECT count(*) FROM bookmark_stats_window_point")).scalar_one()
            == 0
        )
        assert session.execute(text("PRAGMA foreign_key_check")).all() == []


def test_projection_timestamp_window_and_hash_constraints_reject_malformed_data(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session)
        session.commit()
        for values in (
            _point_parameters(window_start="2026-08-04T00:00:00.000000Z"),
            _point_parameters(content_hash="A" * 64),
            _point_parameters(revision=2, supersedes_id=None),
            _point_parameters(revision=1, supersedes_id=1),
        ):
            with pytest.raises(IntegrityError):
                session.execute(_INSERT_POINT, values)
            session.rollback()

        session.execute(_INSERT_POINT, _point_parameters())
        session.commit()
        with pytest.raises(IntegrityError):
            session.execute(
                _INSERT_POINT,
                _point_parameters(
                    id=2,
                    revision=2,
                    supersedes_id=1,
                    correction_reason="unbounded_external_value",
                    content_hash=_HASH_B,
                ),
            )
        session.rollback()


def test_user_deletion_cascades_every_user_scoped_projection_row(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_user(session)
        session.execute(
            text(
                "INSERT INTO bookmark_stats_window_dirty "
                "(user_id, window_start, generation, reason, first_marked_at, last_marked_at) "
                "VALUES (1, :start, 1, 'create', :marked, :marked)"
            ),
            {"start": _START, "marked": _CALCULATED},
        )
        session.execute(
            text(
                "INSERT INTO bookmark_stats_window_working "
                "(user_id, window_start, window_end, payload, calculated_at, source_generation, "
                "calculation_version, content_hash) VALUES "
                "(1, :start, :end, :payload, :calculated, 0, 'weekly-v1', :hash)"
            ),
            {
                "start": _START,
                "end": _END,
                "payload": '{"schema":1}',
                "calculated": _CALCULATED,
                "hash": _HASH_A,
            },
        )
        session.execute(_INSERT_POINT, _point_parameters())
        session.commit()

        session.execute(text("DELETE FROM users WHERE id = 1"))
        session.commit()

        for table in (
            "bookmark_stats_window_dirty",
            "bookmark_stats_window_working",
            "bookmark_stats_window_point",
        ):
            assert session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
        assert session.execute(text("PRAGMA foreign_key_check")).all() == []
