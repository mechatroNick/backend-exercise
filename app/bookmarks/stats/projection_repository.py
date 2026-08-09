"""Caller-session-owned persistence for private weekly projection rows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
_MAX_BASELINE_CANDIDATE_LIMIT = _MAX_OBSERVATION_LIMIT + 1


class CorrectionReason(StrEnum):
    """The only service-level causes allowed for append-only corrections."""

    LATE_RECALCULATION = "late_recalculation"
    CALCULATION_UPGRADE = "calculation_upgrade"


class _ProjectionStateStatus(StrEnum):
    """Private lifecycle values for the singleton projection control row."""

    PENDING = "pending"
    RUNNING = "running"
    ACTIVE = "active"
    FAILED = "failed"


class ProjectionStateError(Exception):
    """A durable projection state cannot safely support the requested operation."""


class ProjectionCalculationVersionMismatchError(ProjectionStateError):
    """Stored projection data cannot be compared with the active calculation."""


class ProjectionStateTransitionError(ProjectionStateError):
    """The singleton state is malformed or cannot make the requested transition."""


class ProjectionCandidateError(ProjectionStateError):
    """A surviving-data candidate cannot be safely represented as a weekly window."""


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


class ProjectionStateRecord(FrozenInternalModel):
    """Validated private state for the one restartable baseline lifecycle."""

    status: _ProjectionStateStatus
    calculation_version: str
    checkpoint_user_id: int | None
    checkpoint_window: WeeklyWindow | None
    baseline_started_at: datetime | None
    baseline_completed_at: datetime | None
    updated_at: datetime
    last_projection_success_at: datetime | None
    failure_code: str | None


class SurvivingWindowCandidate(FrozenInternalModel):
    """One canonical bookmark-backed user/window pair eligible for baseline work."""

    user_id: int
    window: WeeklyWindow


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


def _failure_code(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 64
        or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_" for character in value)
    ):
        raise ValueError("failure_code must be a sanitized low-cardinality code")
    return value


def _validate_state(record: ProjectionStateRecord) -> None:
    _version(record.calculation_version)
    _utc(record.updated_at, "updated_at")
    if record.checkpoint_user_id is None:
        if record.checkpoint_window is not None:
            raise ProjectionStateTransitionError("checkpoint fields must be present together")
    else:
        _positive(record.checkpoint_user_id, "checkpoint_user_id")
        if record.checkpoint_window is None:
            raise ProjectionStateTransitionError("checkpoint fields must be present together")
        WeeklyWindow.from_bounds(record.checkpoint_window.start, record.checkpoint_window.end)
    if record.baseline_started_at is not None:
        started_at = _utc(record.baseline_started_at, "baseline_started_at")
    else:
        started_at = None
    if record.baseline_completed_at is not None:
        completed_at = _utc(record.baseline_completed_at, "baseline_completed_at")
        if started_at is None or completed_at < started_at:
            raise ProjectionStateTransitionError("baseline completion must follow baseline start")
    if record.last_projection_success_at is not None:
        _utc(record.last_projection_success_at, "last_projection_success_at")
    if record.failure_code is not None:
        _failure_code(record.failure_code)
    if record.status is _ProjectionStateStatus.ACTIVE and record.baseline_completed_at is None:
        raise ProjectionStateTransitionError("active baseline state requires completion timestamp")
    if record.status is _ProjectionStateStatus.PENDING and record.baseline_started_at is not None:
        raise ProjectionStateTransitionError("pending baseline state must not have started")


def _validate_candidate(candidate: SurvivingWindowCandidate) -> None:
    _positive(candidate.user_id, "user_id")
    WeeklyWindow.from_bounds(candidate.window.start, candidate.window.end)


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


def _state(row: dict[str, Any]) -> ProjectionStateRecord:
    checkpoint_user_id = row["checkpoint_user_id"]
    checkpoint_window_start = row["checkpoint_window_start"]
    if (checkpoint_user_id is None) != (checkpoint_window_start is None):
        raise ProjectionStateTransitionError("persisted checkpoint fields must be present together")
    checkpoint_start = (
        None
        if checkpoint_window_start is None
        else _decoded(checkpoint_window_start, "checkpoint_window_start")
    )
    checkpoint_window = (
        None
        if checkpoint_start is None
        else WeeklyWindow.from_bounds(checkpoint_start, checkpoint_start + timedelta(days=7))
    )
    record = ProjectionStateRecord(
        status=_ProjectionStateStatus(row["status"]),
        calculation_version=row["calculation_version"],
        checkpoint_user_id=checkpoint_user_id,
        checkpoint_window=checkpoint_window,
        baseline_started_at=(
            None
            if row["baseline_started_at"] is None
            else _decoded(row["baseline_started_at"], "baseline_started_at")
        ),
        baseline_completed_at=(
            None
            if row["baseline_completed_at"] is None
            else _decoded(row["baseline_completed_at"], "baseline_completed_at")
        ),
        updated_at=_decoded(row["updated_at"], "updated_at"),
        last_projection_success_at=(
            None
            if row["last_projection_success_at"] is None
            else _decoded(row["last_projection_success_at"], "last_projection_success_at")
        ),
        failure_code=row["failure_code"],
    )
    _validate_state(record)
    return record


def _candidate(row: dict[str, Any]) -> SurvivingWindowCandidate:
    window = WeeklyWindow.from_datetime(_decoded(row["representative_created_at"], "created_at"))
    persisted_start = _decoded(row["window_start"], "window_start")
    if window.start != persisted_start:
        raise ProjectionCandidateError("surviving candidate window does not match weekly invariant")
    candidate = SurvivingWindowCandidate(user_id=row["user_id"], window=window)
    _validate_candidate(candidate)
    return candidate


class WeeklyProjectionRepository:
    """Parameterized row operations; transaction completion belongs to the caller."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_state(self) -> ProjectionStateRecord | None:
        """Return the validated singleton state without changing transaction ownership."""
        row = (
            self._session.execute(
                text(
                    "SELECT status, calculation_version, checkpoint_user_id, "
                    "checkpoint_window_start, baseline_started_at, baseline_completed_at, "
                    "updated_at, last_projection_success_at, failure_code "
                    "FROM bookmark_stats_projection_state WHERE id=1"
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _state(dict(row))

    def ensure_state(self, calculation_version: str, now: datetime) -> ProjectionStateRecord:
        """Create the pending singleton or verify it is compatible with this calculation."""
        _version(calculation_version)
        encoded_now = _encoded(now, "now")
        state = self.get_state()
        if state is not None:
            self._require_calculation_version(state, calculation_version)
            return state
        self._session.execute(
            text(
                "INSERT INTO bookmark_stats_projection_state "
                "(id, status, calculation_version, checkpoint_user_id, checkpoint_window_start, "
                "baseline_started_at, baseline_completed_at, updated_at, "
                "last_projection_success_at, failure_code) VALUES "
                "(1, :status, :calculation_version, NULL, NULL, NULL, NULL, :updated_at, "
                "NULL, NULL)"
            ),
            {
                "status": _ProjectionStateStatus.PENDING.value,
                "calculation_version": calculation_version,
                "updated_at": encoded_now,
            },
        )
        created = self.get_state()
        if created is None:
            raise ProjectionStateTransitionError("singleton state was not created")
        return created

    def start_or_resume(self, calculation_version: str, now: datetime) -> ProjectionStateRecord:
        """Enter running state once, or resume an already-running same-version baseline."""
        state = self.ensure_state(calculation_version, now)
        if state.status is _ProjectionStateStatus.ACTIVE:
            return state
        if state.status is _ProjectionStateStatus.FAILED:
            raise ProjectionStateTransitionError("failed baseline state requires explicit recovery")
        if state.status is _ProjectionStateStatus.RUNNING:
            return state
        if state.status is not _ProjectionStateStatus.PENDING:
            raise ProjectionStateTransitionError("unsupported projection baseline status")
        encoded_now = _encoded(now, "now")
        self._session.execute(
            text(
                "UPDATE bookmark_stats_projection_state SET status=:status, "
                "baseline_started_at=:baseline_started_at, updated_at=:updated_at "
                "WHERE id=1 AND status=:expected_status"
            ),
            {
                "status": _ProjectionStateStatus.RUNNING.value,
                "baseline_started_at": encoded_now,
                "updated_at": encoded_now,
                "expected_status": _ProjectionStateStatus.PENDING.value,
            },
        )
        started = self.get_state()
        if started is None or started.status is not _ProjectionStateStatus.RUNNING:
            raise ProjectionStateTransitionError("baseline state did not enter running")
        return started

    def surviving_candidates_after(
        self,
        checkpoint: SurvivingWindowCandidate | None,
        limit: int,
    ) -> tuple[SurvivingWindowCandidate, ...]:
        """Read a bounded lexicographic page from surviving canonical bookmarks only."""
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an integer")
        if not 1 <= limit <= _MAX_BASELINE_CANDIDATE_LIMIT:
            raise ValueError("limit must be between 1 and 101")
        if checkpoint is not None:
            _validate_candidate(checkpoint)
        rows = self._session.execute(
            text(
                "WITH candidates AS ("
                "SELECT b.user_id AS user_id, "
                "min(b.created_at) AS representative_created_at, "
                "strftime('%Y-%m-%dT00:00:00.000000Z', "
                "date(b.created_at, '-' || "
                "((CAST(strftime('%w', b.created_at) AS INTEGER) + 6) % 7) || ' days')) "
                "AS window_start "
                "FROM bookmarks AS b "
                "GROUP BY b.user_id, window_start"
                ") "
                "SELECT user_id, representative_created_at, window_start FROM candidates "
                "WHERE :checkpoint_user_id IS NULL "
                "OR user_id > :checkpoint_user_id "
                "OR (user_id = :checkpoint_user_id AND window_start > :checkpoint_window_start) "
                "ORDER BY user_id ASC, window_start ASC LIMIT :limit"
            ),
            {
                "checkpoint_user_id": None if checkpoint is None else checkpoint.user_id,
                "checkpoint_window_start": (
                    None
                    if checkpoint is None
                    else _encoded(checkpoint.window.start, "window_start")
                ),
                "limit": limit,
            },
        ).mappings()
        return tuple(_candidate(dict(row)) for row in rows)

    def advance(
        self,
        candidate: SurvivingWindowCandidate,
        now: datetime,
    ) -> ProjectionStateRecord:
        """Persist one successfully completed candidate as the exclusive next-page checkpoint."""
        _validate_candidate(candidate)
        self._session.execute(
            text(
                "UPDATE bookmark_stats_projection_state SET checkpoint_user_id=:user_id, "
                "checkpoint_window_start=:window_start, updated_at=:updated_at "
                "WHERE id=1 AND status=:status"
            ),
            {
                "user_id": candidate.user_id,
                "window_start": _encoded(candidate.window.start, "window_start"),
                "updated_at": _encoded(now, "now"),
                "status": _ProjectionStateStatus.RUNNING.value,
            },
        )
        advanced = self.get_state()
        if advanced is None or advanced.status is not _ProjectionStateStatus.RUNNING:
            raise ProjectionStateTransitionError("baseline state did not persist checkpoint")
        return advanced

    def activate(self, now: datetime) -> ProjectionStateRecord:
        """Durably mark a running baseline complete after the terminal page commits."""
        encoded_now = _encoded(now, "now")
        self._session.execute(
            text(
                "UPDATE bookmark_stats_projection_state SET status=:status, "
                "baseline_completed_at=:baseline_completed_at, updated_at=:updated_at, "
                "failure_code=NULL WHERE id=1 AND status=:expected_status"
            ),
            {
                "status": _ProjectionStateStatus.ACTIVE.value,
                "baseline_completed_at": encoded_now,
                "updated_at": encoded_now,
                "expected_status": _ProjectionStateStatus.RUNNING.value,
            },
        )
        active = self.get_state()
        if active is None or active.status is not _ProjectionStateStatus.ACTIVE:
            raise ProjectionStateTransitionError("baseline state did not activate")
        return active

    def fail(
        self, calculation_version: str, failure_code: str, now: datetime
    ) -> ProjectionStateRecord:
        """Expose an explicit low-cardinality failure transition for the owning lifecycle."""
        _version(calculation_version)
        _failure_code(failure_code)
        state = self.get_state()
        if state is None:
            raise ProjectionStateTransitionError("cannot fail an absent projection state")
        self._require_calculation_version(state, calculation_version)
        if state.status is _ProjectionStateStatus.ACTIVE:
            raise ProjectionStateTransitionError("active projection state cannot fail baseline")
        self._session.execute(
            text(
                "UPDATE bookmark_stats_projection_state SET status=:status, "
                "failure_code=:failure_code, "
                "updated_at=:updated_at WHERE id=1"
            ),
            {
                "status": _ProjectionStateStatus.FAILED.value,
                "failure_code": failure_code,
                "updated_at": _encoded(now, "now"),
            },
        )
        failed = self.get_state()
        if failed is None or failed.status is not _ProjectionStateStatus.FAILED:
            raise ProjectionStateTransitionError("projection state did not enter failed")
        return failed

    @staticmethod
    def _require_calculation_version(
        state: ProjectionStateRecord,
        calculation_version: str,
    ) -> None:
        if state.calculation_version != calculation_version:
            raise ProjectionCalculationVersionMismatchError(
                "stored projection calculation version differs from runtime"
            )

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

    def delete_working(self, record: WorkingProjectionRecord) -> bool:
        """Delete exactly the working row that was recalculated, never a replacement."""
        _validate_working(record)
        result = cast(
            CursorResult[Any],
            self._session.execute(
                text(
                    "DELETE FROM bookmark_stats_window_working "
                    "WHERE user_id=:user_id AND window_start=:window_start "
                    "AND window_end=:window_end AND payload=:payload "
                    "AND calculated_at=:calculated_at "
                    "AND source_generation=:source_generation "
                    "AND calculation_version=:calculation_version "
                    "AND content_hash=:content_hash"
                ),
                self._working_parameters(record),
            ),
        )
        return result.rowcount == 1

    def pending_projection_generation(self, user_id: int, window: WeeklyWindow) -> int | None:
        """Return a still-pending projection generation for this exact dirty key."""
        _positive(user_id, "user_id")
        validated_window = WeeklyWindow.from_bounds(window.start, window.end)
        row = (
            self._session.execute(
                text(
                    "SELECT generation, projection_completed_generation "
                    "FROM bookmark_stats_window_dirty "
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
        if row is None:
            return None
        generation = _positive(row["generation"], "persisted dirty generation")
        completed = _nonnegative(
            row["projection_completed_generation"], "persisted projection completion"
        )
        return generation if completed != generation else None

    def user_exists(self, user_id: int) -> bool:
        """Keep lifecycle work from recreating private rows after a user cascade."""
        _positive(user_id, "user_id")
        return (
            self._session.execute(
                text("SELECT 1 FROM users WHERE id=:user_id"), {"user_id": user_id}
            ).scalar_one_or_none()
            is not None
        )

    def require_active(self, calculation_version: str) -> ProjectionStateRecord:
        """Require a completed compatible baseline before normal projection work."""
        _version(calculation_version)
        state = self.get_state()
        if state is None:
            raise ProjectionStateTransitionError("projection baseline state is absent")
        self._require_calculation_version(state, calculation_version)
        if state.status is not _ProjectionStateStatus.ACTIVE:
            raise ProjectionStateTransitionError("projection baseline is not active")
        return state

    def record_projection_success(
        self, calculation_version: str, now: datetime
    ) -> ProjectionStateRecord:
        """Guard the success timestamp against a state or version transition race."""
        _version(calculation_version)
        encoded_now = _encoded(now, "now")
        result = cast(
            CursorResult[Any],
            self._session.execute(
                text(
                    "UPDATE bookmark_stats_projection_state "
                    "SET last_projection_success_at=:now, updated_at=:now, failure_code=NULL "
                    "WHERE id=1 AND status=:status AND calculation_version=:calculation_version"
                ),
                {
                    "now": encoded_now,
                    "status": _ProjectionStateStatus.ACTIVE.value,
                    "calculation_version": calculation_version,
                },
            ),
        )
        if result.rowcount != 1:
            raise ProjectionStateTransitionError("projection state became inactive or incompatible")
        state = self.get_state()
        if state is None:
            raise ProjectionStateTransitionError("projection state disappeared after success")
        return state

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
    "ProjectionCalculationVersionMismatchError",
    "ProjectionCandidateError",
    "ProjectionPointRecord",
    "ProjectionStateError",
    "ProjectionStateRecord",
    "ProjectionStateTransitionError",
    "SurvivingWindowCandidate",
    "WeeklyProjectionRepository",
    "WorkingProjectionRecord",
]
