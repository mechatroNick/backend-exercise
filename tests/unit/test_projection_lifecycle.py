"""Pure failure and guard coverage for the normal projection processor."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlmodel import Session

from app.bookmarks.stats.dirty import DirtyMarker, DirtyReason
from app.bookmarks.stats.projection_repository import (
    ProjectionCalculationVersionMismatchError,
    ProjectionCandidateError,
    ProjectionStateError,
    ProjectionStateTransitionError,
    WeeklyProjectionRepository,
    WorkingProjectionRecord,
    _ProjectionStateStatus,
)
from app.bookmarks.stats.projection_service import ProjectionProcessor
from app.bookmarks.stats.schemas import BookmarkStats
from app.bookmarks.stats.weekly import calculate_weekly_payload, calculation_version, weekly_window

_NOW = datetime(2026, 8, 18, 12, tzinfo=UTC)
_WINDOW = weekly_window(_NOW)
_VERSION = calculation_version(5)
_CALCULATION = calculate_weekly_payload(
    BookmarkStats(total_bookmarks=0, total_tags=0, top_tags=(), bookmarks_per_month=()), 5
)


class _Clock:
    def __init__(self, now: datetime = _NOW) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class _NaiveClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 18, 12)


class _RollbackCountingSession(Session):
    def __init__(self) -> None:
        super().__init__()
        self.rollback_count = 0

    def rollback(self) -> None:
        self.rollback_count += 1


def _marker(start: datetime = _WINDOW.start) -> DirtyMarker:
    return DirtyMarker(
        user_id=1,
        window_start=start,
        generation=1,
        current_completed_generation=0,
        projection_completed_generation=0,
        reason=DirtyReason.UPDATE,
        first_marked_at=_NOW,
        last_marked_at=_NOW,
    )


def test_processor_constructor_and_boundary_types_fail_closed() -> None:
    with pytest.raises(TypeError, match="clock"):
        ProjectionProcessor(clock=object(), top_tags_limit=5)
    with pytest.raises(TypeError, match="top_tags_limit"):
        ProjectionProcessor(clock=_Clock(), top_tags_limit=True)
    with pytest.raises(TypeError, match="factories"):
        ProjectionProcessor(clock=_Clock(), top_tags_limit=5, reader_factory=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="dirty_repository_factory"):
        ProjectionProcessor(clock=_Clock(), top_tags_limit=5, dirty_repository_factory=object())  # type: ignore[arg-type]

    processor = ProjectionProcessor(clock=_Clock(), top_tags_limit=5)
    for method, candidate, message in (
        (processor.process_dirty, object(), "marker"),
        (processor.process_overdue, object(), "observed"),
    ):
        with _RollbackCountingSession() as session:
            with pytest.raises(TypeError, match=message):
                method(session, candidate)  # type: ignore[arg-type]
            assert session.rollback_count == 1
    with pytest.raises(TypeError, match="session"):
        processor._bound(object())  # type: ignore[arg-type]


def test_noncanonical_and_future_dirty_markers_roll_back_before_persistence() -> None:
    processor = ProjectionProcessor(clock=_Clock(), top_tags_limit=5)
    for marker, message in (
        (_marker(_WINDOW.start + timedelta(days=1)), "canonical"),
        (_marker(weekly_window(_NOW + timedelta(days=14)).start), "future"),
    ):
        with _RollbackCountingSession() as session:
            with pytest.raises(ProjectionCandidateError, match=message):
                processor.process_dirty(session, marker)
            assert session.rollback_count == 1


def test_processor_rolls_back_when_clock_normalization_fails() -> None:
    processor = ProjectionProcessor(clock=_NaiveClock(), top_tags_limit=5)
    observed = WorkingProjectionRecord(
        user_id=1,
        window=_WINDOW,
        payload=_CALCULATION.payload,
        calculated_at=_NOW,
        source_generation=0,
        calculation_version=_VERSION,
        content_hash=_CALCULATION.content_hash,
    )
    for method, candidate in (
        (processor.process_dirty, _marker()),
        (processor.process_overdue, observed),
    ):
        with _RollbackCountingSession() as session:
            with pytest.raises(ValueError, match="timezone-aware"):
                method(session, candidate)
            assert session.rollback_count == 1


def test_developed_and_current_helpers_fail_closed_on_version_or_user_guards() -> None:
    point = SimpleNamespace(calculation_version="old", content_hash="0" * 64, revision=1, id=1)
    repository = SimpleNamespace(effective_point=lambda _user_id, _window: point)
    with pytest.raises(ProjectionCalculationVersionMismatchError, match="developed"):
        ProjectionProcessor._persist_developed(
            repository,
            1,
            _WINDOW,
            _CALCULATION,
            1,
            _NOW,  # type: ignore[arg-type]
        )

    processor = ProjectionProcessor(clock=_Clock(), top_tags_limit=5)
    reader = SimpleNamespace(calculation_version=_VERSION)
    no_user = SimpleNamespace(user_exists=lambda _user_id: False)
    assert processor._ensure_current_working(no_user, reader, 1, _NOW) is False  # type: ignore[arg-type]

    existing = SimpleNamespace(calculation_version="old")
    mismatch = SimpleNamespace(
        user_exists=lambda _user_id: True,
        get_working=lambda _user_id, _window: existing,
    )
    with pytest.raises(ProjectionCalculationVersionMismatchError, match="current working"):
        processor._ensure_current_working(mismatch, reader, 1, _NOW)  # type: ignore[arg-type]


def test_repository_delete_guard_failure_is_raised_after_developed_write() -> None:
    working = WorkingProjectionRecord(
        user_id=1,
        window=_WINDOW,
        payload=_CALCULATION.payload,
        calculated_at=_NOW,
        source_generation=1,
        calculation_version=_VERSION,
        content_hash=_CALCULATION.content_hash,
    )

    class _Reader:
        calculation_version = _VERSION

        def read(self, _user_id: int, _window: object) -> BookmarkStats:
            return BookmarkStats(
                total_bookmarks=0, total_tags=0, top_tags=(), bookmarks_per_month=()
            )

    class _Repository:
        def require_active(self, _version: str) -> None:
            return None

        def effective_point(self, _user_id: int, _window: object) -> None:
            return None

        def append_point(self, _point: object) -> None:
            return None

        def get_working(self, _user_id: int, _window: object) -> WorkingProjectionRecord:
            return working

        def delete_working(self, _record: WorkingProjectionRecord) -> bool:
            return False

    processor = ProjectionProcessor(
        clock=_Clock(_WINDOW.end),
        top_tags_limit=5,
        reader_factory=lambda _session, _limit: _Reader(),
        repository_factory=lambda _session: _Repository(),
    )
    with Session() as session, pytest.raises(ProjectionStateError, match="changed before deletion"):
        processor.process_dirty(session, _marker())


def test_processor_current_working_and_calculation_version_guards() -> None:
    class _WrongReader:
        calculation_version = "wrong"

        def read(self, _user_id: int, _window: object) -> BookmarkStats:
            return BookmarkStats(
                total_bookmarks=0, total_tags=0, top_tags=(), bookmarks_per_month=()
            )

    processor = ProjectionProcessor(clock=_Clock(), top_tags_limit=5)
    with pytest.raises(ProjectionCalculationVersionMismatchError, match="reader calculation"):
        processor._calculation(_WrongReader(), 1, _WINDOW)  # type: ignore[arg-type]


def test_repository_active_and_success_guards_fail_closed() -> None:
    repository = WeeklyProjectionRepository(object())  # type: ignore[arg-type]
    repository.get_state = lambda: None  # type: ignore[method-assign]
    with pytest.raises(ProjectionStateTransitionError, match="absent"):
        repository.require_active(_VERSION)
    repository.get_state = lambda: SimpleNamespace(  # type: ignore[method-assign]
        calculation_version=_VERSION,
        status=_ProjectionStateStatus.RUNNING,
    )
    with pytest.raises(ProjectionStateTransitionError, match="not active"):
        repository.require_active(_VERSION)

    class _Session:
        def __init__(self, rowcount: int) -> None:
            self.rowcount = rowcount

        def execute(self, _statement: object, _parameters: object) -> SimpleNamespace:
            return SimpleNamespace(rowcount=self.rowcount)

    rowcount_zero = WeeklyProjectionRepository(_Session(0))  # type: ignore[arg-type]
    with pytest.raises(ProjectionStateTransitionError, match="inactive"):
        rowcount_zero.record_projection_success(_VERSION, _NOW)
    missing_after_update = WeeklyProjectionRepository(_Session(1))  # type: ignore[arg-type]
    missing_after_update.get_state = lambda: None  # type: ignore[method-assign]
    with pytest.raises(ProjectionStateTransitionError, match="disappeared"):
        missing_after_update.record_projection_success(_VERSION, _NOW)


def test_overdue_delete_guard_failure_rolls_back_before_next_window_creation() -> None:
    working = WorkingProjectionRecord(
        user_id=1,
        window=_WINDOW,
        payload=_CALCULATION.payload,
        calculated_at=_NOW,
        source_generation=0,
        calculation_version=_VERSION,
        content_hash=_CALCULATION.content_hash,
    )

    class _Reader:
        calculation_version = _VERSION

        def read(self, _user_id: int, _window: object) -> BookmarkStats:
            return BookmarkStats(
                total_bookmarks=0, total_tags=0, bookmarks_per_month=(), top_tags=()
            )

    class _Repository:
        def require_active(self, _version: str) -> None:
            return None

        def get_working(self, _user_id: int, _window: object) -> WorkingProjectionRecord:
            return working

        def pending_projection_generation(self, _user_id: int, _window: object) -> None:
            return None

        def effective_point(self, _user_id: int, _window: object) -> None:
            return None

        def append_point(self, _point: object) -> None:
            return None

        def delete_working(self, _record: WorkingProjectionRecord) -> bool:
            return False

    processor = ProjectionProcessor(
        clock=_Clock(_WINDOW.end),
        top_tags_limit=5,
        reader_factory=lambda _session, _limit: _Reader(),
        repository_factory=lambda _session: _Repository(),
    )
    with Session() as session, pytest.raises(ProjectionStateError, match="changed before deletion"):
        processor.process_overdue(session, working)
