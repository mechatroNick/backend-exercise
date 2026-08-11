"""Caller-session-owned durable statistics invalidation markers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, cast

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    text,
)
from sqlalchemy.engine import CursorResult
from sqlmodel import Field, Session, SQLModel

from app.core.internal_models import FrozenInternalModel
from app.db.types import UTCDateTime

_UTC_TEXT_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class DirtyReason(StrEnum):
    """Low-cardinality causes permitted in durable invalidation state."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    RECONCILE = "reconcile"


class BookmarkStatsWindowDirty(SQLModel, table=True):
    """Durable per-user/week invalidation with separate current and projection completion."""

    __tablename__ = "bookmark_stats_window_dirty"  # pyright: ignore[reportAssignmentType] -- SQLModel metaclass
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "window_start", name="pk_stats_dirty_user_window"),
        ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_stats_dirty_user", ondelete="CASCADE"
        ),
        CheckConstraint("generation > 0", name="ck_stats_dirty_generation_positive"),
        CheckConstraint(
            "current_completed_generation >= 0 AND current_completed_generation <= generation",
            name="ck_stats_dirty_current_completion_generation",
        ),
        CheckConstraint(
            "projection_completed_generation >= 0 "
            "AND projection_completed_generation <= generation",
            name="ck_stats_dirty_projection_completion_generation",
        ),
        CheckConstraint(
            "length(reason) > 0 AND length(reason) <= 32", name="ck_stats_dirty_reason_bounded"
        ),
        CheckConstraint(
            "reason IN ('create', 'update', 'delete', 'reconcile')",
            name="ck_stats_dirty_reason_known",
        ),
        CheckConstraint(
            "length(window_start) = 27 "
            "AND substr(window_start, 11) = 'T00:00:00.000000Z' "
            "AND strftime('%w', window_start) = '1'",
            name="ck_stats_dirty_window_monday_utc",
        ),
        CheckConstraint(
            "length(first_marked_at) = 27 AND substr(first_marked_at, 27, 1) = 'Z'",
            name="ck_stats_dirty_first_marked_utc",
        ),
        CheckConstraint(
            "length(last_marked_at) = 27 AND substr(last_marked_at, 27, 1) = 'Z'",
            name="ck_stats_dirty_last_marked_utc",
        ),
        Index("ix_stats_dirty_window_user", "window_start", "user_id"),
        Index(
            "ix_stats_dirty_last_marked_user_window",
            "last_marked_at",
            "user_id",
            "window_start",
        ),
    )
    user_id: int = Field(sa_column=Column(Integer, nullable=False, primary_key=True))
    window_start: datetime = Field(
        sa_column=Column(UTCDateTime(), nullable=False, primary_key=True)
    )
    generation: int = Field(sa_column=Column(Integer, nullable=False))
    current_completed_generation: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    projection_completed_generation: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    reason: str = Field(sa_column=Column(String(32), nullable=False))
    first_marked_at: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))
    last_marked_at: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))


def _positive(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


def utc_monday(value: datetime) -> datetime:
    """Normalize an aware timestamp to its UTC Monday midnight window."""
    value = _utc(value)
    return (value - timedelta(days=value.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


class DirtyMarker(FrozenInternalModel):
    """One observed dirty generation that remains pending until both consumers complete it."""

    user_id: int
    window_start: datetime
    generation: int
    current_completed_generation: int
    projection_completed_generation: int
    reason: DirtyReason
    first_marked_at: datetime
    last_marked_at: datetime


class DirtyBacklog(FrozenInternalModel):
    """Identifier-free durable-work count and age for readiness evaluation."""

    count: int
    oldest_marked_at: datetime | None


class DirtyAcknowledgementStatus(StrEnum):
    """The durable outcome of one guarded consumer acknowledgement."""

    STALE = "stale"
    ACKNOWLEDGED = "acknowledged"
    DELETED = "deleted"


class DirtyAcknowledgement(FrozenInternalModel):
    """A precise outcome for a generation-guarded acknowledgement attempt."""

    status: DirtyAcknowledgementStatus


def _encoded(value: datetime) -> str:
    return _utc(value).strftime(_UTC_TEXT_FORMAT)


def _decoded(value: str) -> datetime:
    try:
        return datetime.strptime(value, _UTC_TEXT_FORMAT).replace(tzinfo=UTC)
    except ValueError as error:
        raise ValueError("persisted dirty timestamp is not canonical UTC") from error


def _marker(row: dict[str, Any]) -> DirtyMarker:
    window_start = _decoded(row["window_start"])
    if window_start != utc_monday(window_start):
        raise ValueError("persisted dirty window is not UTC Monday midnight")
    return DirtyMarker(
        user_id=_positive(row["user_id"], "persisted user_id"),
        window_start=window_start,
        generation=_positive(row["generation"], "persisted generation"),
        current_completed_generation=_nonnegative(
            row["current_completed_generation"], "persisted current_completed_generation"
        ),
        projection_completed_generation=_nonnegative(
            row["projection_completed_generation"],
            "persisted projection_completed_generation",
        ),
        reason=DirtyReason(row["reason"]),
        first_marked_at=_decoded(row["first_marked_at"]),
        last_marked_at=_decoded(row["last_marked_at"]),
    )


def _nonnegative(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


class BookmarkStatsDirtyRepository:
    """Atomic persistence only; caller owns transaction boundaries and logging."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def mark_dirty(
        self,
        user_id: int,
        window_start: datetime,
        reason: DirtyReason,
        marked_at: datetime,
    ) -> None:
        """Atomically create or advance work inside the caller's canonical mutation transaction."""
        _positive(user_id, "user_id")
        if not isinstance(reason, DirtyReason):
            raise TypeError("reason must be a DirtyReason")
        window, marked = _encoded(utc_monday(window_start)), _encoded(marked_at)
        statement = text(
            "INSERT INTO bookmark_stats_window_dirty "
            "(user_id, window_start, generation, current_completed_generation, "
            "projection_completed_generation, reason, first_marked_at, last_marked_at) "
            "VALUES (:user_id, :window, 1, 0, 0, :reason, :marked, :marked) "
            "ON CONFLICT(user_id, window_start) DO UPDATE SET "
            "generation = generation + 1, reason = excluded.reason, "
            "current_completed_generation = 0, projection_completed_generation = 0, "
            "last_marked_at = excluded.last_marked_at"
        )
        self._session.execute(
            statement, {"user_id": user_id, "window": window, "reason": reason, "marked": marked}
        )

    def observe(self, limit: int = 100) -> tuple[DirtyMarker, ...]:
        """Return one oldest-first bounded page without acknowledging or completing it."""
        _positive(limit, "limit")
        if limit > 100:
            raise ValueError("limit must be at most 100")
        statement = text(
            "SELECT user_id, window_start, generation, current_completed_generation, "
            "projection_completed_generation, reason, first_marked_at, last_marked_at "
            "FROM bookmark_stats_window_dirty "
            "ORDER BY last_marked_at ASC, user_id ASC, window_start ASC LIMIT :limit"
        )
        return tuple(
            _marker(dict(row))
            for row in self._session.execute(statement, {"limit": limit}).mappings()
        )

    def user_ids_after(self, after_id: int = 0, limit: int = 100) -> tuple[int, ...]:
        """Return one bounded, stable page of users for full reconciliation."""
        if isinstance(after_id, bool) or not isinstance(after_id, int) or after_id < 0:
            raise ValueError("after_id must be a nonnegative integer")
        _positive(limit, "limit")
        if limit > 100:
            raise ValueError("limit must be at most 100")
        rows = self._session.execute(
            text("SELECT id FROM users WHERE id > :after_id ORDER BY id ASC LIMIT :limit"),
            {"after_id": after_id, "limit": limit},
        )
        return tuple(_positive(row[0], "persisted user_id") for row in rows)

    def backlog(self) -> DirtyBacklog:
        """Return identifier-free durable backlog facts without changing transaction state."""
        row = (
            self._session.execute(
                text(
                    "SELECT count(*) AS count, min(first_marked_at) AS oldest_marked_at "
                    "FROM bookmark_stats_window_dirty"
                )
            )
            .mappings()
            .one()
        )
        return DirtyBacklog(
            count=row["count"],
            oldest_marked_at=None
            if row["oldest_marked_at"] is None
            else _decoded(row["oldest_marked_at"]),
        )

    def acknowledge_current(
        self, user_id: int, window_start: datetime, generation: int
    ) -> DirtyAcknowledgement:
        """Durably acknowledge current work without deleting pending projection work."""
        return self._acknowledge("current_completed_generation", user_id, window_start, generation)

    def acknowledge_projection(
        self, user_id: int, window_start: datetime, generation: int
    ) -> DirtyAcknowledgement:
        """Durably acknowledge projection work and delete only fully acknowledged work."""
        return self._acknowledge(
            "projection_completed_generation", user_id, window_start, generation
        )

    def _acknowledge(
        self,
        completion_column: str,
        user_id: int,
        window_start: datetime,
        generation: int,
    ) -> DirtyAcknowledgement:
        _positive(user_id, "user_id")
        _positive(generation, "generation")
        window = _encoded(utc_monday(window_start))
        parameters = {"user_id": user_id, "window": window, "generation": generation}
        acknowledged = cast(
            CursorResult[Any],
            self._session.execute(
                text(
                    "UPDATE bookmark_stats_window_dirty "
                    f"SET {completion_column}=:generation "
                    "WHERE user_id=:user_id AND window_start=:window AND generation=:generation"
                ),
                parameters,
            ),
        )
        if acknowledged.rowcount != 1:
            return DirtyAcknowledgement(status=DirtyAcknowledgementStatus.STALE)
        deleted = cast(
            CursorResult[Any],
            self._session.execute(
                text(
                    "DELETE FROM bookmark_stats_window_dirty WHERE user_id=:user_id "
                    "AND window_start=:window AND generation=:generation "
                    "AND current_completed_generation=:generation "
                    "AND projection_completed_generation=:generation"
                ),
                parameters,
            ),
        )
        return DirtyAcknowledgement(
            status=(
                DirtyAcknowledgementStatus.DELETED
                if deleted.rowcount == 1
                else DirtyAcknowledgementStatus.ACKNOWLEDGED
            )
        )


__all__ = [
    "BookmarkStatsDirtyRepository",
    "BookmarkStatsWindowDirty",
    "DirtyAcknowledgement",
    "DirtyAcknowledgementStatus",
    "DirtyBacklog",
    "DirtyMarker",
    "DirtyReason",
    "utc_monday",
]
