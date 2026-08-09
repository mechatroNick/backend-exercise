"""Caller-session-owned persistence for private weekly projection rows."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlmodel import Session

from app.bookmarks.stats.weekly import WeeklyWindow
from app.core.clock import normalize_utc
from app.core.internal_models import FrozenInternalModel

_UTC_TEXT_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
_MAX_OBSERVATION_LIMIT = 100


class CorrectionReason(StrEnum):
    """The only service-level causes allowed for append-only corrections."""

    LATE_RECALCULATION = "late_recalculation"
    CALCULATION_UPGRADE = "calculation_upgrade"


def _positive(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _nonnegative(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    return normalize_utc(value)


def _encoded(value: datetime, name: str) -> str:
    return _utc(value, name).strftime(_UTC_TEXT_FORMAT)


def _decoded(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError(f"persisted {name} must be a UTC timestamp string")
    try:
        return datetime.strptime(value, _UTC_TEXT_FORMAT).replace(tzinfo=UTC)
    except ValueError as error:
        raise ValueError(f"persisted {name} is not canonical UTC") from error


def _hash(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("content_hash must be lowercase SHA-256 hex")
    return value


def _version(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ValueError("calculation_version must be a nonempty string of at most 128 characters")
    return value


def _payload(value: bytes) -> bytes:
    if not isinstance(value, bytes) or not value:
        raise ValueError("payload must be nonempty bytes")
    try:
        value.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("payload must be UTF-8") from error
    return value


class WorkingProjectionRecord(FrozenInternalModel):
    user_id: int
    window: WeeklyWindow
    payload: bytes
    calculated_at: datetime
    source_generation: int
    calculation_version: str
    content_hash: str


class NewProjectionPoint(FrozenInternalModel):
    user_id: int
    window: WeeklyWindow
    revision: int
    supersedes_id: int | None
    payload: bytes
    calculated_at: datetime
    developed_at: datetime
    correction_reason: CorrectionReason | None
    source_generation: int
    calculation_version: str
    content_hash: str


class ProjectionPointRecord(NewProjectionPoint):
    id: int


def _validate_working(record: WorkingProjectionRecord) -> None:
    _positive(record.user_id, "user_id")
    WeeklyWindow.from_bounds(record.window.start, record.window.end)
    _payload(record.payload)
    _utc(record.calculated_at, "calculated_at")
    _nonnegative(record.source_generation, "source_generation")
    _version(record.calculation_version)
    _hash(record.content_hash)


def _validate_point(point: NewProjectionPoint) -> None:
    _positive(point.user_id, "user_id")
    WeeklyWindow.from_bounds(point.window.start, point.window.end)
    _positive(point.revision, "revision")
    if point.supersedes_id is not None:
        _positive(point.supersedes_id, "supersedes_id")
    _payload(point.payload)
    calculated_at = _utc(point.calculated_at, "calculated_at")
    if _utc(point.developed_at, "developed_at") < calculated_at:
        raise ValueError("developed_at must not precede calculated_at")
    _nonnegative(point.source_generation, "source_generation")
    _version(point.calculation_version)
    _hash(point.content_hash)
    if point.revision == 1:
        if point.supersedes_id is not None or point.correction_reason is not None:
            raise ValueError("revision 1 must not supersede a point or have a correction reason")
    elif point.supersedes_id is None:
        raise ValueError("correction revision must supersede the effective point")
    elif not isinstance(point.correction_reason, CorrectionReason):
        raise ValueError("correction revision requires a CorrectionReason")


def _working(row: dict[str, Any]) -> WorkingProjectionRecord:
    payload = row["payload"]
    record = WorkingProjectionRecord(
        user_id=row["user_id"],
        window=WeeklyWindow.from_bounds(
            _decoded(row["window_start"], "window_start"),
            _decoded(row["window_end"], "window_end"),
        ),
        payload=_payload(payload.encode("utf-8") if isinstance(payload, str) else b""),
        calculated_at=_decoded(row["calculated_at"], "calculated_at"),
        source_generation=row["source_generation"],
        calculation_version=row["calculation_version"],
        content_hash=row["content_hash"],
    )
    _validate_working(record)
    return record


def _point(row: dict[str, Any]) -> ProjectionPointRecord:
    payload = row["payload"]
    record = ProjectionPointRecord(
        id=row["id"],
        user_id=row["user_id"],
        window=WeeklyWindow.from_bounds(
            _decoded(row["window_start"], "window_start"),
            _decoded(row["window_end"], "window_end"),
        ),
        revision=row["revision"],
        supersedes_id=row["supersedes_id"],
        payload=_payload(payload.encode("utf-8") if isinstance(payload, str) else b""),
        calculated_at=_decoded(row["calculated_at"], "calculated_at"),
        developed_at=_decoded(row["developed_at"], "developed_at"),
        correction_reason=(
            None if row["correction_reason"] is None else CorrectionReason(row["correction_reason"])
        ),
        source_generation=row["source_generation"],
        calculation_version=row["calculation_version"],
        content_hash=row["content_hash"],
    )
    _positive(record.id, "persisted id")
    _validate_point(record)
    return record


class WeeklyProjectionRepository:
    """Parameterized row operations; transaction completion belongs to the caller."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_working(self, user_id: int, window: WeeklyWindow) -> WorkingProjectionRecord | None:
        _positive(user_id, "user_id")
        validated_window = WeeklyWindow.from_bounds(window.start, window.end)
        row = (
            self._session.execute(
                text(
                    "SELECT user_id, window_start, window_end, payload, calculated_at, "
                    "source_generation, calculation_version, content_hash "
                    "FROM bookmark_stats_window_working "
                    "WHERE user_id=:user_id AND window_start=:window_start"
                ),
                {
                    "user_id": user_id,
                    "window_start": _encoded(validated_window.start, "window_start"),
                },
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _working(dict(row))

    def replace_working(self, record: WorkingProjectionRecord) -> None:
        _validate_working(record)
        self._session.execute(
            text(
                "INSERT INTO bookmark_stats_window_working "
                "(user_id, window_start, window_end, payload, calculated_at, source_generation, "
                "calculation_version, content_hash) VALUES "
                "(:user_id, :window_start, :window_end, :payload, :calculated_at, "
                ":source_generation, :calculation_version, :content_hash) "
                "ON CONFLICT(user_id, window_start) DO UPDATE SET "
                "window_end=excluded.window_end, payload=excluded.payload, "
                "calculated_at=excluded.calculated_at, "
                "source_generation=excluded.source_generation, "
                "calculation_version=excluded.calculation_version, "
                "content_hash=excluded.content_hash"
            ),
            self._working_parameters(record),
        )

    def observe_overdue(
        self, now: datetime, limit: int = _MAX_OBSERVATION_LIMIT
    ) -> tuple[WorkingProjectionRecord, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an integer")
        if not 1 <= limit <= _MAX_OBSERVATION_LIMIT:
            raise ValueError("limit must be between 1 and 100")
        rows = self._session.execute(
            text(
                "SELECT user_id, window_start, window_end, payload, calculated_at, "
                "source_generation, calculation_version, content_hash "
                "FROM bookmark_stats_window_working WHERE window_end <= :now "
                "ORDER BY window_end ASC, user_id ASC LIMIT :limit"
            ),
            {"now": _encoded(now, "now"), "limit": limit},
        ).mappings()
        return tuple(_working(dict(row)) for row in rows)

    def effective_point(self, user_id: int, window: WeeklyWindow) -> ProjectionPointRecord | None:
        _positive(user_id, "user_id")
        validated_window = WeeklyWindow.from_bounds(window.start, window.end)
        row = (
            self._session.execute(
                text(
                    "SELECT id, user_id, window_start, window_end, revision, supersedes_id, "
                    "payload, "
                    "calculated_at, developed_at, correction_reason, source_generation, "
                    "calculation_version, content_hash FROM bookmark_stats_window_point "
                    "WHERE user_id=:user_id AND window_start=:window_start "
                    "ORDER BY revision DESC LIMIT 1"
                ),
                {
                    "user_id": user_id,
                    "window_start": _encoded(validated_window.start, "window_start"),
                },
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _point(dict(row))

    def append_point(self, point: NewProjectionPoint) -> ProjectionPointRecord:
        _validate_point(point)
        current = self.effective_point(point.user_id, point.window)
        if point.revision == 1:
            if current is not None:
                raise ValueError("root revision requires no existing effective point")
        elif current is None:
            raise ValueError("correction requires an existing effective point")
        elif point.revision != current.revision + 1 or point.supersedes_id != current.id:
            raise ValueError("correction must immediately supersede the effective revision")

        result = cast(
            CursorResult[Any],
            self._session.execute(
                text(
                    "INSERT INTO bookmark_stats_window_point "
                    "(user_id, window_start, window_end, revision, supersedes_id, payload, "
                    "calculated_at, developed_at, correction_reason, source_generation, "
                    "calculation_version, content_hash) "
                    "VALUES (:user_id, :window_start, :window_end, :revision, :supersedes_id, "
                    ":payload, "
                    ":calculated_at, :developed_at, :correction_reason, :source_generation, "
                    ":calculation_version, :content_hash)"
                ),
                self._point_parameters(point),
            ),
        )
        inserted_id = result.lastrowid
        if isinstance(inserted_id, bool) or not isinstance(inserted_id, int) or inserted_id <= 0:
            raise RuntimeError("point insert did not return an identifier")
        inserted = (
            self._session.execute(
                text(
                    "SELECT id, user_id, window_start, window_end, revision, supersedes_id, "
                    "payload, "
                    "calculated_at, developed_at, correction_reason, source_generation, "
                    "calculation_version, content_hash FROM bookmark_stats_window_point "
                    "WHERE id=:id"
                ),
                {"id": inserted_id},
            )
            .mappings()
            .one()
        )
        return _point(dict(inserted))

    @staticmethod
    def _working_parameters(record: WorkingProjectionRecord) -> dict[str, object]:
        return {
            "user_id": record.user_id,
            "window_start": _encoded(record.window.start, "window_start"),
            "window_end": _encoded(record.window.end, "window_end"),
            "payload": record.payload.decode("utf-8"),
            "calculated_at": _encoded(record.calculated_at, "calculated_at"),
            "source_generation": record.source_generation,
            "calculation_version": record.calculation_version,
            "content_hash": record.content_hash,
        }

    @staticmethod
    def _point_parameters(point: NewProjectionPoint) -> dict[str, object]:
        return {
            "user_id": point.user_id,
            "window_start": _encoded(point.window.start, "window_start"),
            "window_end": _encoded(point.window.end, "window_end"),
            "revision": point.revision,
            "supersedes_id": point.supersedes_id,
            "payload": point.payload.decode("utf-8"),
            "calculated_at": _encoded(point.calculated_at, "calculated_at"),
            "developed_at": _encoded(point.developed_at, "developed_at"),
            "correction_reason": point.correction_reason,
            "source_generation": point.source_generation,
            "calculation_version": point.calculation_version,
            "content_hash": point.content_hash,
        }


__all__ = [
    "NewProjectionPoint",
    "CorrectionReason",
    "ProjectionPointRecord",
    "WeeklyProjectionRepository",
    "WorkingProjectionRecord",
]
