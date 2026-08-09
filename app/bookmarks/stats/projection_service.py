"""Restartable, surviving-data-only initial weekly projection baseline."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlmodel import Session

from app.bookmarks.stats.projection_repository import (
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


__all__ = ["BaselineRunner", "ProjectionBaselineResult"]
