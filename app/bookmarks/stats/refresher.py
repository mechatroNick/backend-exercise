"""Lifecycle-owned canonical current-statistics refresher."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from threading import Event, Lock, Thread, current_thread
from time import perf_counter
from typing import Protocol
from uuid import UUID

from sqlmodel import Session

from app.bookmarks.stats.dirty import BookmarkStatsDirtyRepository, DirtyMarker
from app.bookmarks.stats.publisher import StatsInvalidationPublisher
from app.bookmarks.stats.raw_sql import BookmarkStatsReader
from app.bookmarks.stats.snapshots import StatsSnapshotStore
from app.core.clock import Clock, normalize_utc
from app.core.internal_models import FrozenInternalModel
from app.core.logging import log_event, log_exception
from app.db.engine import SessionFactory

_MAX_BATCH_SIZE = 100
_THREAD_NAME = "bookmark-stats-refresher"
_SafeValue = bool | int | float | str


class _ThreadFactory(Protocol):
    def __call__(
        self,
        *,
        target: Callable[[], None],
        name: str,
        daemon: bool,
    ) -> Thread: ...


class _RefresherBoundaryError(RuntimeError):
    """Sanitized exception that retains worker frames without adapter text."""


class RefresherState(FrozenInternalModel):
    """Bounded operational state without user, resource, or content identifiers."""

    started: bool
    alive: bool
    cycle_running: bool
    initial_completed: bool
    initial_success: bool
    last_cycle_started_at: datetime | None
    last_cycle_completed_at: datetime | None
    last_success_at: datetime | None
    total_cycles: int
    successful_cycles: int
    consecutive_failures: int
    last_affected_user_count: int
    last_marker_count: int
    last_error_code: str | None
    shutdown_timed_out: bool


def _positive(value: int, name: str, *, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return value


def _timeout(value: int | float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{name} must be a nonnegative number")
    return float(value)


class StatsRefresher:
    """Own one non-overlapping worker loop and generation-safe refresh cycles."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        publisher: StatsInvalidationPublisher,
        store: StatsSnapshotStore,
        clock: Clock,
        top_tags_limit: int,
        interval_seconds: int,
        full_reconciliation_seconds: int,
        batch_size: int,
        logger: logging.Logger,
        service_instance_id: UUID,
        thread_factory: _ThreadFactory = Thread,
    ) -> None:
        _positive(top_tags_limit, "top_tags_limit", maximum=100)
        _positive(interval_seconds, "interval_seconds")
        _positive(full_reconciliation_seconds, "full_reconciliation_seconds")
        if full_reconciliation_seconds < interval_seconds:
            raise ValueError("full_reconciliation_seconds must be at least interval_seconds")
        _positive(batch_size, "batch_size", maximum=_MAX_BATCH_SIZE)
        if not isinstance(service_instance_id, UUID) or service_instance_id.int == 0:
            raise ValueError("service_instance_id must be a non-nil UUID")
        self._session_factory = session_factory
        self._publisher = publisher
        self._store = store
        self._clock = clock
        self._top_tags_limit = top_tags_limit
        self._interval_seconds = interval_seconds
        self._full_reconciliation_seconds = full_reconciliation_seconds
        self._batch_size = batch_size
        self._logger = logger
        self._service_instance_id = str(service_instance_id)
        self._thread_factory = thread_factory

        self._stop_event = Event()
        self._initial_event = Event()
        self._cycle_lock = Lock()
        self._state_lock = Lock()
        self._thread: Thread | None = None
        self._started = False
        self._cycle_running = False
        self._initial_success = False
        self._last_cycle_started_at: datetime | None = None
        self._last_cycle_completed_at: datetime | None = None
        self._last_success_at: datetime | None = None
        self._last_full_reconciliation_at: datetime | None = None
        self._full_cursor = 0
        self._total_cycles = 0
        self._successful_cycles = 0
        self._consecutive_failures = 0
        self._last_affected_user_count = 0
        self._last_marker_count = 0
        self._last_error_code: str | None = None
        self._shutdown_timed_out = False
        self._worker_exited = False
        self._deferred_stop_callbacks: list[Callable[[], None]] = []

    def start(self) -> bool:
        """Start the exact worker once; construction itself remains inert."""
        with self._state_lock:
            if self._started:
                return False
            self._started = True
            self._worker_exited = False
            self._stop_event.clear()
            thread = self._thread_factory(target=self._run, name=_THREAD_NAME, daemon=False)
            self._thread = thread
        self._log_event(
            logging.INFO,
            "bookmark_stats.refresher_starting",
            message="statistics refresher starting",
            context={"interval_seconds": self._interval_seconds},
        )
        try:
            thread.start()
        except Exception:
            with self._state_lock:
                self._started = False
                self._thread = None
                self._last_error_code = "thread_start_failed"
            raise
        return True

    def wait_initial(self, timeout_seconds: int | float) -> bool:
        """Wait a bounded duration for the immediate startup cycle."""
        timeout = _timeout(timeout_seconds, "timeout_seconds")
        if not self._initial_event.wait(timeout):
            return False
        with self._state_lock:
            return self._initial_success

    def stop(self, timeout_seconds: int | float) -> bool:
        """Request cooperative stop and make one bounded join attempt."""
        timeout = _timeout(timeout_seconds, "timeout_seconds")
        with self._state_lock:
            thread = self._thread
        if thread is None:
            return True
        self._log_event(
            logging.INFO,
            "bookmark_stats.refresher_stopping",
            message="statistics refresher stopping",
        )
        self._stop_event.set()
        if thread is not current_thread():
            thread.join(timeout)
        stopped = not thread.is_alive()
        with self._state_lock:
            self._shutdown_timed_out = not stopped
            if not stopped:
                self._last_error_code = "shutdown_timeout"
        if stopped:
            self._log_event(
                logging.INFO,
                "bookmark_stats.refresher_stopped",
                message="statistics refresher stopped",
            )
        else:
            self._log_event(
                logging.ERROR,
                "bookmark_stats.refresher_join_timeout",
                outcome="failure",
                message="statistics refresher did not stop within the configured timeout",
                context={"shutdown_timeout_seconds": timeout},
            )
        return stopped

    def defer_until_stopped(self, callback: Callable[[], None]) -> None:
        """Run cleanup after worker exit, or immediately when it has already exited."""
        if not callable(callback):
            raise TypeError("callback must be callable")
        with self._state_lock:
            run_now = self._thread is None or self._worker_exited
            if not run_now:
                self._deferred_stop_callbacks.append(callback)
        if run_now:
            with suppress(Exception):
                callback()

    def run_cycle(self, *, full: bool = False) -> bool:
        """Run one bounded canonical cycle; return false when work must retry."""
        if not isinstance(full, bool):
            raise TypeError("full must be a boolean")
        if not self._cycle_lock.acquire(blocking=False):
            return False
        started_at = self._safe_now(datetime.now(UTC))
        started_monotonic = perf_counter()
        session: Session | None = None
        affected_user_count = 0
        marker_count = 0
        first_error: Exception | None = None
        success = False
        full_requested = full
        full_page: tuple[int, ...] = ()
        full_page_complete = False
        durable_backlog_empty = False
        with self._state_lock:
            self._cycle_running = True
            self._last_cycle_started_at = started_at
        try:
            session = self._session_factory()
            repository = BookmarkStatsDirtyRepository(session)
            events = self._publisher.drain(self._batch_size)
            markers = repository.observe(self._batch_size)
            marker_count = len(markers)
            publisher_state = self._publisher.state()
            full_requested = full or publisher_state.reconciliation_required
            if full_requested:
                full_page = repository.user_ids_after(self._full_cursor, self._batch_size)
                full_page_complete = len(full_page) < self._batch_size

            users = {event.user_id for event in events}
            users.update(marker.user_id for marker in markers)
            users.update(full_page)
            affected_user_count = len(users)
            markers_by_user: dict[int, tuple[DirtyMarker, ...]] = {
                user_id: tuple(marker for marker in markers if marker.user_id == user_id)
                for user_id in users
            }
            session.rollback()

            successful_users = 0
            for user_id in sorted(users):
                try:
                    if self._refresh_user(session, user_id, markers_by_user[user_id]):
                        successful_users += 1
                    elif first_error is None:
                        first_error = _RefresherBoundaryError(
                            "statistics candidate became stale during finalization"
                        )
                except Exception as error:
                    self._rollback_safely(session)
                    if first_error is None:
                        first_error = error

            success = successful_users == affected_user_count
            if full_requested:
                durable_backlog_empty = repository.backlog().count == 0
                if success and full_page_complete and durable_backlog_empty:
                    self._full_cursor = 0
                    acknowledged = self._publisher.acknowledge_full_reconciliation(
                        publisher_state.reconciliation_epoch
                    )
                    if acknowledged:
                        full_completed_at = self._now()
                        with self._state_lock:
                            self._last_full_reconciliation_at = full_completed_at
                elif success and full_page:
                    self._full_cursor = full_page[-1]
                    self._publisher.require_full_reconciliation()
                else:
                    self._publisher.require_full_reconciliation()
        except Exception as error:
            if session is not None:
                self._rollback_safely(session)
            first_error = error
            success = False
            with suppress(Exception):
                self._publisher.require_full_reconciliation()
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception as error:
                    first_error = error
                    success = False
                    with suppress(Exception):
                        self._publisher.require_full_reconciliation()
            completed_at = self._safe_now(started_at)
            duration_ms = max(0, round((perf_counter() - started_monotonic) * 1000))
            with self._state_lock:
                self._cycle_running = False
                self._last_cycle_completed_at = completed_at
                self._total_cycles += 1
                self._last_affected_user_count = affected_user_count
                self._last_marker_count = marker_count
                if success:
                    self._successful_cycles += 1
                    self._consecutive_failures = 0
                    self._last_success_at = completed_at
                    self._last_error_code = None
                else:
                    self._consecutive_failures += 1
                    self._last_error_code = "cycle_failed"
                consecutive_failures = self._consecutive_failures
            self._cycle_lock.release()

        context: dict[str, _SafeValue] = {
            "duration_ms": duration_ms,
            "affected_user_count": affected_user_count,
            "marker_count": marker_count,
            "full_reconciliation": full_requested,
            "failure_count": consecutive_failures,
        }
        if success:
            self._log_event(
                logging.INFO,
                "bookmark_stats.refresh_cycle_succeeded",
                message="statistics refresh cycle succeeded",
                context=context,
            )
        else:
            self._log_failure(first_error, context)
        return success

    def snapshot_healthy(self) -> bool:
        """Report whether the enabled worker has a successful current lifecycle."""
        with self._state_lock:
            thread = self._thread
            return bool(
                self._started
                and thread is not None
                and thread.is_alive()
                and self._initial_event.is_set()
                and self._initial_success
                and self._last_success_at is not None
                and self._consecutive_failures == 0
                and not self._shutdown_timed_out
            )

    def state(self) -> RefresherState:
        """Return one immutable, identifier-free lifecycle snapshot."""
        with self._state_lock:
            thread = self._thread
            return RefresherState(
                started=self._started,
                alive=bool(thread is not None and thread.is_alive()),
                cycle_running=self._cycle_running,
                initial_completed=self._initial_event.is_set(),
                initial_success=self._initial_success,
                last_cycle_started_at=self._last_cycle_started_at,
                last_cycle_completed_at=self._last_cycle_completed_at,
                last_success_at=self._last_success_at,
                total_cycles=self._total_cycles,
                successful_cycles=self._successful_cycles,
                consecutive_failures=self._consecutive_failures,
                last_affected_user_count=self._last_affected_user_count,
                last_marker_count=self._last_marker_count,
                last_error_code=self._last_error_code,
                shutdown_timed_out=self._shutdown_timed_out,
            )

    def _refresh_user(
        self,
        session: Session,
        user_id: int,
        markers: tuple[DirtyMarker, ...],
    ) -> bool:
        expected_epoch = self._store.epoch(user_id)
        stats = BookmarkStatsReader(session, self._top_tags_limit).read(user_id)
        generated_at = self._now()
        session.rollback()

        repository = BookmarkStatsDirtyRepository(session)
        for marker in markers:
            if not repository.complete(marker.user_id, marker.window_start, marker.generation):
                self._rollback_safely(session)
                return False

        source_generation = max((marker.generation for marker in markers), default=0)
        try:
            published = self._store.publish(
                user_id=user_id,
                stats=stats,
                generated_at=generated_at,
                source_generation=source_generation,
                expected_epoch=expected_epoch,
            )
        except Exception:
            self._rollback_safely(session)
            raise
        if not published:
            self._rollback_safely(session)
            return False
        try:
            if markers:
                session.commit()
        except Exception:
            self._invalidate_safely(user_id)
            self._rollback_safely(session)
            raise
        return True

    def _run(self) -> None:
        try:
            initial_success = self.run_cycle(full=True)
            with self._state_lock:
                self._initial_success = initial_success
            self._initial_event.set()
            self._log_event(
                logging.INFO if initial_success else logging.WARNING,
                "bookmark_stats.refresher_started",
                outcome="success" if initial_success else "degraded",
                message="statistics refresher started",
                context={
                    "initial_success": initial_success,
                    "failure_count": 0 if initial_success else 1,
                    "interval_seconds": self._interval_seconds,
                    "worker_is_daemon": current_thread().daemon,
                },
            )
            while not self._stop_event.wait(self._interval_seconds):
                now = self._safe_now(self._last_cycle_completed_at or datetime.now(UTC))
                with self._state_lock:
                    last_full = self._last_full_reconciliation_at
                    consecutive_failures = self._consecutive_failures
                full_due = last_full is None or now - last_full >= timedelta(
                    seconds=self._full_reconciliation_seconds
                )
                try:
                    reconciliation_required = self._publisher.state().reconciliation_required
                except Exception:
                    reconciliation_required = True
                if consecutive_failures > 0:
                    self._log_event(
                        logging.WARNING,
                        "bookmark_stats.refresh_retrying",
                        outcome="degraded",
                        message="statistics refresh retrying after failure",
                        context={"failure_count": consecutive_failures},
                    )
                self.run_cycle(full=full_due or reconciliation_required)
        finally:
            with self._state_lock:
                self._worker_exited = True
                callbacks = tuple(self._deferred_stop_callbacks)
                self._deferred_stop_callbacks.clear()
            for callback in callbacks:
                with suppress(Exception):
                    callback()

    def _now(self) -> datetime:
        return normalize_utc(self._clock.now())

    def _safe_now(self, fallback: datetime) -> datetime:
        try:
            return self._now()
        except Exception:
            return fallback

    def _invalidate_safely(self, user_id: int) -> None:
        with suppress(Exception):
            self._store.invalidate(user_id)

    @staticmethod
    def _rollback_safely(session: Session) -> None:
        with suppress(Exception):
            session.rollback()

    def _safe_context(self, context: dict[str, _SafeValue] | None = None) -> dict[str, _SafeValue]:
        return {"service_instance_id": self._service_instance_id} | (context or {})

    def _log_event(
        self,
        level: int,
        event: str,
        *,
        outcome: str = "success",
        message: str,
        context: dict[str, _SafeValue] | None = None,
    ) -> None:
        with suppress(Exception):
            log_event(
                self._logger,
                level,
                event,
                outcome=outcome,
                message=message,
                context=self._safe_context(context),
                component="bookmark_stats_refresher",
                stacklevel=2,
            )

    def _log_failure(
        self,
        error: Exception | None,
        context: dict[str, _SafeValue],
    ) -> None:
        safe_error = _RefresherBoundaryError("statistics refresh cycle failed").with_traceback(
            None if error is None else error.__traceback__
        )
        with suppress(Exception):
            log_exception(
                self._logger,
                "bookmark_stats.refresh_cycle_failed",
                exception=safe_error,
                message="statistics refresh cycle failed",
                context=self._safe_context(context),
                component="bookmark_stats_refresher",
                stacklevel=2,
            )


__all__ = ["RefresherState", "StatsRefresher"]
