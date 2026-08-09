"""Private SQLModel metadata for weekly event-time projection persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel

from app.db.types import UTCDateTime

_WINDOW_START_CHECK = (
    "length(window_start) = 27 "
    "AND substr(window_start, 11) = 'T00:00:00.000000Z' "
    "AND strftime('%w', window_start) = '1'"
)
_WINDOW_END_CHECK = (
    "length(window_end) = 27 "
    "AND substr(window_end, 11) = 'T00:00:00.000000Z' "
    "AND strftime('%w', window_end) = '1' "
    "AND window_end = strftime('%Y-%m-%dT00:00:00.000000Z', date(window_start, '+7 days'))"
)
_UTC_TIMESTAMP_CHECK = "length({column}) = 27 AND substr({column}, 27, 1) = 'Z'"
_VERSION_CHECK = "length(trim(calculation_version)) > 0 AND length(calculation_version) <= 128"
_HASH_CHECK = "length(content_hash) = 64 AND content_hash NOT GLOB '*[^0-9a-f]*'"


def _monday_check(column: str) -> str:
    return (
        f"length({column}) = 27 "
        f"AND substr({column}, 11) = 'T00:00:00.000000Z' "
        f"AND strftime('%w', {column}) = '1'"
    )


class BookmarkStatsWindowWorking(SQLModel, table=True):
    """One replaceable canonical aggregate for an open UTC week."""

    __tablename__ = "bookmark_stats_window_working"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "window_start", name="pk_stats_working_user_window"),
        ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_stats_working_user", ondelete="CASCADE"
        ),
        CheckConstraint(_WINDOW_START_CHECK, name="ck_stats_working_window_start_monday_utc"),
        CheckConstraint(_WINDOW_END_CHECK, name="ck_stats_working_window_end_one_week"),
        CheckConstraint("length(payload) > 0", name="ck_stats_working_payload_nonempty"),
        CheckConstraint("source_generation >= 0", name="ck_stats_working_source_generation"),
        CheckConstraint(_VERSION_CHECK, name="ck_stats_working_calculation_version"),
        CheckConstraint(_HASH_CHECK, name="ck_stats_working_content_hash"),
        CheckConstraint(
            _UTC_TIMESTAMP_CHECK.format(column="calculated_at"),
            name="ck_stats_working_calculated_at_utc",
        ),
        Index("ix_stats_working_window_end_user", "window_end", "user_id"),
    )

    user_id: int = Field(sa_column=Column(Integer, nullable=False, primary_key=True))
    window_start: datetime = Field(
        sa_column=Column(UTCDateTime(), nullable=False, primary_key=True)
    )
    window_end: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))
    payload: str = Field(sa_column=Column(Text, nullable=False))
    calculated_at: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))
    source_generation: int = Field(sa_column=Column(Integer, nullable=False))
    calculation_version: str = Field(sa_column=Column(String(128), nullable=False))
    content_hash: str = Field(sa_column=Column(String(64), nullable=False))


class BookmarkStatsWindowPoint(SQLModel, table=True):
    """Append-only developed-week revisions with same-window supersession protection."""

    __tablename__ = "bookmark_stats_window_point"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_stats_point"),
        ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_stats_point_user", ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["supersedes_id", "user_id", "window_start"],
            [
                "bookmark_stats_window_point.id",
                "bookmark_stats_window_point.user_id",
                "bookmark_stats_window_point.window_start",
            ],
            name="fk_stats_point_supersedes_same_window",
        ),
        UniqueConstraint(
            "user_id", "window_start", "revision", name="uq_stats_point_user_window_revision"
        ),
        UniqueConstraint("supersedes_id", name="uq_stats_point_supersedes"),
        UniqueConstraint("id", "user_id", "window_start", name="uq_stats_point_id_user_window"),
        CheckConstraint("revision >= 1", name="ck_stats_point_revision_positive"),
        CheckConstraint(
            "(revision = 1 AND supersedes_id IS NULL) "
            "OR (revision > 1 AND supersedes_id IS NOT NULL)",
            name="ck_stats_point_root_iff_revision_one",
        ),
        CheckConstraint(
            "supersedes_id IS NULL OR supersedes_id != id",
            name="ck_stats_point_no_self_supersession",
        ),
        CheckConstraint(_WINDOW_START_CHECK, name="ck_stats_point_window_start_monday_utc"),
        CheckConstraint(_WINDOW_END_CHECK, name="ck_stats_point_window_end_one_week"),
        CheckConstraint("length(payload) > 0", name="ck_stats_point_payload_nonempty"),
        CheckConstraint("source_generation >= 0", name="ck_stats_point_source_generation"),
        CheckConstraint(_VERSION_CHECK, name="ck_stats_point_calculation_version"),
        CheckConstraint(_HASH_CHECK, name="ck_stats_point_content_hash"),
        CheckConstraint(
            _UTC_TIMESTAMP_CHECK.format(column="calculated_at"),
            name="ck_stats_point_calculated_at_utc",
        ),
        CheckConstraint(
            _UTC_TIMESTAMP_CHECK.format(column="developed_at"),
            name="ck_stats_point_developed_at_utc",
        ),
        CheckConstraint(
            "developed_at >= calculated_at", name="ck_stats_point_developed_after_calculated"
        ),
        CheckConstraint(
            "(revision = 1 AND correction_reason IS NULL) OR "
            "(revision > 1 AND correction_reason IN "
            "('late_recalculation', 'calculation_upgrade'))",
            name="ck_stats_point_correction_reason",
        ),
        Index(
            "ix_stats_point_effective_user_window_revision", "user_id", "window_start", "revision"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(sa_column=Column(Integer, nullable=False))
    window_start: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))
    window_end: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))
    revision: int = Field(sa_column=Column(Integer, nullable=False))
    supersedes_id: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    payload: str = Field(sa_column=Column(Text, nullable=False))
    calculated_at: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))
    developed_at: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))
    correction_reason: str | None = Field(
        default=None, sa_column=Column(String(128), nullable=True)
    )
    source_generation: int = Field(sa_column=Column(Integer, nullable=False))
    calculation_version: str = Field(sa_column=Column(String(128), nullable=False))
    content_hash: str = Field(sa_column=Column(String(64), nullable=False))


class BookmarkStatsProjectionState(SQLModel, table=True):
    """The single private, restartable baseline/projection control row."""

    __tablename__ = "bookmark_stats_projection_state"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_stats_projection_state"),
        CheckConstraint("id = 1", name="ck_stats_projection_state_singleton"),
        CheckConstraint(
            "status IN ('pending', 'running', 'active', 'failed')",
            name="ck_stats_projection_state_status",
        ),
        CheckConstraint(_VERSION_CHECK, name="ck_stats_projection_state_calculation_version"),
        CheckConstraint(
            "(checkpoint_user_id IS NULL AND checkpoint_window_start IS NULL) OR "
            "(checkpoint_user_id > 0 AND checkpoint_window_start IS NOT NULL)",
            name="ck_stats_projection_state_checkpoint_pair",
        ),
        CheckConstraint(
            "checkpoint_window_start IS NULL OR (" + _monday_check("checkpoint_window_start") + ")",
            name="ck_stats_projection_state_checkpoint_monday_utc",
        ),
        CheckConstraint(
            _UTC_TIMESTAMP_CHECK.format(column="updated_at"),
            name="ck_stats_projection_state_updated_at_utc",
        ),
        CheckConstraint(
            "baseline_started_at IS NULL OR "
            + _UTC_TIMESTAMP_CHECK.format(column="baseline_started_at"),
            name="ck_stats_projection_state_baseline_started_at_utc",
        ),
        CheckConstraint(
            "baseline_completed_at IS NULL OR "
            + _UTC_TIMESTAMP_CHECK.format(column="baseline_completed_at"),
            name="ck_stats_projection_state_baseline_completed_at_utc",
        ),
        CheckConstraint(
            "last_projection_success_at IS NULL OR "
            + _UTC_TIMESTAMP_CHECK.format(column="last_projection_success_at"),
            name="ck_stats_projection_state_last_success_at_utc",
        ),
        CheckConstraint(
            "baseline_completed_at IS NULL OR (baseline_started_at IS NOT NULL "
            "AND baseline_completed_at >= baseline_started_at)",
            name="ck_stats_projection_state_baseline_order",
        ),
        CheckConstraint(
            "failure_code IS NULL OR (length(failure_code) > 0 AND length(failure_code) <= 64 "
            "AND failure_code NOT GLOB '*[^a-z0-9_]*')",
            name="ck_stats_projection_state_failure_code_sanitized",
        ),
    )

    id: int = Field(sa_column=Column(Integer, nullable=False, primary_key=True))
    status: str = Field(sa_column=Column(String(16), nullable=False))
    calculation_version: str = Field(sa_column=Column(String(128), nullable=False))
    checkpoint_user_id: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    checkpoint_window_start: datetime | None = Field(
        default=None, sa_column=Column(UTCDateTime(), nullable=True)
    )
    baseline_started_at: datetime | None = Field(
        default=None, sa_column=Column(UTCDateTime(), nullable=True)
    )
    baseline_completed_at: datetime | None = Field(
        default=None, sa_column=Column(UTCDateTime(), nullable=True)
    )
    updated_at: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))
    last_projection_success_at: datetime | None = Field(
        default=None, sa_column=Column(UTCDateTime(), nullable=True)
    )
    failure_code: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))


__all__ = [
    "BookmarkStatsProjectionState",
    "BookmarkStatsWindowPoint",
    "BookmarkStatsWindowWorking",
]
