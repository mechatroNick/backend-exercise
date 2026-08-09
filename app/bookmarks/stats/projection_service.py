"""Restartable, surviving-data-only initial weekly projection baseline."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum

from sqlmodel import Session

from app.bookmarks.stats.dirty import (
    BookmarkStatsDirtyRepository,
    DirtyAcknowledgementStatus,
    DirtyMarker,
)
from app.bookmarks.stats.projection_repository import (
    CorrectionReason,
    NewProjectionPoint,
    ProjectionCalculationVersionMismatchError,
    ProjectionCandidateError,
    ProjectionStateError,
    ProjectionStateRecord,
    SurvivingWindowCandidate,
    WeeklyProjectionRepository,
    WorkingProjectionRecord,
    _ProjectionStateStatus,
)
from app.bookmarks.stats.weekly import (
    HashComparison,
    WeeklyCalculation,
    WeeklyStatsReader,
    WeeklyWindow,
    calculate_weekly_payload,
    compare_content_hashes,
)
from app.core.clock import Clock, normalize_utc
from app.core.internal_models import FrozenInternalModel

_MAX_BASELINE_BATCH_SIZE = 100

SessionFactory = Callable[[], Session]
WeeklyReaderFactory = Callable[[Session, int], WeeklyStatsReader]
ProjectionRepositoryFactory = Callable[[Session], WeeklyProjectionRepository]


class ProjectionBaselineResult(FrozenInternalModel):
    """Identifier-free outcome from one bounded baseline transaction."""

    processed_candidate_count: int
    has_more: bool
    active: bool


class ProjectionProcessOutcome(StrEnum):
    """Stable, identifier-free result for one normal projection transaction."""

    APPLIED = "applied"
    DEFERRED = "deferred"
    STALE = "stale"
    ABSENT = "absent"


class ProjectionProcessResult(FrozenInternalModel):
    outcome: ProjectionProcessOutcome
    appended_revision: int | None = None
    created_current_working: bool = False


class ProjectionProcessor:
    """Apply one dirty marker or overdue developing row in a caller-owned transaction."""

    def __init__(
        self,
        *,
        clock: Clock,
        top_tags_limit: int,
        reader_factory: WeeklyReaderFactory = WeeklyStatsReader,
        repository_factory: ProjectionRepositoryFactory = WeeklyProjectionRepository,
        dirty_repository_factory: Callable[
            [Session], BookmarkStatsDirtyRepository
        ] = BookmarkStatsDirtyRepository,
    ) -> None:
        if not hasattr(clock, "now") or not callable(clock.now):
            raise TypeError("clock must provide now()")
        if isinstance(top_tags_limit, bool) or not isinstance(top_tags_limit, int):
            raise TypeError("top_tags_limit must be an integer")
        if not callable(reader_factory) or not callable(repository_factory):
            raise TypeError("projection factories must be callable")
        if not callable(dirty_repository_factory):
            raise TypeError("dirty_repository_factory must be callable")
        self._clock = clock
        self._top_tags_limit = top_tags_limit
        self._reader_factory = reader_factory
        self._repository_factory = repository_factory
        self._dirty_repository_factory = dirty_repository_factory

    def process_dirty(self, session: Session, marker: DirtyMarker) -> ProjectionProcessResult:
        """Durably apply one observed generation, or roll every write back when stale."""
        if not isinstance(marker, DirtyMarker):
            raise TypeError("marker must be a DirtyMarker")
        now = normalize_utc(self._clock.now())
        window = WeeklyWindow.from_datetime(marker.window_start)
        if window.start != marker.window_start:
            raise ProjectionCandidateError("dirty marker window is not canonical")
        if window.start > now:
            self._rollback(session)
            raise ProjectionCandidateError("future dirty marker cannot be projected")
        try:
            reader, repository = self._bound(session)
            repository.require_active(reader.calculation_version)
            calculation = self._calculation(reader, marker.user_id, window)
            appended_revision: int | None = None
            if window.end <= now:
                appended_revision = self._persist_developed(
                    repository, marker.user_id, window, calculation, marker.generation, now
                )
                working = repository.get_working(marker.user_id, window)
                if working is not None and not repository.delete_working(working):
                    raise ProjectionStateError("closed working row changed before deletion")
                created_current = self._ensure_current_working(
                    repository, reader, marker.user_id, now
                )
            else:
                created_current = False
                existing = repository.get_working(marker.user_id, window)
                if (
                    existing is not None
                    and existing.calculation_version != calculation.calculation_version
                ):
                    raise ProjectionCalculationVersionMismatchError(
                        "stored working projection calculation version differs from runtime"
                    )
                repository.replace_working(
                    WorkingProjectionRecord(
                        user_id=marker.user_id,
                        window=window,
                        payload=calculation.payload,
                        calculated_at=now,
                        source_generation=marker.generation,
                        calculation_version=calculation.calculation_version,
                        content_hash=calculation.content_hash,
                    )
                )
            repository.record_projection_success(calculation.calculation_version, now)
            acknowledgement = self._dirty_repository_factory(session).acknowledge_projection(
                marker.user_id, window.start, marker.generation
            )
            if acknowledgement.status is DirtyAcknowledgementStatus.STALE:
                self._rollback(session)
                return ProjectionProcessResult(outcome=ProjectionProcessOutcome.STALE)
            return ProjectionProcessResult(
                outcome=ProjectionProcessOutcome.APPLIED,
                appended_revision=appended_revision,
                created_current_working=created_current,
            )
        except Exception:
            self._rollback(session)
            raise

    def process_overdue(
        self, session: Session, observed: WorkingProjectionRecord
    ) -> ProjectionProcessResult:
        """Finalize one refetched overdue row from a fresh canonical read, not stale payload."""
        if not isinstance(observed, WorkingProjectionRecord):
            raise TypeError("observed must be a WorkingProjectionRecord")
        now = normalize_utc(self._clock.now())
        try:
            reader, repository = self._bound(session)
            repository.require_active(reader.calculation_version)
            working = repository.get_working(observed.user_id, observed.window)
            if working is None:
                return ProjectionProcessResult(outcome=ProjectionProcessOutcome.ABSENT)
            if working.window.end > now:
                raise ProjectionCandidateError("working projection is not overdue")
            if working.calculation_version != reader.calculation_version:
                raise ProjectionCalculationVersionMismatchError(
                    "stored overdue working calculation version differs from runtime"
                )
            if (
                repository.pending_projection_generation(working.user_id, working.window)
                is not None
            ):
                return ProjectionProcessResult(outcome=ProjectionProcessOutcome.DEFERRED)
            calculation = self._calculation(reader, working.user_id, working.window)
            appended_revision = self._persist_developed(
                repository,
                working.user_id,
                working.window,
                calculation,
                working.source_generation,
                now,
            )
            if not repository.delete_working(working):
                raise ProjectionStateError("overdue working row changed before deletion")
            created_current = self._ensure_current_working(repository, reader, working.user_id, now)
            repository.record_projection_success(calculation.calculation_version, now)
            return ProjectionProcessResult(
                outcome=ProjectionProcessOutcome.APPLIED,
                appended_revision=appended_revision,
                created_current_working=created_current,
            )
        except Exception:
            self._rollback(session)
            raise

    def _bound(self, session: Session) -> tuple[WeeklyStatsReader, WeeklyProjectionRepository]:
        if not isinstance(session, Session):
            raise TypeError("session must be a Session")
        return (
            self._reader_factory(session, self._top_tags_limit),
            self._repository_factory(session),
        )

    def _calculation(
        self, reader: WeeklyStatsReader, user_id: int, window: WeeklyWindow
    ) -> WeeklyCalculation:
        calculation = calculate_weekly_payload(reader.read(user_id, window), self._top_tags_limit)
        if calculation.calculation_version != reader.calculation_version:
            raise ProjectionCalculationVersionMismatchError(
                "weekly reader calculation version differs from projection calculation"
            )
        return calculation

    @staticmethod
    def _persist_developed(
        repository: WeeklyProjectionRepository,
        user_id: int,
        window: WeeklyWindow,
        calculation: WeeklyCalculation,
        source_generation: int,
        now: datetime,
    ) -> int | None:
        existing = repository.effective_point(user_id, window)
        if existing is None:
            repository.append_point(
                NewProjectionPoint(
                    user_id=user_id,
                    window=window,
                    revision=1,
                    supersedes_id=None,
                    payload=calculation.payload,
                    calculated_at=now,
                    developed_at=now,
                    correction_reason=None,
                    source_generation=source_generation,
                    calculation_version=calculation.calculation_version,
                    content_hash=calculation.content_hash,
                )
            )
            return 1
        comparison = compare_content_hashes(
            stored_version=existing.calculation_version,
            stored_hash=existing.content_hash,
            candidate_version=calculation.calculation_version,
            candidate_hash=calculation.content_hash,
        )
        if comparison is HashComparison.VERSION_MISMATCH:
            raise ProjectionCalculationVersionMismatchError(
                "stored developed point calculation version differs from runtime"
            )
        if comparison is HashComparison.SAME:
            return None
        revision = existing.revision + 1
        repository.append_point(
            NewProjectionPoint(
                user_id=user_id,
                window=window,
                revision=revision,
                supersedes_id=existing.id,
                payload=calculation.payload,
                calculated_at=now,
                developed_at=now,
                correction_reason=CorrectionReason.LATE_RECALCULATION,
                source_generation=source_generation,
                calculation_version=calculation.calculation_version,
                content_hash=calculation.content_hash,
            )
        )
        return revision

    def _ensure_current_working(
        self,
        repository: WeeklyProjectionRepository,
        reader: WeeklyStatsReader,
        user_id: int,
        now: datetime,
    ) -> bool:
        if not repository.user_exists(user_id):
            return False
        window = WeeklyWindow.from_datetime(now)
        current = repository.get_working(user_id, window)
        if current is not None:
            if current.calculation_version != reader.calculation_version:
                raise ProjectionCalculationVersionMismatchError(
                    "current working projection calculation version differs from runtime"
                )
            return False
        calculation = self._calculation(reader, user_id, window)
        repository.replace_working(
            WorkingProjectionRecord(
                user_id=user_id,
                window=window,
                payload=calculation.payload,
                calculated_at=now,
                source_generation=0,
                calculation_version=calculation.calculation_version,
                content_hash=calculation.content_hash,
            )
        )
        return True

    @staticmethod
    def _rollback(session: Session) -> None:
        session.rollback()


class BaselineRunner:
    """Own one session transaction per restartable baseline step."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        clock: Clock,
        top_tags_limit: int,
        batch_size: int,
        reader_factory: WeeklyReaderFactory = WeeklyStatsReader,
        repository_factory: ProjectionRepositoryFactory = WeeklyProjectionRepository,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        if not hasattr(clock, "now") or not callable(clock.now):
            raise TypeError("clock must provide now()")
        if isinstance(top_tags_limit, bool) or not isinstance(top_tags_limit, int):
            raise TypeError("top_tags_limit must be an integer")
        if isinstance(batch_size, bool) or not isinstance(batch_size, int):
            raise TypeError("batch_size must be an integer")
        if not 1 <= batch_size <= _MAX_BASELINE_BATCH_SIZE:
            raise ValueError("batch_size must be between 1 and 100")
        if not callable(reader_factory):
            raise TypeError("reader_factory must be callable")
        if not callable(repository_factory):
            raise TypeError("repository_factory must be callable")
        self._session_factory = session_factory
        self._clock = clock
        self._top_tags_limit = top_tags_limit
        self._batch_size = batch_size
        self._reader_factory = reader_factory
        self._repository_factory = repository_factory

    def run_step(self) -> ProjectionBaselineResult:
        """Persist no more than one candidate page, rolling it back as one unit on failure."""
        session = self._session_factory()
        try:
            now = normalize_utc(self._clock.now())
            reader = self._reader_factory(session, self._top_tags_limit)
            repository = self._repository_factory(session)
            state = repository.start_or_resume(reader.calculation_version, now)
            if state.status is _ProjectionStateStatus.ACTIVE:
                session.commit()
                return ProjectionBaselineResult(
                    processed_candidate_count=0,
                    has_more=False,
                    active=True,
                )

            checkpoint = self._checkpoint(state)
            candidates = repository.surviving_candidates_after(checkpoint, self._batch_size + 1)
            page = candidates[: self._batch_size]
            has_more = len(candidates) > self._batch_size
            for candidate in page:
                self._persist_candidate(
                    repository=repository,
                    reader=reader,
                    candidate=candidate,
                    now=now,
                )

            if page:
                repository.advance(page[-1], now)
            if not has_more:
                repository.activate(now)
            session.commit()
            return ProjectionBaselineResult(
                processed_candidate_count=len(page),
                has_more=has_more,
                active=not has_more,
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _checkpoint(state: ProjectionStateRecord) -> SurvivingWindowCandidate | None:
        if state.checkpoint_user_id is None:
            return None
        if state.checkpoint_window is None:
            raise ProjectionStateError("running state has an incomplete checkpoint")
        return SurvivingWindowCandidate(
            user_id=state.checkpoint_user_id,
            window=state.checkpoint_window,
        )

    def _persist_candidate(
        self,
        *,
        repository: WeeklyProjectionRepository,
        reader: WeeklyStatsReader,
        candidate: SurvivingWindowCandidate,
        now: datetime,
    ) -> None:
        window = candidate.window
        if window.start > now:
            raise ProjectionCandidateError("future surviving candidate cannot be baselined")
        calculation = calculate_weekly_payload(
            reader.read(candidate.user_id, window), self._top_tags_limit
        )
        if calculation.calculation_version != reader.calculation_version:
            raise ProjectionCalculationVersionMismatchError(
                "weekly reader calculation version differs from persisted calculation"
            )
        if window.end <= now:
            self._persist_closed_candidate(repository, candidate, calculation, now)
            return
        self._persist_current_candidate(repository, candidate, calculation, now)

    @staticmethod
    def _persist_closed_candidate(
        repository: WeeklyProjectionRepository,
        candidate: SurvivingWindowCandidate,
        calculation: WeeklyCalculation,
        now: datetime,
    ) -> None:
        existing = repository.effective_point(candidate.user_id, candidate.window)
        if existing is None:
            repository.append_point(
                NewProjectionPoint(
                    user_id=candidate.user_id,
                    window=candidate.window,
                    revision=1,
                    supersedes_id=None,
                    payload=calculation.payload,
                    calculated_at=now,
                    developed_at=now,
                    correction_reason=None,
                    source_generation=0,
                    calculation_version=calculation.calculation_version,
                    content_hash=calculation.content_hash,
                )
            )
            return
        comparison = compare_content_hashes(
            stored_version=existing.calculation_version,
            stored_hash=existing.content_hash,
            candidate_version=calculation.calculation_version,
            candidate_hash=calculation.content_hash,
        )
        if comparison is HashComparison.VERSION_MISMATCH:
            raise ProjectionCalculationVersionMismatchError(
                "stored developed point calculation version differs from runtime"
            )
        # A same-version changed root remains immutable; the later dirty consumer owns correction.

    @staticmethod
    def _persist_current_candidate(
        repository: WeeklyProjectionRepository,
        candidate: SurvivingWindowCandidate,
        calculation: WeeklyCalculation,
        now: datetime,
    ) -> None:
        existing = repository.get_working(candidate.user_id, candidate.window)
        if existing is not None and existing.calculation_version != calculation.calculation_version:
            raise ProjectionCalculationVersionMismatchError(
                "stored working projection calculation version differs from runtime"
            )
        repository.replace_working(
            WorkingProjectionRecord(
                user_id=candidate.user_id,
                window=candidate.window,
                payload=calculation.payload,
                calculated_at=now,
                source_generation=0,
                calculation_version=calculation.calculation_version,
                content_hash=calculation.content_hash,
            )
        )


__all__ = [
    "BaselineRunner",
    "ProjectionBaselineResult",
    "ProjectionProcessOutcome",
    "ProjectionProcessResult",
    "ProjectionProcessor",
]
