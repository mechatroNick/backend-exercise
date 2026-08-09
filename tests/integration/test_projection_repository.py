"""Migrated-SQLite repository behavior for private weekly projections."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlmodel import Session

from app.bookmarks.stats import projection_repository as projection_module
from app.bookmarks.stats.projection_repository import (
    CorrectionReason,
    NewProjectionPoint,
    WeeklyProjectionRepository,
    WorkingProjectionRecord,
)
from app.bookmarks.stats.weekly import WeeklyWindow

_NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)
_WINDOW = WeeklyWindow.from_datetime(datetime(2026, 8, 5, tzinfo=UTC))
_NEXT_WINDOW = WeeklyWindow.from_datetime(datetime(2026, 8, 12, tzinfo=UTC))
_HASH_A = "a" * 64
_HASH_B = "b" * 64


def _seed_users(session: Session) -> None:
    for user_id in (1, 2):
        session.execute(
            text(
                "INSERT INTO users (id, username, email, password_hash, created_at) "
                "VALUES (:id, :username, :email, 'hash', :created_at)"
            ),
            {
                "id": user_id,
                "username": f"user-{user_id}",
                "email": f"user-{user_id}@example.test",
                "created_at": "2026-08-01T00:00:00.000000Z",
            },
        )


def _working(
    *, user_id: int = 1, window: WeeklyWindow = _WINDOW, payload: bytes = b'{"schema_version":1}'
) -> WorkingProjectionRecord:
    return WorkingProjectionRecord(
        user_id=user_id,
        window=window,
        payload=payload,
        calculated_at=_NOW,
        source_generation=2,
        calculation_version="weekly-v1;payload-schema=1;top-tags-limit=5",
        content_hash=_HASH_A,
    )


def _point(
    *,
    revision: int = 1,
    supersedes_id: int | None = None,
    user_id: int = 1,
    window: WeeklyWindow = _WINDOW,
    payload: bytes = b'{"schema_version":1}',
    content_hash: str = _HASH_A,
) -> NewProjectionPoint:
    return NewProjectionPoint(
        user_id=user_id,
        window=window,
        revision=revision,
        supersedes_id=supersedes_id,
        payload=payload,
        calculated_at=_NOW,
        developed_at=_NOW + timedelta(seconds=1),
        correction_reason=None if revision == 1 else CorrectionReason.LATE_RECALCULATION,
        source_generation=2,
        calculation_version="weekly-v1;payload-schema=1;top-tags-limit=5",
        content_hash=content_hash,
    )


def test_replace_working_observe_overdue_is_bounded_and_caller_transaction_owned(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_users(session)
        repository = WeeklyProjectionRepository(session)
        repository.replace_working(
            _working(payload=b'{"schema_version":1,"stats":{"total_bookmarks":1}}')
        )
        repository.replace_working(
            _working(payload=b'{"schema_version":1,"stats":{"total_bookmarks":2}}')
        )
        repository.replace_working(_working(user_id=2, window=_NEXT_WINDOW))
        assert repository.get_working(1, _WINDOW).payload.endswith(b"2}}")  # type: ignore[union-attr]
        assert repository.observe_overdue(_NOW, limit=1) == (repository.get_working(1, _WINDOW),)
        session.rollback()
        assert repository.get_working(1, _WINDOW) is None
        with pytest.raises(ValueError, match="between 1 and 100"):
            repository.observe_overdue(_NOW, limit=101)


def test_append_only_effective_revision_preserves_a_b_a_history_and_owner_scope(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_users(session)
        repository = WeeklyProjectionRepository(session)
        root = repository.append_point(_point())
        correction = repository.append_point(
            _point(revision=2, supersedes_id=root.id, content_hash=_HASH_B)
        )
        latest = repository.append_point(
            _point(revision=3, supersedes_id=correction.id, content_hash=_HASH_A)
        )
        session.commit()

        assert repository.effective_point(1, _WINDOW) == latest
        assert repository.effective_point(2, _WINDOW) is None
        rows = session.execute(
            text(
                "SELECT revision, content_hash FROM bookmark_stats_window_point "
                "WHERE user_id=1 AND window_start=:start ORDER BY revision"
            ),
            {"start": "2026-08-03T00:00:00.000000Z"},
        ).all()
        assert rows == [(1, _HASH_A), (2, _HASH_B), (3, _HASH_A)]


def test_append_rejects_nonroot_skips_mismatched_predecessor_and_never_updates_old_rows(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_users(session)
        repository = WeeklyProjectionRepository(session)
        with pytest.raises(ValueError, match="existing effective"):
            repository.append_point(_point(revision=2, supersedes_id=1))
        root = repository.append_point(_point())
        with pytest.raises(ValueError, match="root revision"):
            repository.append_point(_point())
        with pytest.raises(ValueError, match="immediately supersede"):
            repository.append_point(_point(revision=3, supersedes_id=root.id, content_hash=_HASH_B))
        with pytest.raises(ValueError, match="immediately supersede"):
            repository.append_point(
                _point(revision=2, supersedes_id=root.id + 100, content_hash=_HASH_B)
            )
        with pytest.raises(ValueError, match="existing effective"):
            repository.append_point(_point(revision=2, supersedes_id=root.id, user_id=2))
        with pytest.raises(ValueError, match="CorrectionReason"):
            repository.append_point(
                _point(revision=2, supersedes_id=root.id).model_copy(
                    update={"correction_reason": None}
                )
            )
        session.flush()
        assert session.execute(
            text("SELECT revision, content_hash FROM bookmark_stats_window_point WHERE id=:id"),
            {"id": root.id},
        ).one() == (1, _HASH_A)


def test_repository_rejects_invalid_records_before_sql(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        repository = WeeklyProjectionRepository(session)
        with pytest.raises(ValueError, match="positive integer"):
            repository.replace_working(_working(user_id=0))
        with pytest.raises(ValueError, match="lowercase SHA-256"):
            repository.replace_working(_working().model_copy(update={"content_hash": "A" * 64}))
        with pytest.raises(ValueError, match="revision 1"):
            repository.append_point(
                _point().model_copy(update={"correction_reason": "late_change"})
            )
        with pytest.raises(ValueError, match="developed_at"):
            repository.append_point(
                _point().model_copy(update={"developed_at": _NOW - timedelta(seconds=1)})
            )
        with pytest.raises(ValueError, match="nonnegative integer"):
            repository.replace_working(_working().model_copy(update={"source_generation": -1}))
        with pytest.raises(ValueError, match="nonempty string"):
            repository.replace_working(_working().model_copy(update={"calculation_version": ""}))
        with pytest.raises(ValueError, match="nonempty bytes"):
            repository.replace_working(_working().model_copy(update={"payload": b""}))
        with pytest.raises(ValueError, match="UTF-8"):
            repository.replace_working(_working().model_copy(update={"payload": b"\xff"}))
        with pytest.raises(ValueError, match="supersede"):
            repository.append_point(_point(revision=2, supersedes_id=None))
        with pytest.raises(TypeError, match="limit must be an integer"):
            repository.observe_overdue(_NOW, limit=True)
        with pytest.raises(TypeError, match="now must be a datetime"):
            repository.observe_overdue("not-a-datetime")  # type: ignore[arg-type]


def test_repository_defensively_rejects_malformed_persisted_values() -> None:
    with pytest.raises(TypeError, match="UTC timestamp string"):
        projection_module._decoded(None, "window_start")
    with pytest.raises(ValueError, match="not canonical UTC"):
        projection_module._decoded("not-a-time", "window_start")


class _NoRowResult:
    def mappings(self) -> _NoRowResult:
        return self

    def one_or_none(self) -> None:
        return None


class _NoIdResult:
    lastrowid = None


class _NoIdSession:
    def __init__(self) -> None:
        self._calls = 0

    def execute(self, _statement: object, _parameters: object) -> _NoRowResult | _NoIdResult:
        self._calls += 1
        return _NoRowResult() if self._calls == 1 else _NoIdResult()


def test_append_surfaces_a_driver_that_cannot_return_inserted_identifier() -> None:
    repository = WeeklyProjectionRepository(_NoIdSession())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="did not return an identifier"):
        repository.append_point(_point())
